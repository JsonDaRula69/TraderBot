"""Auto-update checker for TraderBot — checks GitHub tags for new versions."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from packaging.version import InvalidVersion, Version

from traderbot.paths import get_data_dir

logger = logging.getLogger(__name__)

GITHUB_REPO = "JsonDaRula69/TraderBot"
GITHUB_TAGS_URL = f"https://api.github.com/repos/{GITHUB_REPO}/tags"
GITHUB_DEV_BRANCH_URL = f"https://api.github.com/repos/{GITHUB_REPO}/branches/dev"
GITHUB_RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
PUBKEY_PATH = os.environ.get(
    "TRADERBOT_UPDATE_PUBKEY_PATH",
    str(Path(__file__).resolve().parent / "update_pubkey.pem"),
)
CACHE_DIR = get_data_dir()
CACHE_FILE = CACHE_DIR / ".update_check_cache.json"


class SignatureVerificationError(Exception):
    """Ed25519 signature verification failed for a release asset."""


def _load_update_public_key() -> Ed25519PublicKey:
    """Load the Ed25519 public key for release verification."""
    path = Path(PUBKEY_PATH)
    if path.exists():
        return Ed25519PublicKey.from_public_bytes(path.read_bytes().strip())

    # Hardcoded key — replaced by maintainer before release.
    hardcoded = os.environ.get("TRADERBOT_UPDATE_PUBKEY_B64")
    if hardcoded:
        import base64
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(hardcoded))

    raise SignatureVerificationError(
        "No Ed25519 update verification key found. "
        "Set TRADERBOT_UPDATE_PUBKEY_PATH or TRADERBOT_UPDATE_PUBKEY_B64."
    )


def get_current_version() -> str:
    """Read current version from VERSION file (source of truth)."""
    version_file = Path(__file__).resolve().parent.parent.parent / "VERSION"
    return version_file.read_text().strip().lstrip("v")


def fetch_latest_version(timeout: float = 10.0, dev: bool = False) -> tuple[str, str] | None:
    """Fetch latest version from GitHub. Returns (version, html_url) or None."""
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
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps({"ts": time.time(), "latest": latest, "url": url}))


def check_for_updates(force: bool = False, check_interval_minutes: int = 30, dev: bool = False) -> dict | None:
    """Check if a newer version exists. Returns dict with 'current', 'latest', 'url' or None."""
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
                if compare_versions(cache["latest"], current):
                    return None
                # cached latest < current — cache is stale (likely manually updated),
                # fall through to fetch and refresh.

    result = fetch_latest_version(dev=dev)
    if result is None:
        # Failed to fetch the latest version info (e.g. no network).
        # Check if origin/main has newer commits than local HEAD.
        try:
            import subprocess

            repo_dir = Path(__file__).resolve().parent.parent.parent
            if (repo_dir / ".git").exists():
                local_sha = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=repo_dir, capture_output=True, text=True, timeout=5,
                ).stdout.strip()
                remote_sha = subprocess.run(
                    ["git", "ls-remote", "origin", "refs/heads/main"],
                    cwd=repo_dir, capture_output=True, text=True, timeout=15,
                ).stdout.strip().split()[0] if not dev else None
                dev_sha = subprocess.run(
                    ["git", "ls-remote", "origin", "refs/heads/dev"],
                    cwd=repo_dir, capture_output=True, text=True, timeout=15,
                ).stdout.strip().split()[0] if dev else None
                upstream_sha = dev_sha if dev else remote_sha
                if upstream_sha and local_sha != upstream_sha:
                    branch = "dev" if dev else "main"
                    remote_url = f"https://github.com/{GITHUB_REPO}/tree/{branch}"
                    logger.info("Update available: local %s != origin/%s HEAD", local_sha[:8], branch)
                    return {"current": current, "latest": current, "url": remote_url}
        except Exception as exc:
            logger.debug("Git-based update check failed: %s", exc)
        return None

    latest, url = result
    if not dev:
        _write_cache(latest, url)

    if dev or compare_versions(current, latest):
        logger.info("Update available: v%s -> v%s", current, latest)
        return {"current": current, "latest": latest, "url": url}

    return None


def verify_release_signature(tag: str, signature_b64: str) -> bool:
    """Verify an Ed25519 detached signature over a release tag."""
    try:
        pubkey = _load_update_public_key()
    except SignatureVerificationError:
        logger.warning("Cannot verify release signature: no public key configured")
        return False

    import base64

    try:
        sig_bytes = base64.b64decode(signature_b64)
    except Exception:
        logger.debug("Signature base64 decode failed")
        return False

    try:
        pubkey.verify(sig_bytes, tag.encode())
        return True
    except InvalidSignature:
        logger.warning("Release signature verification FAILED for tag %s", tag)
        return False


def _fetch_release_signature(tag_name: str, timeout: float = 10.0) -> str | None:
    """Fetch the Ed25519 signature from a GitHub release body."""
    try:
        url = f"{GITHUB_RELEASES_URL}/tags/{tag_name}"
        resp = httpx.get(
            url,
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "traderbot-update-checker"},
            timeout=timeout,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            logger.debug("Failed to fetch release for %s: HTTP %s", tag_name, resp.status_code)
            return None
        body = resp.json().get("body", "")
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("Ed25519-Signature:"):
                return line.split(":", 1)[1].strip()
        logger.debug("No Ed25519-Signature found in release body for %s", tag_name)
        return None
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
        logger.debug("Failed to fetch release signature: %s", exc)
        return None


def apply_update(restart: bool = False, dev: bool = False, verify_signature: bool = True) -> bool:
    """Apply update by running git pull + pip install. Returns True on success.

    Post-update steps: refresh workspace files, rebuild Docker sandbox image,
    re-configure OpenClaw sandbox settings, re-register cron jobs, restart gateway.
    """
    import subprocess

    repo_dir = Path(__file__).resolve().parent.parent.parent
    branch = "dev" if dev else "main"

    try:
        if not (repo_dir / ".git").exists():
            logger.error("Cannot update: not a git repository (installed via ZIP?). Reinstall with: curl -fsSL https://raw.githubusercontent.com/JsonDaRula69/TraderBot/main/install/traderbot-installer.sh -o /tmp/traderbot-installer.sh && bash /tmp/traderbot-installer.sh")
            return False

        if verify_signature and not dev:
            latest_result = fetch_latest_version()
            if latest_result is not None:
                tag_ver, _ = latest_result
                tag_name = f"v{tag_ver}"
                sig = _fetch_release_signature(tag_name)
                if sig is not None and not verify_release_signature(tag_name, sig):
                    logger.error("Update aborted: Ed25519 signature verification failed")
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
                logger.info("Uncommitted changes detected, auto-stashing before update")
                subprocess.run(
                    ["git", "stash", "--include-untracked"],
                    cwd=repo_dir,
                    capture_output=True,
                    timeout=30,
                )

        subprocess.run(["git", "pull", "origin", branch], cwd=repo_dir, check=True, capture_output=True)
        pip_args = [sys.executable, "-m", "pip", "install", "-e", "."]
        subprocess.run(pip_args, cwd=repo_dir, check=True, capture_output=True)
        logger.info("Updated successfully from %s branch", branch)

        # Refresh agent workspace files (replace templates, preserve user data)
        _refresh_workspace_files(repo_dir)

        # Rebuild Docker sandbox image if Docker is available
        _rebuild_sandbox_image(repo_dir)

        # Re-apply OpenClaw sandbox config (binds, allow external sources, etc.)
        _configure_openclaw_sandbox()

        # Deploy or refresh bootstrap hook
        _enable_bootstrap_hook()

        # Re-register cron jobs for all deployed agents
        _reregister_cron_jobs(repo_dir)

        # systemd restart can take 30s+; non-blocking so a slow
        # restart doesn't abort the update command.
        try:
            subprocess.Popen(
                ["openclaw", "gateway", "restart"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            logger.info("OpenClaw gateway restart issued")
        except Exception as exc:
            logger.warning("Failed to issue gateway restart: %s", exc)

        if restart:
            os.execv(sys.executable, [sys.executable, *sys.argv])
        return True
    except subprocess.CalledProcessError as exc:
        logger.error("Update failed: %s", exc)
        return False


def _rebuild_sandbox_image(repo_dir: Path) -> None:
    """Rebuild the Docker sandbox image if Docker is available."""
    build_script = repo_dir / "install" / "docker" / "build-sandbox.sh"
    if not build_script.exists():
        logger.debug("Sandbox build script not found at %s, skipping rebuild", build_script)
        return
    try:
        import subprocess
        subprocess.run(["bash", str(build_script)], capture_output=True, timeout=300)
        logger.info("Docker sandbox image rebuilt")
    except Exception as exc:
        logger.warning("Sandbox image rebuild failed (Docker may not be available): %s", exc)


def _configure_openclaw_sandbox() -> None:
    """Re-apply OpenClaw sandbox config keys that the installer sets."""
    import subprocess
    import os

    try:
        subprocess.run(
            ["openclaw", "config", "set", "agents.defaults.sandbox.mode", "non-main"],
            capture_output=True, timeout=15,
        )
        subprocess.run(
            ["openclaw", "config", "set", "agents.defaults.sandbox.backend", "docker"],
            capture_output=True, timeout=15,
        )
        subprocess.run(
            ["openclaw", "config", "set", "agents.defaults.sandbox.scope", "agent"],
            capture_output=True, timeout=15,
        )
        subprocess.run(
            ["openclaw", "config", "set", "agents.defaults.sandbox.workspaceAccess", "rw"],
            capture_output=True, timeout=15,
        )
        subprocess.run(
            ["openclaw", "config", "set", "agents.defaults.sandbox.docker.image", "traderbot-sandbox:bookworm-slim"],
            capture_output=True, timeout=15,
        )
        subprocess.run(
            ["openclaw", "config", "set", "agents.defaults.sandbox.docker.network", "bridge"],
            capture_output=True, timeout=15,
        )
        subprocess.run(
            ["openclaw", "config", "set", "agents.defaults.sandbox.docker.readOnlyRoot", "true"],
            capture_output=True, timeout=15,
        )
        subprocess.run(
            ["openclaw", "config", "set", "agents.defaults.sandbox.docker.capDrop", '["ALL"]'],
            capture_output=True, timeout=15,
        )
        subprocess.run(
            ["openclaw", "config", "set", "agents.defaults.sandbox.docker.memory", "1g"],
            capture_output=True, timeout=15,
        )
        subprocess.run(
            ["openclaw", "config", "set", "agents.defaults.sandbox.docker.dangerouslyAllowExternalBindSources", "true"],
            capture_output=True, timeout=15,
        )
        home = os.environ.get("HOME", "/root")
        subprocess.run(
            [
                "openclaw", "config", "set",
                "agents.defaults.sandbox.docker.binds",
                f'["{home}/traderbot:/traderbot:ro","{home}/.traderbot:/home/traderbot/.traderbot:rw"]',
                "--strict-json",
            ],
            capture_output=True, timeout=15,
        )
        subprocess.run(
            ["openclaw", "config", "set", 'agents.list[0].sandbox.mode', 'off'],
            capture_output=True, timeout=15,
        )
        # Block direct Kalshi API access — agents must use the traderbot CLI
        subprocess.run(
            [
                "openclaw", "config", "set",
                "agents.defaults.sandbox.docker.extraHosts",
                '["api.elections.kalshi.com:127.0.0.1","api.kalshi.com:127.0.0.1","trading-api.kalshi.com:127.0.0.1"]',
                "--strict-json",
            ],
            capture_output=True, timeout=15,
        )
        logger.info("OpenClaw sandbox configuration re-applied")
    except Exception as exc:
        logger.warning("Failed to re-apply sandbox config (openclaw CLI may not be on PATH): %s", exc)


def _reregister_cron_jobs(repo_dir: Path) -> None:
    """Re-register heartbeat cron jobs for all deployed agents."""
    import subprocess
    try:
        # Sysadmin cron
        subprocess.run(
            [sys.executable, "-m", "traderbot", "cron", "setup-heartbeat-tasks",
             "--agent", "main", "--role", "sysadmin", "--replace"],
            capture_output=True, timeout=30,
        )
        # Agent cron for each deployed agent directory
        agents_root = Path.home() / ".openclaw" / "agents"
        if agents_root.exists():
            for agent_dir in agents_root.iterdir():
                if (agent_dir / "agent").is_dir():
                    ag_id = agent_dir.name
                    subprocess.run(
                        [sys.executable, "-m", "traderbot", "cron", "setup-heartbeat-tasks",
                         "--agent", ag_id, "--replace"],
                        capture_output=True, timeout=30,
                    )
        logger.info("Cron jobs re-registered for all deployed agents")
    except Exception as exc:
        logger.warning("Cron re-registration failed: %s", exc)


def _refresh_workspace_files(repo_dir: Path) -> None:
    """Refresh agent workspace files from the repo's template directory.

    Replaces template files (AGENTS.md, SOUL.md, TOOLS.md, etc.) with the
    latest versions from the repo. Preserves user-managed files: USER.md,
    MEMORY.md, HEARTBEAT_DATA.md, SESSION-STATE.md, and .learnings/.
    """
    import shutil as _shutil

    ws_root = Path.home() / ".openclaw" / "workspace"
    template_root = repo_dir / ".openclaw" / "workspace"

    if not template_root.exists():
        logger.debug("No workspace templates at %s, skipping refresh", template_root)
        return

    if not ws_root.exists():
        logger.debug("No deployed workspaces at %s, skipping refresh", ws_root)
        return

    template_files = [
        "AGENTS.md", "SOUL.md", "TOOLS.md", "IDENTITY.md",
        "HEARTBEAT.md",
    ]
    preserved_files = {
        "USER.md", "MEMORY.md", "HEARTBEAT_DATA.md", "SESSION-STATE.md",
    }
    preserved_dirs = {".learnings"}

    for agent_dir in sorted(ws_root.iterdir()):
        if not agent_dir.is_dir():
            continue
        agent_name = agent_dir.name

        # Determine template source
        tdir = template_root / agent_name
        if not tdir.exists():
            tdir = template_root / "agents" / agent_name
        if not tdir.exists():
            tdir = template_root / "agent"
        if not tdir.exists():
            logger.debug("No template source for %s, using fallback", agent_name)
            continue

        replaced = 0
        preserved = 0
        for fname in template_files:
            src = tdir / fname
            dst = agent_dir / fname
            if src.exists():
                _shutil.copy2(str(src), str(dst))
                replaced += 1

        for fname in preserved_files:
            if (agent_dir / fname).exists():
                preserved += 1

        for dname in preserved_dirs:
            if (agent_dir / dname).is_dir():
                preserved += 1

        logger.info(
            "Workspace refresh for %s: %d files replaced, %d preserved",
            agent_name, replaced, preserved,
        )


def _enable_bootstrap_hook() -> None:
    """Deploy bootstrap hook files and enable the traderbot-bootstrap hook.

    The custom bootstrap hook (at ~/.openclaw/hooks/traderbot-bootstrap/)
    mutates context.bootstrapFiles to auto-inject SESSION-STATE.md and
    HEARTBEAT_DATA.md into every agent session, plus injects a Pre-Session
    Status block when pending/escalated items or circuit breaker flags exist.
    """
    import subprocess

    try:
        repo_dir = Path(__file__).resolve().parent.parent.parent
        hook_src = repo_dir / "src" / "traderbot" / "profiles" / "openclaw_config.py"
        if hook_src.exists():
            from traderbot.profiles.openclaw_config import ensure_agent_bootstrap_hook
            ensure_agent_bootstrap_hook()
        else:
            subprocess.run(
                ["openclaw", "hooks", "enable", "traderbot-bootstrap"],
                capture_output=True, timeout=15,
            )
        logger.info("Bootstrap hooks configured")
    except Exception as exc:
        logger.warning("Failed to enable bootstrap hooks: %s", exc)
