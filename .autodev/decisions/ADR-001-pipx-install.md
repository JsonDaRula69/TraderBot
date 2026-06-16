# ADR-001: pipx as sole installation method

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-001
**Tags:** installation, deployment, pipx, architecture

## Context

TraderBot needs a reliable, reproducible installation method. Previous approaches included installer scripts, manual venv setup, and plain pip, which created dependency drift and support issues.

## Decision

pipx is the sole installation method. No installer script, no manual venv, no plain pip. `pipx install traderbot` is the only supported path.

## Consequences

- Simpler installation, fewer support issues
- pipx handles venv isolation automatically
- pyproject.toml is the single source of truth for dependencies
- Users without pipx must install it first (documented prerequisite)
- `traderbot deploy` (not `bootstrap`) is the first-time configuration command

## Notes for AutoDev Agents

When implementing installation logic: the `deploy` command assumes pipx installation. No fallback install methods. OS detection adjusts prompts but not the install method itself (DD-006). The `install/` directory is retired except for Docker-related files (DD-007).
