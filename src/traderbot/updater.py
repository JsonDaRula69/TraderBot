"""Auto-update checker for TraderBot — checks GitHub tags for new versions."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from packaging.version import InvalidVersion, Version

from traderbot.paths import get_data_dir

logger = logging.getLogger(__name__)

CACHE_DIR = get_data_dir()

OPENCLAW_PUBLIC_KEY = b""
try:
    key_path = Path(__file__).resolve().parent / "release.pub"
    if key_path.exists():
        OPENCLAW_PUBLIC_KEY = Ed25519PublicKey.from_public_bytes(key_path.read_bytes())
except Exception:
    OPENCLAW_PUBLIC_KEY = b""

GITHUB_REPO = "JsonDaRula69/TraderBot"


def fetch_latest_version() -> tuple[str, str] | None:
    """Check GitHub for the latest release tag and its archive URL."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        resp = httpx.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        tag = data.get("tag_name", "")
        if not tag or not tag.startswith("v"):
            return None
        return tag.lstrip("v"), data.get("zipball_url", "")
    except Exception as exc:
        logger.warning("Failed to fetch latest version: %s", exc)
        return None

