# Category Agent Workspaces

Each subdirectory (economics/, politics/, sports/, crypto/, weather/) contains a prebuilt OpenClaw subagent workspace for that category.

Structure per agent:

```
<category>/
├── AGENTS.md        — Category-specific rules (markets this agent trades)
├── SOUL.md          — Agent identity, personality, principles
├── IDENTITY.md      — Prebuilt name, creature, vibe, emoji, avatar
├── TOOLS.md         — Agent-specific CLI reference and auth tiers
├── HEARTBEAT.md     — Heartbeat checklist for this agent's cadence
├── HEARTBEAT_DATA.md
├── MEMORY.md
├── SESSION-STATE.md
├── USER.md          — Copied from sysadmin workspace on agent creation
└── memory/
    └── YYYY-MM-DD.md
```

Workspace files are fully prepopulated at creation time. No BOOTSTRAP.md needed — identity is frozen. The agent knows its category, its personality, and its job from session one.
