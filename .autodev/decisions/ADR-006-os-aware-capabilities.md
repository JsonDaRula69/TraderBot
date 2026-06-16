# ADR-006: OS-aware capability detection

**Status:** Decided (implementation pending)
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-006
**Tags:** setup, cross-platform, os-detection

## Context

TraderBot runs on macOS, Windows, and Linux (including headless). Setup prompts and steps must adapt to the detected OS.

## Decision

`traderbot deploy` detects OS capabilities upfront and adjusts prompts and messaging accordingly. No keyring questions on headless Linux. No macOS-specific prompts on Windows. Docker sandbox step skipped if Docker is not installed.

## Consequences

- Need a `detect_capabilities()` function returning: keyring_available, docker_available, service_manager (systemd/launchd/task_scheduler/none), display_available, openclaw_installed
- Setup steps conditionally included/excluded based on detected capabilities
- User sees messages relevant to their OS, not generic ones

## Notes for AutoDev Agents

When implementing platform-specific code: use `sys.platform` for broad detection and `shutil.which()` for tool availability. Infisical runs on all platforms including headless Linux (DD-037). The `keyring` module is not available on headless Linux — do not prompt for it there.
