#!/bin/sh
# build-sandbox.sh — build the TraderBot Phase 5 sandbox image (T3, D10, R3).
#
# This is the ONLY build entry-point in the repo. The image tag is derived by
# traderbot.sandbox.sandbox_image_tag() — the module is the single source of
# truth for the D10 name:tag contract; this script must not hand-roll a tag.
#
# DOCKERFILE_SHA256 below pins the exact bytes of install/docker/Dockerfile this
# build was authored against. traderbot.deploy.sandbox_build.resolve_sandbox_dockerfile()
# re-computes this digest and FAILS CLOSED on drift, so a swapped or stubbed
# Dockerfile is detected rather than trusted.
# DOCKERFILE_SHA256=a1a6482142a45c3e017a2bb6b172719d3019f5c1f4034cb47da96565ebefaac2
set -eu

# Resolve the repo root from this script's own location
# (<repo>/install/docker/build-sandbox.sh -> <repo>).
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
cd "$REPO_ROOT"

DOCKERFILE="install/docker/Dockerfile"

if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: 'docker' is not on PATH." >&2
    echo "Remedy: install Docker (or start the Docker daemon) and re-run this script." >&2
    exit 1
fi

# Consume the tag from the module. If the import fails we FAIL loudly rather than
# silently deriving a tag here: traderbot.sandbox is required (D10). This is a
# print-then-fail path, not a fallback. sandbox_image_tag() returns the FULL
# name:tag ref ("traderbot-sandbox:d<8hex>"), so it is used verbatim below —
# never re-prefixed.
TAG=$(python3 -c "from traderbot.sandbox import sandbox_image_tag; from pathlib import Path; print(sandbox_image_tag(Path('install/docker/Dockerfile')))") || {
    echo "ERROR: could not import traderbot.sandbox.sandbox_image_tag." >&2
    echo "traderbot.sandbox is required as the single source of truth for the image tag (D10)." >&2
    echo "Remedy: install the TraderBot package (e.g. 'uv sync') and re-run from the repo root." >&2
    exit 1
}

# --pull=false forbids an implicit base-image refresh; the base is digest-pinned
# in the Dockerfile, so the build is reproducible and offline at the instruction
# level. Some docker versions spell this flag --pull=never; use that if the local
# docker rejects --pull=false.
# --network none pins the build to no network: the Dockerfile has no RUN/apt/pip
# step, so the build never needs egress (R3 / plan Must-NOT "no network access
# anywhere in container ops").
docker build --pull=false --network none -f "$DOCKERFILE" -t "$TAG" install/docker

echo "$TAG"
