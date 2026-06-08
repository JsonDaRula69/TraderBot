"""Centralized path constants for TraderBot data directories."""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

WORKSPACE_TEMPLATE_FILES: list[str] = [
    "HEARTBEAT_DATA.md",
    "SESSION-STATE.md",
]


def _resolve_db_path(db_path: Path | None = None) -> Path:
    """Resolve database path: explicit override > profile-specific > global default."""
    from traderbot.db import DB_PATH
    from traderbot.profiles.isolation import get_profile_db_path

    if db_path is not None:
        return db_path

    from traderbot.profiles.runtime import get_current_profile

    profile = get_current_profile()
    if profile is not None:
        return get_profile_db_path(profile, "decisions.db")

    return DB_PATH


def _with_db(db_path: Path | None, func):
    """Run func with a database connection, handling open/close."""
    from traderbot.db import get_connection, init_schema

    with get_connection(_resolve_db_path(db_path)) as conn:
        init_schema(conn)
        return func(conn)


def get_data_dir() -> Path:
    """Return the TraderBot data directory (default: ~/.traderbot)."""
    return Path.home() / ".traderbot"


def get_db_path() -> Path:
    """Return the TraderBot database path."""
    return get_data_dir() / "traderbot.db"


def get_audit_dir() -> Path:
    """Return the audit log directory."""
    from traderbot.profiles.isolation import get_profile_audit_path
    from traderbot.profiles.runtime import get_current_profile

    profile = get_current_profile()
    if profile is not None:
        return get_profile_audit_path(profile)
    return get_data_dir() / "audit"


def get_chromadb_dir() -> Path:
    """Return the ChromaDB directory."""
    return get_data_dir() / "chromadb"


def get_logs_dir() -> Path:
    """Return the logs directory."""
    return get_data_dir() / "logs"


def get_workspace_dir() -> Path:
    """Return the OpenClaw workspace directory (relative to CWD)."""
    ws = Path.cwd() / ".openclaw" / "workspace"
    logger.debug("Workspace dir: %s", ws)
    return ws


def get_agent_workspace_dir() -> Path:
    """Return the sandbox-isolated agent workspace directory."""
    aws = get_data_dir() / "agent_workspace"
    logger.debug("Agent workspace dir: %s", aws)
    return aws


def get_master_key_path() -> Path:
    """Return the master password file path (PBKDF2 salt + derived key)."""
    return get_data_dir() / ".master_key"


def _is_pipx_installed() -> bool:
    """Check if traderbot was installed via pipx.

    pipx installs packages into isolated venvs under ~/.local/pipx/venvs/.
    When running from a pipx venv, the executable path contains 'pipx'.
    """
    import sys

    return "pipx" in sys.executable


def get_install_method() -> str:
    """Return how traderbot was installed: 'pipx', 'pip', or 'git'."""
    if _is_pipx_installed():
        return "pipx"
    try:
        get_source_root()  # raises FileNotFoundError if not in source tree
        return "git"
    except FileNotFoundError:
        return "pip"


def get_source_root() -> Path:
    """Return the source tree root (parent of src/traderbot).

    In a source-tree install (``pip install -e .`` or ``git clone``),
    ``Path(__file__).parent.parent.parent`` resolves to the project root
    containing the ``VERSION`` file and ``.openclaw/`` workspace templates.

    In a pip-installed (wheel) install, that path resolves to the Python
    ``site-packages`` directory which is **not** a project root.  In that
    case we raise ``FileNotFoundError`` because the source tree does not
    exist — callers must fall back to ``importlib.metadata`` or
    ``get_data_dir()`` as appropriate.
    """
    candidate = Path(__file__).resolve().parent.parent.parent
    # A real project root always has a VERSION file (installed by hatchling
    # from the root of the repo).  If it's missing we're inside site-packages.
    if (candidate / "VERSION").exists():
        return candidate
    raise FileNotFoundError(
        f"Source tree root not found (checked {candidate}). "
        "This function is only available in source-tree installations. "
        "Use importlib.metadata or get_data_dir() for pip-installed scenarios."
    )


def ensure_data_dir() -> Path:
    """Create data directory if it doesn't exist and return it."""
    path = get_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    logger.info("Data dir: %s", path)
    return path


def list_all_data_paths() -> list[Path]:
    """Return all well-known paths that TraderBot creates at runtime.

    Used by the uninstall command to enumerate files for removal.
    Does NOT include the repo/install directory or venv — only runtime data.
    """
    base = get_data_dir()
    paths: list[Path] = [
        base / ".env",
        base / ".profile_key",
        base / ".token_key",
        base / "profiles.enc",
        base / "tokens.enc",
        base / "profiles.json",  # legacy
        base / "update_config.json",
        base / ".update_check_cache.json",
        base / "circuit_breaker_state.json",
        base / ".breaker_secret",
        base / ".master_key",
        base / "traderbot.db",  # legacy global DB
        base / "audit",
        base / "chromadb",
        base / "keys",
        base / "logs",
        base / "agent_workspace",
    ]
    # Per-profile directories: {mode}-{name}/db, chroma, audit
    if base.exists():
        for child in base.iterdir():
            if child.is_dir() and "-" in child.name:
                for subdir in ("db", "chroma", "audit"):
                    candidate = child / subdir
                    if candidate.exists():
                        paths.append(candidate)
    return paths


def reset_workspace_templates(workspace_dir: Path | None = None) -> list[Path]:
    """Restore workspace template files to their deployable baseline state.

    Strips runtime data that accumulates from tests or CLI usage:
    - HEARTBEAT_DATA.md: resets the ``Last Heartbeat`` timestamp
    - SESSION-STATE.md: strips bare WAL status lines appended after the
      last structured WAL entry
    """
    ws = workspace_dir or get_workspace_dir()
    restored: list[Path] = []

    hb_path = ws / "HEARTBEAT_DATA.md"
    if hb_path.exists():
        content = hb_path.read_text(encoding="utf-8")
        original = content
        content = re.sub(
            r"## Last Heartbeat:.*",
            "## Last Heartbeat: (not yet run)",
            content,
        )
        if content != original:
            hb_path.write_text(content, encoding="utf-8")
            restored.append(hb_path)

    ss_path = ws / "SESSION-STATE.md"
    if ss_path.exists():
        content = ss_path.read_text(encoding="utf-8")
        original = content
        content = _strip_bare_wal_status(content)
        if content != original:
            ss_path.write_text(content, encoding="utf-8")
            restored.append(ss_path)

    return restored


def _strip_bare_wal_status(content: str) -> str:
    """Strip bare WAL status lines that appear after the last structured entry.

    Runtime code like ``update_status`` appends bare ``Status: REJECTED`` lines
    after the last WAL entry.  These are not part of the template.  Bare lines
    that appear *between* WAL entries (part of the template) are preserved.

    A bare line starts with ``Status:`` but not ``- Status:``.  The last
    structured WAL marker is ``### WAL-``.  Everything after that marker
    (and before the next ``## `` heading) that is a bare ``Status:`` line
    gets removed.
    """
    lines = content.split("\n")
    last_wal_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("### WAL-"):
            last_wal_idx = i

    if last_wal_idx == -1:
        return content

    next_heading_idx = len(lines)
    for i in range(last_wal_idx + 1, len(lines)):
        if lines[i].startswith("## "):
            next_heading_idx = i
            break

    cleaned = []
    for i, line in enumerate(lines):
        if (
            last_wal_idx < i < next_heading_idx
            and line.startswith("Status:")
            and not line.startswith("- Status:")
        ):
            continue
        cleaned.append(line)

    return "\n".join(cleaned)
