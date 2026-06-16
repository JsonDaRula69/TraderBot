import { removeMessagesByPane } from "./session-registry"
import { analyzePaneContent, captureTmuxPane, sendToPane } from "./tmux"
import { getCurrentTmuxSession, getTmuxSessionName } from "./tmux"
import { logReplyListenerMessage } from "./reply-listener-log"
import type { OpenClawConfig } from "./types"

export function sanitizeReplyInput(text: string): string {
  return text
    .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, "")
    .replace(/[\u200e\u200f\u202a-\u202e\u2066-\u2069]/g, "")
    .replace(/\r?\n/g, " ")
    .replace(/\\/g, "\\\\")
    .replace(/`/g, "\\`")
    .replace(/\$\(/g, "\\$(")
    .replace(/\$\{/g, "\\${")
    .trim()
}

export class ReplyListenerRateLimiter {
  private readonly maxPerMinute: number
  private readonly timestamps: number[] = []
  private readonly windowMs = 60 * 1000

  constructor(maxPerMinute: number) {
    this.maxPerMinute = maxPerMinute
  }

  canProceed(): boolean {
    const now = Date.now()
    const recent = this.timestamps.filter((timestamp) => now - timestamp < this.windowMs)
    this.timestamps.length = 0
    this.timestamps.push(...recent)

    if (this.timestamps.length >= this.maxPerMinute) {
      return false
    }

    this.timestamps.push(now)
    return true
  }
}

/**
 * Find the best tmux pane for injecting direct messages.
 *
 * Resolution order:
 * 1. Config-specified `directMessageTargetPane` — explicit, most reliable
 * 2. The current tmux session's active pane — detected from the environment
 * 3. Fallback: search for a pane running OpenCode by analyzing pane content
 */
async function resolveDirectMessagePane(config: OpenClawConfig): Promise<string | null> {
  const replyListener = config.replyListener

  // 1. Explicit target pane from config
  if (replyListener?.directMessageTargetPane) {
    return replyListener.directMessageTargetPane
  }

  // 2. Current tmux session
  const currentSession = getCurrentTmuxSession()
  if (currentSession) {
    // Try to find a pane running OpenCode in this session
    const sessionName = await getTmuxSessionName()
    if (sessionName) {
      // Use the session name as the pane target — tmux will pick the active pane
      return sessionName
    }
  }

  // 3. No viable target found
  return null
}

/**
 * Inject a direct (non-reply) message into the AutoDev session.
 *
 * Unlike correlated replies which go to a specific tmux pane identified by
 * message ID correlation, direct messages go to a resolved target pane.
 *
 * The message is prefixed with `[direct]` (or a custom prefix) and includes
 * the sender's username so AutoDev knows who sent it and that it's a new
 * conversation rather than a reply to an existing one.
 */
export async function injectDirectMessageIntoSession(
  text: string,
  platform: string,
  config: OpenClawConfig,
): Promise<boolean> {
  const paneId = await resolveDirectMessagePane(config)
  if (!paneId) {
    logReplyListenerMessage("WARN: No target pane found for direct message injection. Set directMessageTargetPane in config.")
    return false
  }

  const replyListener = config.replyListener
  const prefix = replyListener?.includePrefix === false ? "" : `[direct:${platform}] `
  const sanitized = sanitizeReplyInput(prefix + text)
  const truncated = sanitized.slice(0, replyListener?.maxMessageLength ?? 500)

  const success = await sendToPane(paneId, truncated, true)

  if (success) {
    logReplyListenerMessage(
      `Injected direct message from ${platform} into pane ${paneId}: "${truncated.slice(0, 50)}${truncated.length > 50 ? "..." : ""}"`,
    )
  } else {
    logReplyListenerMessage(`ERROR: Failed to inject direct message into pane ${paneId}`)
  }

  return success
}

export async function injectReplyIntoPane(
  paneId: string,
  text: string,
  platform: string,
  config: OpenClawConfig,
): Promise<boolean> {
  const replyListener = config.replyListener
  const content = await captureTmuxPane(paneId, 15)
  const analysis = analyzePaneContent(content)

  if (analysis.confidence < 0.3) {
    logReplyListenerMessage(
      `WARN: Pane ${paneId} does not appear to be running OpenCode CLI (confidence: ${analysis.confidence}). Skipping injection, removing stale mapping.`,
    )
    removeMessagesByPane(paneId)
    return false
  }

  const prefix = replyListener?.includePrefix === false ? "" : `[reply:${platform}] `
  const sanitized = sanitizeReplyInput(prefix + text)
  const truncated = sanitized.slice(0, replyListener?.maxMessageLength ?? 500)
  const success = await sendToPane(paneId, truncated, true)

  if (success) {
    logReplyListenerMessage(
      `Injected reply from ${platform} into pane ${paneId}: "${truncated.slice(0, 50)}${truncated.length > 50 ? "..." : ""}"`,
    )
  } else {
    logReplyListenerMessage(`ERROR: Failed to inject reply into pane ${paneId}`)
  }

  return success
}
