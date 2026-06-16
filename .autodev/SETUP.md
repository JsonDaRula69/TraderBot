# AutoDev Setup Guide

Step-by-step instructions to deploy the AutoDev team framework.

## Prerequisites

- macOS or Linux machine (your existing Traderbot deployment machine)
- [Bun](https://bun.sh) >= 1.0
- [OpenCode](https://opencode.ai) installed
- [gh](https://cli.github.com) CLI authenticated (`gh auth status`)
- Git
- tmux (for team mode visualization)
- Ollama Cloud access with: GLM 5.1, Deepseek V4 Pro, Deepseek V4 Flash

## Quick Setup

```bash
cd /path/to/Auto-Dev-Traderbot
bash .autodev/scripts/setup.sh
```

This single script installs and configures everything. See below for manual steps if you need more control.

## Manual Setup

### 1. Install oh-my-openagent

```bash
bunx oh-my-openagent install --platform=opencode
```

Follow the TUI prompts. When asked about model subscriptions, skip — you'll configure Ollama Cloud manually.

### 2. Configure model auth for Ollama Cloud

Add your Ollama Cloud provider configuration to `~/.config/opencode/oh-my-openagent.jsonc` or the project-level config:

```jsonc
{
  "providers": {
    "ollama-cloud": {
      "api": "openai-compat",
      "baseUrl": "https://<your-ollama-cloud-endpoint>/v1",
      "apiKey": "<your-api-key>"
    }
  }
}
```

### 3. Copy AutoDev config

The OmO config is at `.autodev/config/oh-my-openagent.jsonc`. Merge its contents into your OpenCode config, or copy it as the project-level config:

```bash
# Project-level (recommended — scoped to Traderbot repo)
cp .autodev/config/oh-my-openagent.jsonc <traderbot-repo>/.opencode/oh-my-openagent.jsonc

# Or user-level (affects all projects)
cp .autodev/config/oh-my-openagent.jsonc ~/.config/opencode/oh-my-openagent.jsonc
```

### 4. Install Magic Context

```bash
npx @cortexkit/magic-context@latest setup --harness opencode
```

Then merge the AutoDev Magic Context config:

```bash
# Project-level
cp .autodev/config/magic-context.jsonc <traderbot-repo>/magic-context.jsonc
```

### 5. Install Loreguard

```bash
npm i -g loreguard-mcp
cd <traderbot-repo>
loreguard init
```

### 6. Configure MCP servers

Copy `.autodev/config/mcp.json` to the project root or merge into existing `.mcp.json`:

```bash
cat .autodev/config/mcp.json >> <traderbot-repo>/.mcp.json
```

### 7. Set up GitHub labels

```bash
cd <traderbot-repo>
bash .autodev/scripts/setup-github-labels.sh
```

### 8. Copy GitHub issue/PR templates

```bash
cp .autodev/templates/autodev-request.md <traderbot-repo>/.github/ISSUE_TEMPLATE/
```

### 9. Seed knowledge base

When Traderbot design decisions are ready:

```bash
# Place ADRs in .autodev/decisions/
# Then import into Loreguard:
bash .autodev/scripts/seed-loreguard.sh
# Then ratify:
loreguard review
```

### 10. Configure the liaison bridge

When the OpenClaw gateway is ready:

1. Add the liaison agent to the OpenClaw gateway config (`openclaw.json`):
   ```json5
   {
     "agents": {
       "list": [
         // ... existing traderbot agents ...
         { "id": "autodev-liaison", "workspace": "~/.openclaw/workspace-autodev-liaison" }
       ]
     }
   }
   ```

2. Create the liaison workspace and bootstrap files:
   ```bash
   mkdir -p ~/.openclaw/workspace-autodev-liaison
   # Copy AGENTS.md with liaison-specific instructions
   ```

3. Update the webhook URL in `.autodev/config/oh-my-openagent.jsonc`:
   ```jsonc
   "openclaw": {
     "gateways": {
       "autodev-liaison": {
         "url": "http://localhost:<gateway-port>/webhook/autodev"
       }
     }
   }
   ```

4. Configure Discord/Telegram tokens for the reply listener (if using that bridge)

### 11. Verify

```bash
# OmO health check
bunx oh-my-openagent doctor

# Magic Context health check
npx @cortexkit/magic-context@latest doctor --harness opencode

# Loreguard health check
loreguard doctor

# Open the Traderbot repo in OpenCode
cd <traderbot-repo>
opencode
# Type: ultrawork
```

## Running the Team

### Start a session

```bash
cd <traderbot-repo>
opencode
# Type: /start-work    (resumes from boulder state if work exists)
# Or:   ultrawork       (autonomous mode)
```

### Trigger work from Traderbot

The liaison agent files a GitHub issue with `autodev-request` label and sends a webhook wake signal. AutoDev picks it up on the next heartbeat or immediately if the webhook fires.

### Trigger work manually

```bash
# File an issue directly
gh issue create --title "Fix P&L rounding" --label "autodev-request"

# Or in an OpenCode session, type:
ultrawork fix the P&L rounding error
```

### End-to-end test

```bash
bash .autodev/scripts/test-e2e.sh
```

## File Map

```
.autodev/
├── ARCHITECTURE.md              # System architecture
├── KNOWLEDGE-ARCHITECTURE.md    # Knowledge/memory design
├── AUDITOR.md                   # Health check procedures
├── HEARTBEAT.md                 # Periodic wake-up checks
├── SETUP.md                     # This guide
├── config/
│   ├── oh-my-openagent.jsonc    # OmO team config + model routing
│   ├── magic-context.jsonc      # Magic Context working memory config
│   ├── mcp.json                 # MCP server registration
│   ├── team-spec.json           # Team Mode member definitions
│   └── standing-orders.md      # Behavioral rules
├── skills/
│   ├── autodev-triage/SKILL.md  # Issue triage entry point
│   ├── autodev-implement/SKILL.md  # Implementation + evidence QA
│   ├── autodev-review/SKILL.md  # Automated PR review
│   └── autodev-deploy/SKILL.md  # Post-merge deployment
├── scripts/
│   ├── setup.sh                 # One-shot framework installer
│   ├── setup-github-labels.sh  # Create GitHub labels
│   ├── seed-loreguard.sh        # Preload decisions into Loreguard
│   └── test-e2e.sh              # End-to-end pipeline test
├── templates/
│   ├── autodev-request.md       # GitHub issue template
│   ├── autodev-delivery.md      # PR description template
│   └── ADR-template.md          # Architecture Decision Record template
├── memory/
│   ├── projectbrief.md          # What Traderbot is
│   ├── techContext.md           # Technologies, APIs
│   └── activeContext.md         # Current work focus
├── decisions/                   # ADRs (seeded into Loreguard)
├── plans/                       # Implementation plans
├── evidence/                    # QA evidence per change
├── reference/                   # On-demand technical docs
│   ├── system-architecture.md
│   ├── kalshi/
│   ├── openclaw/
│   ├── dependencies/
│   └── operations/
└── .github/
    ├── labels/                   # Label definitions
    └── workflows/               # CI workflows (when ready)
```
