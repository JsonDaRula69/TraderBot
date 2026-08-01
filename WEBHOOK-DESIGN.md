# AutoDev ↔ Traderbot Liaison: Webhook Design

Two systems on one machine. They need to talk to each other. Here's how.

---

## The Problem

AutoDev (OpenCode + OmO) and Traderbot (OpenClaw) are separate processes. They need to:

1. **New work**: When a Traderbot agent files an issue, the liaison must wake AutoDev to start work
2. **Validation**: When AutoDev pushes changes, it needs the Traderbot agent to validate the deployment works
3. **Completion**: When work is done, AutoDev must tell the liaison, who tells the originating Traderbot agent
4. **Blocking**: When AutoDev is stuck, the liaison must escalate to the human

GitHub is the shared source of truth — issues, PRs, labels, comments. But GitHub polling has ~30 minute latency. The webhook layer is for low-latency wake signals so work starts immediately, not 30 minutes later.

---

## How the Two Systems Actually Communicate

```
┌─────────────────────────────────────────────────────────────┐
│                        Same Machine                          │
│                                                              │
│   ┌──────────────────────┐       ┌────────────────────────┐  │
│   │   OpenClaw Gateway    │       │   OpenCode + OmO        │  │
│   │   localhost:3000       │       │   (TUI, no HTTP port)  │  │
│   │                        │       │                         │  │
│   │   ┌────────────────┐  │       │                         │  │
│   │   │  Liaison Agent  │  │       │                         │  │
│   │   │  (named agent)  │  │       │                         │  │
│   │   └───────┬────────┘  │       │                         │  │
│   │           │            │       │                         │  │
│   │   ┌───────┴────────┐  │       │                         │  │
│   │   │  /hooks/*       │◄─┼──HTTP─┤  wakeOpenClaw()        │  │
│   │   │  webhook server │  │       │  (OmO sends POST)      │  │
│   │   └────────────────┘  │       │                         │  │
│   │                        │       │                         │  │
│   └──────────┬─────────────┘       │                         │  │
│              │                      │                         │  │
│              │  Shared channel      │                         │  │
│              │  (Discord/Telegram)  │                         │  │
│              │                      │                         │  │
│              ├─────────────────────►│  Reply Listener Daemon │  │
│              │  Liaison posts here  │  (polls every 3s)      │  │
│              │                      │                         │  │
│   ┌──────────┴─────────────┐       │                         │  │
│   │                        │       │                         │  │
│   │       GitHub            │◄──────┤  Both read/write       │  │
│   │       (source of truth) │──────►│                         │  │
│   │                        │       │                         │  │
│   └────────────────────────┘       └─────────────────────────┘  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Two channels, one source of truth

| Channel | Direction | Mechanism | What it carries | Latency |
|---------|-----------|-----------|-----------------|---------|
| **Wake signal** | Either direction | See below | "Hey, check GitHub" | Seconds |
| **GitHub** | Both directions | Issues, PRs, labels, comments | All state and data | 30 min (heartbeat) |

The wake signal never carries business data. It's just a tap on the shoulder. The actual work items, status, and context all live on GitHub. This means if the wake signal is lost, nothing breaks — you just wait for the next heartbeat.

---

## Channel 1: AutoDev → Liaison (via OpenClaw webhooks)

This direction is straightforward. OpenClaw has a built-in webhook server. AutoDev sends HTTP POSTs to it.

```
AutoDev calls wakeOpenClaw()
       │
       ▼
POST http://localhost:3000/hooks/wake         ← simple wake
POST http://localhost:3000/hooks/agent          ← isolated agent turn
POST http://localhost:3000/hooks/autodev-*     ← custom mappings (richer)
       │
       ▼
OpenClaw routes to liaison agent
       │
       ▼
Liaison reads GitHub, takes action
```

### OpenClaw webhook config (in openclaw.json)

```json5
{
  hooks: {
    enabled: true,
    token: "<AUTODEV_HOOK_TOKEN>",     // dedicated token, NOT the gateway auth token
    path: "/hooks",
    allowedAgentIds: ["autodev-liaison"]
  }
}
```

### AutoDev sends to OpenClaw

OmO's `openclaw-core` has a `wakeOpenClaw()` function. It reads the gateway config from `oh-my-openagent.jsonc` and POSTs to the OpenClaw webhook endpoint:

```jsonc
// oh-my-openagent.jsonc
{
  "openclaw": {
    "enabled": true,
    "gateways": {
      "autodev-liaison": {
        "type": "http",
        "url": "http://localhost:3000/hooks/wake",
        "headers": {
          "Authorization": "Bearer ${AUTODEV_HOOK_TOKEN}"
        },
        "timeout": 10000
      }
    },
    "hooks": {
      "autodev:completed": {
        "enabled": true,
        "gateway": "autodev-liaison",
        "instruction": "AutoDev completed work. Check GitHub for details."
      },
      "autodev:blocked": {
        "enabled": true,
        "gateway": "autodev-liaison",
        "instruction": "AutoDev is blocked. Check GitHub and escalate to operator."
      },
      "autodev:deployed": {
        "enabled": true,
        "gateway": "autodev-liaison",
        "instruction": "AutoDev deployed a change. Validate Traderbot health."
      }
    }
  }
}
```

### When AutoDev sends a wake signal

The payload follows OmO's `OpenClawPayload` structure:

```json
{
  "event": "autodev:deployed",
  "instruction": "AutoDev deployed PR #43. Validate Traderbot health.",
  "text": "Deployed: PR #43 for issue #42. Please validate.",
  "timestamp": "2026-06-15T14:05:00Z",
  "context": {
    "issueNumber": "42",
    "prNumber": "43",
    "status": "deployed"
  }
}
```

OpenClaw receives this as a `/hooks/wake` event, routes it to the liaison agent, and the liaison takes action based on the event type.

### Custom hook mappings for event-specific routing

For richer routing, define custom hook paths in `openclaw.json`:

```json5
{
  hooks: {
    enabled: true,
    token: "<AUTODEV_HOOK_TOKEN>",
    path: "/hooks",
    allowedAgentIds: ["autodev-liaison"],
    mappings: [
      {
        match: { path: "autodev-completed" },
        action: "agent",
        agentId: "autodev-liaison",
        instruction: "AutoDev completed work. Check GitHub, notify the requesting Traderbot agent.",
        deliver: true
      },
      {
        match: { path: "autodev-blocked" },
        action: "agent",
        agentId: "autodev-liaison",
        instruction: "AutoDev is blocked. Check GitHub and escalate to the operator immediately.",
        deliver: true,
        channel: "telegram",
        to: "traderbot-ops"
      },
      {
        match: { path: "autodev-deployed" },
        action: "agent",
        agentId: "autodev-liaison",
        instruction: "AutoDev deployed a change. Run Traderbot health validation and report results.",
        deliver: true
      }
    ]
  }
}
```

With custom mappings, AutoDev can POST to `/hooks/autodev-deployed` and OpenClaw routes it to the liaison with the right instruction, and optionally delivers the reply to a channel.

---

## Channel 2: Liaison → AutoDev (via shared channel)

This direction is trickier. OpenCode/OmO doesn't run an HTTP server — it's a TUI. So the liaison can't POST to it directly. Instead, the liaison uses a shared Discord/Telegram channel.

```
Liaison creates GitHub issue with autodev-request label
       │
       ├────► GitHub (durable, always works)
       │
       └────► Posts message on shared Discord/Telegram channel
                    │
                    ▼
              OmO Reply Listener Daemon (polls every 3s)
                    │
                    ▼
              Injects instruction into active AutoDev session
```

### How it works

1. **Liaison creates the GitHub issue** — this is the durable record. Even if the channel message is lost, the next AutoDev heartbeat catches it.

2. **Liaison posts a wake message on the shared channel** — this is the low-latency tap. The OmO reply listener daemon polls the channel every 3 seconds and injects matching messages into the active AutoDev session.

3. **AutoDev's heartbeat (every 30 minutes)** polls GitHub for new `autodev-request` issues — this is the always-on fallback that catches anything the channel message missed.

### The shared channel message format

The liaison posts a structured message on the shared Discord/Telegram channel:

```
🤖 autodev:wake | Issue #42 | high | bug | Fix P&L settlement rounding
```

The OmO reply listener daemon is configured to watch this channel:

```jsonc
// oh-my-openagent.jsonc
{
  "openclaw": {
    "replyListener": {
      "enabled": true,
      "pollIntervalMs": 3000,
      "discordBotToken": "${AUTODEV_DISCORD_BOT_TOKEN}",
      "discordChannelId": "${AUTODEV_DISCORD_CHANNEL_ID}",
      "telegramBotToken": "${AUTODEV_TELEGRAM_BOT_TOKEN}",
      "telegramChatId": "${AUTODEV_TELEGRAM_CHAT_ID}"
    }
  }
}
```

When the daemon sees a message starting with `🤖 autodev:wake`, it injects the instruction into AutoDev's session.

---

## The Four Workflows

### 1. New Work (Traderbot → AutoDev)

```
Traderbot agent      Liaison                    GitHub               AutoDev
     │                 │                          │                     │
     │ "Need a bug     │                          │                     │
     │  fix for P&L"   │                          │                     │
     │────────────────►│                          │                     │
     │                 │ Creates issue with       │                     │
     │                 │ autodev-request label     │                     │
     │                 │──────────────────────────►│                     │
     │                 │                          │                     │
     │                 │ Posts wake message on     │                     │
     │                 │ shared channel            │                     │
     │                 │─────────────────────────────────────────────────►│
     │                 │                          │     (3s latency)    │
     │                 │                          │     AutoDev wakes   │
     │                 │                          │     and triages     │
     │                 │                          │                     │
     │                 │                          │  If channel missed: │
     │                 │                          │  heartbeat polls    │
     │                 │                          │  GitHub every 30min │
     │                 │                          │◄────────────────────│
```

### 2. Validation (AutoDev → Traderbot)

When AutoDev pushes a change and needs the Traderbot agent to validate it:

```
AutoDev             GitHub                Liaison              Traderbot agent
   │                   │                     │                      │
   │ Push changes,     │                     │                      │
   │ update labels     │                     │                      │
   │──────────────────►│                     │                      │
   │                   │                     │                      │
   │ Send wake signal  │                     │                      │
   │ (autodev:deployed)│                     │                      │
   │────────────────────────────────────────►│                      │
   │                   │                     │ Reads PR and issue   │
   │                   │                     │ on GitHub            │
   │                   │                     │                      │
   │                   │                     │ Asks Traderbot agent  │
   │                   │                     │ to validate           │
   │                   │                     │─────────────────────►│
   │                   │                     │                      │
   │                   │                     │    Traderbot agent    │
   │                   │                     │    runs health check, │
   │                   │                     │    verifies deployment│
   │                   │                     │                      │
   │                   │                     │    Validation result  │
   │                   │                     │◄─────────────────────│
   │                   │                     │                      │
   │                   │  Liaison comments   │                      │
   │                   │  validation result  │                      │
   │                   │  on the PR          │                      │
   │                   │◄────────────────────│                      │
   │                   │                     │                      │
   │  AutoDev reads    │                     │                      │
   │  validation result│                     │                      │
   │◄──────────────────│                     │                      │
```

The key insight: AutoDev doesn't directly ask Traderbot to validate. It tells the liaison, who coordinates with the right Traderbot agent. This keeps the separation clean — AutoDev never touches the live Traderbot system directly.

### 3. Completion (AutoDev → Liaison → Traderbot)

```
AutoDev             GitHub                OpenClaw              Liaison              Traderbot
   │                   │                     │                     │                      │
   │ PR merged,        │                     │                     │                      │
   │ label autodev-    │                     │                     │                      │
   │ merged            │                     │                     │                      │
   │──────────────────►│                     │                     │                      │
   │                   │                     │                     │                      │
   │ wakeOpenClaw()    │                     │                     │                      │
   │ (autodev:completed)                    │                     │                      │
   │──────────────────────────────────────────────►│              │                      │
   │                   │                     │  Liaison receives   │                      │
   │                   │                     │  wake event         │                      │
   │                   │                     │────────────────────►│                      │
   │                   │                     │                     │ Verifies on GitHub   │
   │                   │                     │                     │                      │
   │                   │                     │                     │ Notifies requesting  │
   │                   │                     │                     │ Traderbot agent      │
   │                   │                     │                     │─────────────────────►│
```

### 4. Blocking (AutoDev needs human input)

```
AutoDev             GitHub                OpenClaw              Liaison              Human
   │                   │                     │                     │                    │
   │ Stuck, needs      │                     │                     │                    │
   │ clarification     │                     │                     │                    │
   │──────────────────►│                     │                     │                    │
   │ Label:            │                     │                     │                    │
   │ autodev-blocked   │                     │                     │                    │
   │                   │                     │                     │                    │
   │ wakeOpenClaw()    │                     │                     │                    │
   │ (autodev:blocked) │                     │                     │                    │
   │──────────────────────────────────────────────►│              │                    │
   │                   │                     │  Liaison receives   │                    │
   │                   │                     │  wake event         │                    │
   │                   │                     │────────────────────►│                    │
   │                   │                     │                     │ Escalates to       │
   │                   │                     │                     │ operator           │
   │                   │                     │                     │───────────────────►│
   │                   │                     │                     │                    │
   │                   │                     │                     │  Human resolves    │
   │                   │                     │                     │◄───────────────────│
   │                   │                     │                     │                    │
   │                   │  Human comments     │                     │                    │
   │                   │  on issue, removes  │                     │                    │
   │                   │  autodev-blocked     │                     │                    │
   │                   │◄────────────────────────────────────────────│                    │
   │                   │                     │                     │                    │
   │  AutoDev sees     │                     │                     │                    │
   │  unblock on       │                     │                     │                    │
   │  heartbeat        │                     │                     │                    │
   │◄──────────────────│                     │                     │                    │
```

---

## Event Types

### AutoDev → Liaison (via `POST /hooks/wake` or `/hooks/<custom>`)

| Event | When | OpenClaw hook target | Liaison action |
|-------|------|---------------------|----------------|
| `autodev:completed` | PR merged + deployed | Wake liaison session | Verify on GitHub, notify requesting Traderbot agent |
| `autodev:blocked` | Needs human input | Agent turn with delivery | Escalate to operator on Telegram/Discord |
| `autodev:deployed` | Code deployed, needs validation | Agent turn with delivery | Ask Traderbot agent to validate, report results back |
| `autodev:review-ready` | PR ready for human review | Wake liaison session | Check if critical change, notify operator if needed |
| `autodev:deploy-failed` | Deployment health check failed | Agent turn with delivery | Alert operator, rollback may be in progress |

### Liaison → AutoDev (via shared channel message)

| Message | When | AutoDev action |
|---------|------|---------------|
| `autodev:wake` | New issue created | Triages the new issue |
| `autodev:cancel` | Work no longer needed | Stop work, close PR/issue |
| `autodev:priority` | Critical bug or security issue | Immediate triage, high priority |

The shared channel messages are short — just event type, issue number, priority, and a few words. All the detail lives on GitHub.

---

## Fallback and Reliability

The system works even when a channel is down:

| What's down | Impact | Recovery |
|-------------|--------|----------|
| **Discord/Telegram** | Liaison can't wake AutoDev instantly. AutoDev still catches new work every 30 min via heartbeat. | Fix channel credentials. AutoDev is never blocked — just delayed. |
| **OpenClaw webhook** | AutoDev can't notify liaison instantly. Liaison still sees label transitions on GitHub. | Fix webhook config. Liaison polls GitHub. |
| **GitHub** | Both systems lose coordination. AutoDev can't triage new work; liaison can't verify completions. | Both systems buffer locally and retry with exponential backoff. |
| **Liaison agent** | No wake signals from Traderbot. AutoDev still works via heartbeat. | AutoDev heartbeat detects no new issues from liaison. Human can create issues directly. |
| **OpenCode process** | No AutoDev activity. Liaison sees no PR activity. | tmux/systemd restarts OpenCode. OmO resumes from boulder state. |

**GitHub is always the source of truth.** Wake signals are acceleration, not critical path. If any channel fails, the heartbeat eventually catches everything.

---

## Config Summary

### OpenClaw (Traderbot's openclaw.json)

```json5
{
  agents: {
    list: [
      // ... existing Traderbot agents ...
      { id: "autodev-liaison", name: "AutoDev Liaison", workspace: "~/.openclaw/workspace-autodev-liaison" }
    ]
  },
  hooks: {
    enabled: true,
    token: "<AUTODEV_HOOK_TOKEN>",
    path: "/hooks",
    allowedAgentIds: ["autodev-liaison"],
    mappings: [
      {
        match: { path: "autodev-completed" },
        action: "agent",
        agentId: "autodev-liaison",
        instruction: "AutoDev completed work. Verify on GitHub, then notify the requesting Traderbot agent.",
        deliver: true
      },
      {
        match: { path: "autodev-blocked" },
        action: "agent",
        agentId: "autodev-liaison",
        instruction: "AutoDev is blocked and needs human input. Escalate to the operator immediately.",
        deliver: true,
        channel: "telegram",
        to: "traderbot-ops"
      },
      {
        match: { path: "autodev-deployed" },
        action: "agent",
        agentId: "autodev-liaison",
        instruction: "AutoDev deployed a change. Ask the relevant Traderbot agent to validate health.",
        deliver: true
      }
    ]
  }
}
```

### OmO (oh-my-openagent.jsonc)

```jsonc
{
  "openclaw": {
    "enabled": true,
    "gateways": {
      "autodev-liaison": {
        "type": "http",
        "url": "http://localhost:3000/hooks/wake",
        "headers": { "Authorization": "Bearer ${AUTODEV_HOOK_TOKEN}" },
        "timeout": 10000
      }
    },
    "hooks": {
      "autodev:completed": {
        "enabled": true,
        "gateway": "autodev-liaison",
        "instruction": "AutoDev completed work. Check GitHub for details."
      },
      "autodev:blocked": {
        "enabled": true,
        "gateway": "autodev-liaison",
        "instruction": "AutoDev is blocked. Check GitHub and escalate to operator."
      },
      "autodev:deployed": {
        "enabled": true,
        "gateway": "autodev-liaison",
        "instruction": "AutoDev deployed a change. Validate Traderbot health."
      }
    },
    "replyListener": {
      "enabled": true,
      "pollIntervalMs": 3000,
      "discordBotToken": "${AUTODEV_DISCORD_BOT_TOKEN}",
      "discordChannelId": "${AUTODEV_DISCORD_CHANNEL_ID}"
    }
  }
}
```

### Environment Variables

```bash
AUTODEV_HOOK_TOKEN=<dedicated-token>        # Not the gateway auth token
AUTODEV_DISCORD_BOT_TOKEN=<bot-token>        # For OmO reply listener
AUTODEV_DISCORD_CHANNEL_ID=<channel-id>      # Shared AutoDev/Liaison channel
GITHUB_TOKEN=<token>                          # Both systems need repo access
GITHUB_REPOSITORY=<owner/repo>                # Shared repo
```

---

## Testing

```bash
# 1. AutoDev → OpenClaw: Send a wake signal
curl -X POST http://localhost:3000/hooks/wake \
  -H "Authorization: Bearer $AUTODEV_HOOK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"AutoDev pipeline test","mode":"now"}'

# 2. AutoDev → OpenClaw: Send a custom hook (autodev-deployed)
curl -X POST http://localhost:3000/hooks/autodev-deployed \
  -H "Authorization: Bearer $AUTODEV_HOOK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"Test: PR #1 deployed","context":{"issueNumber":"1","prNumber":"1","status":"test"}}'

# 3. Liaison → AutoDev: Post on shared Discord channel
#    Message format: 🤖 autodev:wake | Issue #1 | medium | feature | Test wake signal

# 4. Verify GitHub coordination
gh issue list --label "autodev-request" --state open
```
