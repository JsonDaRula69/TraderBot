# Workspace Template Injection

TraderBot restores allowlisted OpenClaw workspace templates through `traderbot.profiles.injection`. The module never invokes OpenClaw or creates agents.

## Template Inventories

Weather and SysAdmin contain `AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `TOOLS.md`, `HEARTBEAT.md`, `USER.md`, `SESSION-STATE.md`, and `.learnings/`. Economics, crypto, sports, politics, entertainment, financial, world, and other contain only `AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `TOOLS.md`, and `HEARTBEAT.md`.

Every category `TOOLS.md` documents the five registered MCP tools: `health`, `auth_check`, `profile_list`, `market_edge`, and `market_prices` under their `traderbot__` names. `market_edge` remains a registered stub that returns `status: stub` and does not compute edge yet. No category-specific tools are installed by these templates.

## Ownership Strategies

`FENCED_MERGE` manages `AGENTS.md`, `SOUL.md`, `IDENTITY.md`, and `TOOLS.md` between this canonical pair:

```text
<!-- BEGIN TRADERBOT MANAGED -->
<!-- END TRADERBOT MANAGED -->
```

Bytes outside that block are retained exactly. A regular file with no markers receives one appended block. Duplicate, nested, reversed, incomplete, or incompatible TraderBot markers reject the entire operation before target writes begin.

`INIT_IF_MISSING` governs `HEARTBEAT.md`, `USER.md`, `SESSION-STATE.md`, and `.learnings/` where present in an inventory. It creates absent paths and never changes existing regular files or directories.

## Safety Contract

`inject_workspace(workspace_root, template, templates_root=None)` accepts only the fixed `WorkspaceTemplate` names. All derived target names come from fixed manifests and must remain lexically beneath the selected workspace root. Every existing component above and within the selected root is inspected with `lstat`; symlinks and wrong path types are rejected before root creation and immediately before publication.

Platform path aliases are not silently canonicalized. On systems such as macOS where `/var` is a symlink to `/private/var`, callers must explicitly select the canonical, symlink-free path (for example, `/private/var/...`). This keeps the path presented for approval identical to the path that receives writes.

Writes are staged in temporary files in the target directory, flushed, synchronized, and published with `os.replace`. New files use mode `0600` and new directories use mode `0700`; replacements and rollback restore the existing file's ordinary permission bits while discarding ownership and special-bit metadata. The full manifest is preflighted before creation. A replacement failure rolls back already-published files and removes temporary files and newly created workspace paths. Successful reports include each path's action and SHA-256 plus a deterministic aggregate `manifest_hash`.
