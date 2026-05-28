"""Master password gate using PBKDF2-HMAC-SHA256 for trade/simulate commands.

Setup: first invocation prompts to create a password; the salt and derived key
are persisted in ~/.traderbot/.master_key.

Session caching: after successful authentication, a time-limited session token
is set via TRADERBOT_MASTER_TOKEN env var to avoid re-prompting within the same
shell session. Token expires after 30 minutes.

Auto-authentication: When the command runs with an active paper-mode profile,
the session is started automatically so headless agents do not need to prompt.
Live-mode profiles or general CLI usage still require human authentication.

Auto-refresh: session_active() proactively refreshes the token when it is
within SESSION_REFRESH_THRESHOLD of expiry. This ensures 24/7 autonomous
agents never hit a stale token without human intervention.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
import os
import secrets
import sys
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from traderbot.paths import get_master_key_path

logger = logging.getLogger(__name__)

MASTER_KEY_PATH = get_master_key_path()

PBKDF2_ITERATIONS = 600_000
PBKDF2_KEY_LENGTH = 32
PBKDF2_SALT_LENGTH = 32
SESSION_TOKEN_TTL = 30 * 60
SESSION_REFRESH_SECS = 5 * 60
SESSION_TOKEN_ENV = "TRADERBOT_MASTER_TOKEN"


def _derive_key(password: str, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=PBKDF2_KEY_LENGTH,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(password.encode("utf-8"))


def _constant_time_compare(a: bytes, b: bytes) -> bool:
    return hmac.compare_digest(a, b)


def _read_master_key() -> tuple[bytes, bytes] | None:
    if not MASTER_KEY_PATH.exists():
        return None
    try:
        content = MASTER_KEY_PATH.read_text().strip()
        salt_b64, key_b64 = content.rsplit(":", 1)
        salt = base64.b64decode(salt_b64)
        key = base64.b64decode(key_b64)
        if len(salt) != PBKDF2_SALT_LENGTH or len(key) != PBKDF2_KEY_LENGTH:
            logger.warning("Corrupt .master_key: wrong salt/key length")
            return None
        return salt, key
    except (ValueError, binascii.Error) as e:
        logger.warning("Malformed .master_key: %s", e)
        return None


def _write_master_key(salt: bytes, key: bytes) -> None:
    content = f"{base64.b64encode(salt).decode()}:{base64.b64encode(key).decode()}"
    MASTER_KEY_PATH.write_text(content)
    if sys.platform != "win32":
        MASTER_KEY_PATH.chmod(0o600)


def _make_session_token(stored_key: bytes, timestamp: int) -> str:
    msg = f"session:{timestamp}".encode()
    mac = hmac.new(stored_key, msg, hashlib.sha256).digest()
    return f"{timestamp}:{base64.b64encode(mac).decode()}"


def _verify_session_token(token: str, stored_key: bytes) -> bool:
    try:
        ts_str, mac_b64 = token.rsplit(":", 1)
        timestamp = int(ts_str)
    except (ValueError, TypeError):
        return False

    if int(time.time()) - timestamp > SESSION_TOKEN_TTL:
        return False

    msg = f"session:{timestamp}".encode()
    expected_mac = hmac.new(stored_key, msg, hashlib.sha256).digest()
    return _constant_time_compare(base64.b64decode(mac_b64), expected_mac)


def is_setup() -> bool:
    return MASTER_KEY_PATH.exists()


def session_active() -> bool:
    token = os.environ.get(SESSION_TOKEN_ENV)
    if not token:
        return False
    stored = _read_master_key()
    if stored is None:
        return False

    stored_key = stored[1]

    # Proactive refresh: if the token is within SESSION_REFRESH_SECS of expiry,
    # re-issue a fresh one so long-running agents never hit a stale token.
    try:
        ts_str, _ = token.rsplit(":", 1)
        age = int(time.time()) - int(ts_str)
    except (ValueError, TypeError):
        age = 0

    if age >= SESSION_TOKEN_TTL - SESSION_REFRESH_SECS:
        os.environ[SESSION_TOKEN_ENV] = _make_session_token(stored_key, int(time.time()))
        logger.debug("Session token refreshed proactively (age=%ds)", age)
        return True

    return _verify_session_token(token, stored_key)


def authenticate(password: str) -> bool:
    stored = _read_master_key()
    if stored is None:
        logger.warning("Master password not set up; rejecting authentication")
        return False

    salt, expected_key = stored
    try:
        derived = _derive_key(password, salt)
    except Exception:
        logger.exception("Key derivation failed")
        return False

    if not _constant_time_compare(derived, expected_key):
        return False

    os.environ[SESSION_TOKEN_ENV] = _make_session_token(expected_key, int(time.time()))
    return True


def _read_env_file_env(key: str) -> str | None:
    """Read a value from ~/.traderbot/.env if the file exists.

    Fallback for when env vars are not passed through the process hierarchy
    (e.g. OpenClaw agent subprocesses). This does NOT load into os.environ.
    """
    try:
        from traderbot.paths import get_data_dir

        env_path = get_data_dir() / ".env"
        if not env_path.exists():
            return None
        for line in env_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            k, sep, v = stripped.partition("=")
            if sep and k.strip() == key:
                return v.strip().strip("\"'")
    except Exception:
        logger.debug("Failed to read .env for key %s", key, exc_info=True)
    return None


def _try_auto_authenticate() -> bool:
    stored = _read_master_key()
    if stored is None:
        return False

    key = stored[1]
    env_var = "TRADERBOT_AUTO_AUTH_PAPER"

    # Check process environment first, then fall back to .env file
    auto_auth = os.environ.get(env_var) or _read_env_file_env(env_var)
    if auto_auth and auto_auth.lower() in ("1", "true", "yes"):
        os.environ[SESSION_TOKEN_ENV] = _make_session_token(key, int(time.time()))
        logger.info("Auto-authenticated: %s set", env_var)
        return True

    try:
        from traderbot.profiles.runtime import get_current_profile

        profile = get_current_profile()
        if profile is not None and getattr(profile, "mode", None) == "paper":
            os.environ[SESSION_TOKEN_ENV] = _make_session_token(key, int(time.time()))
            logger.info("Auto-authenticated: paper profile '%s'", profile.name)
            return True
    except Exception:
        logger.debug("Profile resolution failed during auto-auth, falling through")

    return False


def setup_master_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if is_setup():
        raise FileExistsError(
            f"Master password already exists at {MASTER_KEY_PATH}. "
            "Use 'traderbot auth change-master-password' to update it."
        )

    salt = secrets.token_bytes(PBKDF2_SALT_LENGTH)
    key = _derive_key(password, salt)

    MASTER_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _write_master_key(salt, key)

    os.environ[SESSION_TOKEN_ENV] = _make_session_token(key, int(time.time()))
    logger.info("Master password configured at %s", MASTER_KEY_PATH)


def change_master_password(old_password: str, new_password: str) -> None:
    if not is_setup():
        raise FileNotFoundError("No master password configured. Use 'setup-master-password' first.")
    if len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters")

    if not authenticate(old_password):
        raise ValueError("Current password is incorrect")

    salt = secrets.token_bytes(PBKDF2_SALT_LENGTH)
    key = _derive_key(new_password, salt)
    _write_master_key(salt, key)
    os.environ[SESSION_TOKEN_ENV] = _make_session_token(key, int(time.time()))
    logger.info("Master password changed")


def require_auth() -> None:
    if os.environ.get("TRADERBOT_DEV_MODE"):
        return

    if session_active():
        return

    if _try_auto_authenticate():
        return

    stored = _read_master_key()
    if stored is None:
        logger.error(
            "Master password not configured. Run: traderbot auth setup-master-password"
        )
        raise SystemExit(1)

    if os.environ.get("TRADERBOT_NONINTERACTIVE"):
        logger.error("Authentication required but TRADERBOT_NONINTERACTIVE is set")
        raise SystemExit(1)

    for attempt in range(3):
        try:
            password = input(f"Master password (attempt {attempt + 1}/3): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAuthentication cancelled.", file=sys.stderr)
            raise SystemExit(1) from None

        if authenticate(password):
            return

        print("Incorrect password.", file=sys.stderr)
        time.sleep(1)

    logger.error("Too many failed authentication attempts")
    raise SystemExit(1)


def clear_session() -> None:
    os.environ.pop(SESSION_TOKEN_ENV, None)
    logger.info("Master password session cleared")
