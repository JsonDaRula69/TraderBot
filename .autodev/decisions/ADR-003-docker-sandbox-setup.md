# ADR-003: Docker sandbox included in setup

**Status:** Decided
**Date:** 2025-06-08
**Source:** v2roadmap.md DD-003
**Tags:** docker, sandbox, setup, deployment

## Context

Category agents must run in Docker sandboxes (DD-010). The Docker setup step should be part of the deploy flow, not a separate prerequisite.

## Decision

`traderbot setup` includes a Docker sandbox setup step. It checks for Docker availability, offers to install it if missing, and builds the sandbox image as part of deployment.

## Consequences

- Setup detects Docker availability via `detect_capabilities()` (DD-006)
- If Docker is not available, setup offers to install it or skip (with a warning that category agents cannot run)
- The Dockerfile lives in `install/docker/` as a build artifact
- SysAdmin does NOT run in Docker (DD-036)

## Notes for AutoDev Agents

The Docker sandbox is mandatory for category agents (DD-010). The sandbox setup is a deploy-time step, not a separate script. The base image is `python:3.12-slim-bookworm`. Bind mounts are: agent data dir (RW), workspace files (RO), TRADERBOT_PROFILE_TOKEN via SecretRef. No API tokens inside containers.
