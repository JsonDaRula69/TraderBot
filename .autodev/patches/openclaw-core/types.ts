import type {
  OpenClawGateway,
  OpenClawHook,
} from "./types"

// Re-export types that already exist
export type { OpenClawGateway, OpenClawHook }

// Extended reply listener config with direct message support
export type OpenClawReplyListenerConfig = {
  readonly discordBotToken?: string
  readonly discordChannelId?: string
  readonly discordMention?: string
  readonly authorizedDiscordUserIds?: readonly string[]
  readonly telegramBotToken?: string
  readonly telegramChatId?: string
  readonly pollIntervalMs?: number
  readonly rateLimitPerMinute?: number
  readonly maxMessageLength?: number
  readonly includePrefix?: boolean
  // --- New fields for direct message support ---
  /**
   * When true, accept non-reply messages from authorized users and inject them
   * into the AutoDev tmux session. Direct messages are prefixed with [direct]
   * to distinguish them from correlated replies.
   *
   * Default: false (original behavior — only replies are processed)
   */
  readonly acceptDirectMessages?: boolean
  /**
   * The tmux pane ID to inject direct messages into. If not specified, direct
   * messages are injected into the tmux pane determined by the current session.
   *
   * For AutoDev, this should be set to the tmux pane running the Sisyphus (lead)
   * session, e.g., "autodev.0" or "%0".
   */
  readonly directMessageTargetPane?: string
  /**
   * Prefix for direct messages injected into the session. Defaults to "[direct]".
   * This helps AutoDev distinguish between correlated replies and new conversations.
   */
  readonly directMessagePrefix?: string
}

export type OpenClawConfig = {
  readonly enabled: boolean
  readonly gateways: Record<string, OpenClawGateway>
  readonly hooks: Record<string, OpenClawHook>
  readonly replyListener?: OpenClawReplyListenerConfig
}

export interface OpenClawContext {
  sessionId?: string
  projectPath?: string
  projectName?: string
  tmuxSession?: string
  prompt?: string
  contextSummary?: string
  reasoning?: string
  question?: string
  tmuxTail?: string
  replyChannel?: string
  replyTarget?: string
  replyThread?: string
  [key: string]: string | undefined
}

export interface OpenClawPayload {
  event: string
  instruction: string
  text: string
  timestamp: string
  sessionId?: string
  projectPath?: string
  projectName?: string
  tmuxSession?: string
  tmuxTail?: string
  channel?: string
  to?: string
  threadId?: string
  context: OpenClawContext
}

export interface WakeResult {
  gateway: string
  success: boolean
  error?: string
  statusCode?: number
  messageId?: string
  platform?: string
  channelId?: string
  threadId?: string
}
