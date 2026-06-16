# Direct Message Support for OmO Reply Listener

## What This Adds

The OmO reply listener currently only processes **replies** to messages that AutoDev already sent. A human can respond to AutoDev's status updates, but they can't start a new conversation — they can only reply.

This patch adds `acceptDirectMessages` support, so authorized humans can type new messages in the Discord/Telegram channel and have them injected directly into AutoDev's session.

## How It Works

### Before (reply-only)

```
AutoDev sends status → Discord channel → message ID registered
Human replies to that message → reply listener picks it up
→ lookupByMessageId finds the tmux pane → inject into that pane
```

A message that isn't a reply is silently ignored (`if (!replyToMessageId) continue`).

### After (direct messages enabled)

```
Human types a new message → Discord channel
→ not a reply, but from an authorized user
→ inject into AutoDev's session with [direct] prefix
→ AutoDev sees: [direct:discord] <username> what's the status on issue #42?
```

Direct messages are distinguishable from replies:
- **Replies** get the `[reply:discord]` prefix
- **Direct messages** get the `[direct:discord] <username>` prefix

This lets AutoDev know whether it's continuing a conversation (reply) or starting a new one (direct).

## Config

Add three new fields to `replyListener` in `oh-my-openagent.jsonc`:

```jsonc
"replyListener": {
  "enabled": true,
  "acceptDirectMessages": true,            // Enable direct message support
  "directMessageTargetPane": "autodev.0",  // tmux pane ID for AutoDev's lead session
  "directMessagePrefix": "[direct]",       // Prefix for direct messages (default: "[direct]")
  
  // ... existing fields ...
  "discordBotToken": "...",
  "discordChannelId": "...",
  "authorizedDiscordUserIds": ["123456789"], // Discord user IDs allowed to send direct messages
  "telegramBotToken": "...",
  "telegramChatId": "..."
}
```

### New fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `acceptDirectMessages` | boolean | `false` | When true, non-reply messages from authorized users are injected into the session |
| `directMessageTargetPane` | string | (auto-detect) | tmux pane ID to inject direct messages into. If not set, auto-detects the current session |
| `directMessagePrefix` | string | `"[direct]"` | Prefix for direct messages. Distinguishes them from reply-correlated messages |

### `directMessageTargetPane`

This is the tmux pane where direct messages are injected. Options:

- **Explicit pane ID**: `"autodev.0"` — the first pane of the `autodev` tmux session. Most reliable.
- **Auto-detect**: Leave empty. The system will try to find the current tmux session. This works if AutoDev is the only tmux session running.
- **`%0`**: The tmux window ID. Works if you know the specific window number.

For AutoDev, set this to the tmux pane where Sisyphus (the lead agent) runs, since it's the triage entry point.

## Acknowledgment Reactions

To help humans know their message was received:

- **Replies** get a ✅ reaction on Discord, or "✅ Injected into session." on Telegram
- **Direct messages** get a 🔔 reaction on Discord, or "🔔 Injected into session." on Telegram

Different reactions so the human can tell which mode their message was processed in.

## Security Considerations

- `authorizedDiscordUserIds` is the authorization gate. Only users in this list can send direct messages to AutoDev. Everyone else's messages are silently ignored.
- The `acceptDirectMessages` flag is off by default. You have to explicitly enable it.
- The same rate limiting applies to direct messages as to replies (`rateLimitPerMinute`).

## Files Changed

All in `packages/openclaw-core/src/`:

| File | Change |
|------|--------|
| `types.ts` | Added `acceptDirectMessages`, `directMessageTargetPane`, `directMessagePrefix` to `OpenClawReplyListenerConfig` |
| `config.ts` | Added normalization for the three new fields |
| `reply-listener-discord.ts` | Added direct message handling alongside reply handling. Different flow for `!replyToMessageId && acceptDirectMessages`. Different acknowledgment reaction (🔔 vs ✅). |
| `reply-listener-telegram.ts` | Same as Discord — direct message handling alongside replies |
| `reply-listener-injection.ts` | Added `injectDirectMessageIntoSession()` function. Resolves target pane from config or auto-detect. Prefixed with `[direct:platform] <username>`. |

## How to Apply

These patches go into the `oh-my-openagent` repo at `packages/openclaw-core/src/`. Copy the modified files from `.autodev/patches/openclaw-core/` over the originals, or create a PR with the changes.

The patches are backward-compatible — `acceptDirectMessages` defaults to `false`, so existing installations work without any changes.
