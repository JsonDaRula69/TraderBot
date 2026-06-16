import { lookupByMessageId } from "./session-registry"
import { injectReplyIntoPane, injectDirectMessageIntoSession, ReplyListenerRateLimiter } from "./reply-listener-injection"
import { logReplyListenerMessage } from "./reply-listener-log"
import {
  recordSeenDiscordMessage,
  writeReplyListenerDaemonState,
  type ReplyListenerDaemonState,
} from "./reply-listener-state"
import type { OpenClawConfig } from "./types"

interface DiscordMessage {
  id: string
  content: string
  author: { id: string; username?: string }
  message_reference?: { message_id?: string }
}

let discordBackoffUntil = 0

export async function pollDiscordReplies(
  config: OpenClawConfig,
  state: ReplyListenerDaemonState,
  rateLimiter: ReplyListenerRateLimiter,
): Promise<void> {
  const replyListener = config.replyListener
  if (!replyListener?.discordBotToken || !replyListener.discordChannelId) return
  if (!replyListener.authorizedDiscordUserIds || replyListener.authorizedDiscordUserIds.length === 0) {
    return
  }
  if (Date.now() < discordBackoffUntil) return

  try {
    const after = state.discordLastMessageId
      ? `?after=${state.discordLastMessageId}&limit=10`
      : "?limit=10"
    const url = `https://discord.com/api/v10/channels/${replyListener.discordChannelId}/messages${after}`

    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 10000)
    const response = await fetch(url, {
      method: "GET",
      headers: { Authorization: `Bot ${replyListener.discordBotToken}` },
      signal: controller.signal,
    })
    clearTimeout(timeout)

    const remaining = response.headers.get("x-ratelimit-remaining")
    const reset = response.headers.get("x-ratelimit-reset")
    if (remaining !== null && Number.parseInt(remaining, 10) < 2) {
      const parsedReset = reset ? Number.parseFloat(reset) : Number.NaN
      const resetTime = Number.isFinite(parsedReset) ? parsedReset * 1000 : Date.now() + 10000
      discordBackoffUntil = resetTime
      logReplyListenerMessage(
        `WARN: Discord rate limit low (remaining: ${remaining}), backing off until ${new Date(resetTime).toISOString()}`,
      )
    }

    if (!response.ok) {
      state.errors += 1
      state.lastError = `Discord API error: HTTP ${response.status}`
      logReplyListenerMessage(state.lastError)
      writeReplyListenerDaemonState(state)
      return
    }

    const messages = await response.json()
    if (!Array.isArray(messages) || messages.length === 0) return

    for (const message of [...messages as DiscordMessage[]].reverse()) {
      recordSeenDiscordMessage(state, message.id)
      writeReplyListenerDaemonState(state)

      // Skip messages from unauthorized users
      if (!replyListener.authorizedDiscordUserIds.includes(message.author.id)) continue

      const replyToMessageId = message.message_reference?.message_id

      if (replyToMessageId) {
        // --- Correlated reply: inject into the tmux pane that sent the original message ---
        const mapping = lookupByMessageId("discord-bot", replyToMessageId)
        if (!mapping) continue

        if (!rateLimiter.canProceed()) {
          logReplyListenerMessage(`WARN: Rate limit exceeded, dropping Discord reply ${message.id}`)
          state.errors += 1
          continue
        }

        const success = await injectReplyIntoPane(mapping.tmuxPaneId, message.content, "discord", config)
        if (success) {
          state.messagesInjected += 1
          // Acknowledge with ✅ reaction
          try {
            await fetch(
              `https://discord.com/api/v10/channels/${replyListener.discordChannelId}/messages/${message.id}/reactions/%E2%9C%85/@me`,
              {
                method: "PUT",
                headers: { Authorization: `Bot ${replyListener.discordBotToken}` },
              },
            )
          } catch (error) {
            logReplyListenerMessage(
              `WARN: Failed to acknowledge Discord message ${message.id}: ${error instanceof Error ? error.message : String(error)}`,
            )
          }
        } else {
          state.errors += 1
        }
      } else if (replyListener.acceptDirectMessages) {
        // --- Direct message: not a reply, but from an authorized user ---
        // Inject into the active AutoDev session with [direct] prefix
        if (!rateLimiter.canProceed()) {
          logReplyListenerMessage(`WARN: Rate limit exceeded, dropping Discord direct message ${message.id}`)
          state.errors += 1
          continue
        }

        const prefix = replyListener.directMessagePrefix ?? "[direct]"
        const content = `${prefix} <${message.author.username ?? message.author.id}> ${message.content}`

        const success = await injectDirectMessageIntoSession(content, "discord", config)
        if (success) {
          state.messagesInjected += 1
          // Acknowledge with 🔔 reaction (different from reply ✅)
          try {
            await fetch(
              `https://discord.com/api/v10/channels/${replyListener.discordChannelId}/messages/${message.id}/reactions/%F0%9F%94%94/@me`,
              {
                method: "PUT",
                headers: { Authorization: `Bot ${replyListener.discordBotToken}` },
              },
            )
          } catch (error) {
            logReplyListenerMessage(
              `WARN: Failed to acknowledge Discord direct message ${message.id}: ${error instanceof Error ? error.message : String(error)}`,
            )
          }
        } else {
          state.errors += 1
        }
      }
      // If neither a correlated reply nor acceptDirectMessages, skip silently

      writeReplyListenerDaemonState(state)
    }
  } catch (error) {
    state.errors += 1
    state.lastError = error instanceof Error ? error.message : String(error)
    logReplyListenerMessage(`Discord polling error: ${state.lastError}`)
  }
}
