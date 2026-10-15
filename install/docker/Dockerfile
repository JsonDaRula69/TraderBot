# traderbot-sandbox — Phase 5 containment base image (T3, D10, R3).
#
# Digest provenance: the pin below is the Docker Hub registry manifest-list
# (OCI image index) digest for library/python:3.12-slim-bookworm, retrieved
# 2026-10-15 through the registry token-auth manifests endpoint at
# https://registry-1.docker.io/v2/library/python/manifests/3.12-slim-bookworm
# with Accept: application/vnd.oci.image.index.v1+json. The multi-arch index
# digest stays valid on every target architecture; the target host is linux.
#
# Pinning method: the digest is embedded in the FROM reference so the base
# resolves by content, never by a mutable tag. Re-pin deliberately only when the
# base image is intentionally upgraded. Recorded in
# .omo/evidence/phase5-t3-image-review.txt.
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

# OCI image metadata labels.
LABEL org.opencontainers.image.source="https://github.com/JsonDaRula69/TraderBot"
LABEL org.opencontainers.image.title="traderbot-sandbox"
LABEL phase="5"

# Network-free by design (R3): no package installs, no build-time downloads, and
# no shell commands execute during the build. TraderBot is never packaged inside
# the container (IS-7); agents reach TraderBot over the gateway MCP transport.
#
# No ENTRYPOINT/CMD is defined: OpenClaw supplies the container command at spawn
# time, so baking one here would only conflict with the gateway contract.

# Non-root runtime identity required by the sandbox contract (D1).
USER 1000:1000

# WORKDIR is inert: OpenClaw bind-mounts the real workspace at /workspace and the
# agent data dir at /data. /unused exists only to give the image a defined cwd.
WORKDIR /unused
