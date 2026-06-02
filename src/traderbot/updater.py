"""Auto-update checker for TraderBot — delegates to standalone bootstrap script."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time as _time
from pathlib import Path

import httpx
from packaging.version import InvalidVersion, Version

from traderbot.paths import get_data_dir

logger = logging.getLogger(__name__)
CACHE_DIR = get_data_dir()
GITHUB_REPO = "JsonDaRula69/TraderBot"


def _version_tuple(version_str: str) -> tuple[int, ...]:
    try:
        return Version(version_str).release
    except InvalidVersion:
        return (0, 0, 0)


def get_current_version() -> str:
    repo_dir = Path(__file__).resolve().parent.parent.parent
    version_file = repo_dir / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip().lstrip("v")
    try:
        from importlib.metadata import version
        return version("traderbot").lstrip("v")
    except Exception:
        return "0.0.0"


def fetch_latest_version(cache_ttl_seconds: int = 3600) -> tuple[str, str] | None:
    """Fetch latest release version from GitHub, cached locally to avoid 403 rate limits.

    Caches the result to ``CACHE_DIR / .update_cache.json`` for *cache_ttl_seconds*
    (default 1 hour). Subsequent calls within the TTL return the cached value
    without hitting the GitHub API — preventing unauthenticated rate-limit
    exhaustion (60 req/hour per IP).
    """
    cache_path = CACHE_DIR / ".update_cache.json"
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text())
            age = _time.time() - cached.get("ts", 0)
            if age < cache_ttl_seconds and "tag" in cached and "url" in cached:
                return cached["tag"], cached["url"]
        except Exception:
            pass

    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        resp = httpx.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        tag = data.get("tag_name", "")
        if not tag or not tag.startswith("v"):
            return None
        result = (tag.lstrip("v"), data.get("zipball_url", ""))
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({"tag": result[0], "url": result[1], "ts": _time.time()}))
            cache_path.chmod(0o600)
        except Exception:
            pass
        return result
    except Exception as exc:
        is_403 = "403" in str(exc)
        if is_403 and cache_path.exists():
            try:
                stale = json.loads(cache_path.read_text())
                if "tag" in stale and "url" in stale:
                    logger.warning("GitHub API rate limited — using cached version info")
                    return stale["tag"], stale["url"]
            except Exception:
                pass
        # Rate-limited with no cache yet: seed from local VERSION so subsequent
        # callers within the TTL skip the API entirely.
        if is_403:
            current = get_current_version()
            try:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(
                    json.dumps({"tag": current, "url": "", "ts": _time.time()})
                )
                cache_path.chmod(0o600)
            except Exception:
                pass
            return (current, "")
        logger.warning("Failed to fetch latest version: %s", exc)
        return None


def check_for_updates(
    silent: bool = False,
    force: bool = False,
    check_interval_minutes: int | None = None,
    dev: bool = False,
) -> dict | None:
    """Check for newer releases, respecting configured interval and rate-limit cache.

    Loads ``UpdateConfig`` internally. Respects *check_interval_minutes* by
    tracking the last-check time in an interval marker file — subsequent calls
    within the interval return ``None`` (no-op) unless *force* is ``True``.

    The actual version fetch itself is cached (``fetch_latest_version``) with a TTL
    equal to *check_interval_minutes*, so the GitHub API is hit at most once per
    interval regardless of how many callers fire.
    """
    from traderbot.update_config import UpdateConfig

    config = UpdateConfig.load()
    if not config.enabled and not force:
        return None

    interval_minutes = check_interval_minutes if check_interval_minutes is not None else config.check_interval_minutes

    # Interval guard: skip if we checked recently (unless forced)
    interval_marker = CACHE_DIR / ".update_check_ts"
    if not force and interval_marker.exists():
        try:
            last_check = float(interval_marker.read_text().strip())
            if _time.time() - last_check < interval_minutes * 60:
                return None
        except Exception:
            pass

    current = get_current_version().lstrip("v")
    latest = fetch_latest_version(cache_ttl_seconds=interval_minutes * 60)
    if latest is None:
        return None

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        interval_marker.write_text(str(_time.time()))
    except Exception:
        pass

    latest_ver, url = latest
    if _version_tuple(latest_ver) > _version_tuple(current) or force:
        if not silent:
            print(f"Update available: v{current} → v{latest_ver}. Run 'traderbot update' to update.")
        result: dict = {"current": current, "latest": latest_ver, "url": url}

        if config.auto_apply and not silent:
            if apply_update(dev=dev):
                logger.info("Auto-update applied: v%s → v%s", current, latest_ver)
            else:
                logger.warning("Auto-update failed: v%s → v%s", current, latest_ver)
        return result
    return None


def apply_update(restart: bool = False, dev: bool = False, verify_signature: bool = True) -> bool:
    repo_dir = Path(__file__).resolve().parent.parent.parent
    bootstrap = repo_dir / "install" / "traderbot-update.py"
    if not bootstrap.exists():
        logger.error("Bootstrap script not found at %s", bootstrap)
        return False
    flag = "--dev" if dev else ""
    try:
        result = subprocess.run([sys.executable, str(bootstrap), flag], timeout=600)
        if result.returncode != 0:
            logger.error("Bootstrap update failed with exit code %d", result.returncode)
            return False
    except Exception as exc:
        logger.error("Bootstrap update failed: %s", exc)
        return False
    logger.info("Update applied successfully")
    if restart:
        os.execv(sys.executable, [sys.executable, *sys.argv])
    return True