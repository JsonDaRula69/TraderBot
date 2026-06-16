# OpenClaw Core Patches: Direct Message Support for Reply Listener

These patches modify the `openclaw-core` package in oh-my-openagent to support
direct (non-reply) messages from authorized Discord/Telegram users in addition
to the existing reply-based injection.

## What Changed

The reply listener currently only processes messages that are **replies** to
previous AutoDev messages (correlated via `message_reference` / `reply_to_message`).
This means a human cannot initiate a new conversation with AutoDev through Discord
— they can only reply to messages AutoDev already sent.

These patches add an `acceptDirectMessages` config option that, when enabled, also
injects new (non-reply) messages from authorized users directly into the active
AutoDev tmux session.

## Files Modified

- `types.ts` — Added `acceptDirectMessages` and `directMessageTargetPane` to `OpenClawReplyListenerConfig`
- `config.ts` — Added normalization for `acceptDirectMessages`
- `reply-listener-discord.ts` — Added direct message handling alongside reply handling
- `reply-listener-telegram.ts` — Added direct message handling alongside reply handling
- `reply-listener-injection.ts` — Added `injectDirectMessageIntoSession()` for non-correlated messages

## How to Apply

```bash
cd <path-to-oh-my-openagent>
git apply <this-directory>/*.patch
```

Or copy the modified files directly into `packages/openclaw-core/src/`.
