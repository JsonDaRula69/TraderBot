"""Auto-update checker for TraderBot — checks GitHub tags for new versions."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

import httpx
from packaging.version import InvalidVersion, Version

from traderbot.paths import get_data_dir

logger = logging.getLogger(__name__)

GITHUB_REPO = "JsonDaRula69/TraderBot"
GITHUB_TAGS_URL = f"https://api.github.com/repos/{GITHUB_REPO}/tags"
GITHUB_DEV_BRANCH_URL = f"https://api.github.com/repos/{GITHUB_REPO}/branches/dev"
CACHE_DIR = get_data_dir()
CACHE_FILE = CACHE_DIR / ".update_check_cache.json"


def get_current_version() -> str:
    """Read current version from VERSION file (source of truth)."""
    version_file = Path(__file__).resolve().parent.parent.parent / "VERSION"
    return version_file.read_text().strip().lstrip("v")


def fetch_latest_version(timeout: float = 10.0, dev: bool = False) -> tuple[str, str] | None:
    """Fetch latest version from GitHub. Returns (version, html_url) or None.

    Args:
        timeout: HTTP request timeout in seconds.
        dev: If True, check the dev branch commit instead of latest tag.
    """
    try:
        if dev:
            url = GITHUB_DEV_BRANCH_URL
            resp = httpx.get(
                url,
                headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "traderbot-update-checker"},
                timeout=timeout,
                follow_redirects=True,
            )
            if resp.status_code != 200:
                logger.debug("GitHub API returned %s", resp.status_code)
                return None
            data = resp.json()
            commit = data.get("commit", {})
            sha = commit.get("sha", "")[:8]
            branch_url = f"https://github.com/{GITHUB_REPO}/tree/dev"
            return f"dev-{sha}", branch_url
        resp = httpx.get(
            GITHUB_TAGS_URL,
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "traderbot-update-checker"},
            timeout=timeout,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            logger.debug("GitHub API returned %s", resp.status_code)
            return None
        tags = resp.json()
        if not isinstance(tags, list) or not tags:
            logger.debug("No tags found")
            return None
        latest_tag = tags[0]
        tag_name = latest_tag.get("name", "").lstrip("v")
        tag_url = latest_tag.get("html_url", f"https://github.com/{GITHUB_REPO}/releases/tag/{latest_tag.get('name', '')}")
        return tag_name, tag_url
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


def check_for_updates(force: bool = False, check_interval_minutes: int = 30, dev: bool = False) -> dict | None:
    """Check if a newer version exists. Returns dict with 'current', 'latest', 'url' or None.

    Uses cache to avoid hitting GitHub API on every call. Respects check_interval_minutes.
    Set force=True to bypass cache. Set dev=True to check dev branch.
    """
    if os.environ.get("TRADERBOT_NO_UPDATE_CHECK") or os.environ.get("CI"):
        return None

    current = get_current_version()

    if not force and not dev:
        cache = _read_cache()
        if cache is not None:
            elapsed_minutes = (time.time() - cache["ts"]) / 60
            if elapsed_minutes < check_interval_minutes:
                if compare_versions(current, cache["latest"]):
                    logger.info("Update available: v%s -> v%s", current, cache["latest"])
                    return {"current": current, "latest": cache["latest"], "url": cache.get("url", "")}
                return None

    result = fetch_latest_version(dev=dev)
    if result is None:
        return None

    latest, url = result
    if not dev:
        _write_cache(latest, url)

    if dev or compare_versions(current, latest):
        logger.info("Update available: v%s -> v%s", current, latest)
        return {"current": current, "latest": latest, "url": url}

    return None


def apply_update(restart: bool = False, dev: bool = False) -> bool:
    """Apply update by running git pull + pip install. Returns True on success.

    Data preservation: all runtime data lives in ~/.traderbot/ (outside repo) and
    is never touched by git pull. The repo-local .traderbot/ dir is gitignored.

    Args:
        restart: Restart the process after update.
        dev: Pull from dev branch instead of main.
    """
    import subprocess

    repo_dir = Path(__file__).resolve().parent.parent.parent
    branch = "dev" if dev else "main"

    try:
        if not (repo_dir / ".git").exists():
            logger.error("Cannot update: not a git repository (installed via ZIP?). Reinstall with: curl -fsSL https://raw.githubusercontent.com/JsonDaRula69/TraderBot/main/install/traderbot-installer.sh -o /tmp/traderbot-installer.sh && bash /tmp/traderbot-installer.sh")
            return False

        git_status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        if git_status.stdout.strip():
            untracked = [line.strip() for line in git_status.stdout.strip().splitlines() if not line.startswith("??")]
            if untracked:
                logger.error("Cannot update: uncommitted changes in working tree. Commit or stash first.")
                return False

        subprocess.run(["git", "pull", "origin", branch], cwd=repo_dir, check=True, capture_output=True)
        pip_args = [sys.executable, "-m", "pip", "install", "-e", "."]
        subprocess.run(pip_args, cwd=repo_dir, check=True, capture_output=True)
        logger.info("Updated successfully from %s branch", branch)
        if restart:
            os.execv(sys.executable, [sys.executable, *sys.argv])
        return True
    except subprocess.CalledProcessError as exc:
        logger.error("Update failed: %s", exc)
        return False
