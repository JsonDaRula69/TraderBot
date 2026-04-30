"""Auto-update checker for TraderBot — checks GitHub releases for new versions."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

import httpx
from packaging.version import InvalidVersion, Version

logger = logging.getLogger(__name__)

GITHUB_REPO = "JsonDaRula69/TraderBot"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
CACHE_DIR = Path.home() / ".traderbot"
CACHE_FILE = CACHE_DIR / ".update_check_cache.json"


def get_current_version() -> str:
    """Read current version from VERSION file (source of truth)."""
    version_file = Path(__file__).resolve().parent.parent.parent / "VERSION"
    return version_file.read_text().strip().lstrip("v")


def fetch_latest_version(timeout: float = 10.0) -> tuple[str, str] | None:
    """Fetch latest release version from GitHub API. Returns (version, html_url) or None."""
    try:
        resp = httpx.get(
            GITHUB_API_URL,
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "traderbot-update-checker"},
            timeout=timeout,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            logger.debug("GitHub API returned %s", resp.status_code)
            return None
        data = resp.json()
        tag = data.get("tag_name", "")
        url = data.get("html_url", "")
        return tag.lstrip("v"), url
    except (httpx.HTTPError, KeyError, json.JSONDecodeError) as exc:
        logger.debug("Update check failed: %s", exc)
        return None


def compare_versions(current: str, latest: str) -> bool:
    """Return True if latest > current (valid semver comparison)."""
    try:
        return Version(latest) > Version(current)
    except InvalidVersion:
        return False


def _read_cache() -> dict | None:
    """Read update check cache. Returns dict with 'ts', 'latest', 'url' or None."""
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text())
        if isinstance(data, dict) and "ts" in data:
            return data
    except (json.JSONDecodeError, ValueError, OSError):
        pass
    return None


def _write_cache(latest: str, url: str) -> None:
    """Write update check cache with current timestamp."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps({"ts": time.time(), "latest": latest, "url": url}))


def check_for_updates(force: bool = False, check_interval_hours: int = 6) -> dict | None:
    """Check if a newer version exists. Returns dict with 'current', 'latest', 'url' or None.

    Uses cache to avoid hitting GitHub API on every call. Respects check_interval_hours.
    Set force=True to bypass cache.
    """
    if os.environ.get("TRADERBOT_NO_UPDATE_CHECK") or os.environ.get("CI"):
        return None

    current = get_current_version()

    if not force:
        cache = _read_cache()
        if cache is not None:
            elapsed_hours = (time.time() - cache["ts"]) / 3600
            if elapsed_hours < check_interval_hours:
                if compare_versions(current, cache["latest"]):
                    logger.info("Update available: v%s -> v%s", current, cache["latest"])
                    return {"current": current, "latest": cache["latest"], "url": cache.get("url", "")}
                return None

    result = fetch_latest_version()
    if result is None:
        return None

    latest, url = result
    _write_cache(latest, url)

    if compare_versions(current, latest):
        logger.info("Update available: v%s -> v%s", current, latest)
        return {"current": current, "latest": latest, "url": url}

    return None


def apply_update(restart: bool = False) -> bool:
    """Apply update by running git pull + pip install. Returns True on success.

    Data preservation: all runtime data lives in ~/.traderbot/ (outside repo) and
    is never touched by git pull. The repo-local .traderbot/ dir is gitignored.
    """
    import subprocess

    repo_dir = Path(__file__).resolve().parent.parent.parent

    try:
        git_status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        if git_status.stdout.strip():
            untracked = [l.strip() for l in git_status.stdout.strip().splitlines() if not l.startswith("??")]
            if untracked:
                logger.error("Cannot update: uncommitted changes in working tree. Commit or stash first.")
                return False

        subprocess.run(["git", "pull", "origin", "main"], cwd=repo_dir, check=True, capture_output=True)
        pip_args = [sys.executable, "-m", "pip", "install", "-e", "."]
        subprocess.run(pip_args, cwd=repo_dir, check=True, capture_output=True)
        logger.info("Updated successfully to latest version")
        if restart:
            os.execv(sys.executable, [sys.executable] + sys.argv)
        return True
    except subprocess.CalledProcessError as exc:
        logger.error("Update failed: %s", exc)
        return False