"""Per-profile environment-based credential resolution."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)


class ProfileAuthStore:
    """Per-profile credential store using environment variables.

    API keys are shared globally via .env; per-profile overrides use
    KALSHI_API_KEY_PROFILE_{NAME} env vars.
    """

    def __init__(self, profile: TradingProfile) -> None:
        self._profile = profile

    def get_credentials(self, service: str) -> tuple[str, str] | None:
        """Retrieve credentials for this profile from env vars.

        Returns:
            Tuple of (key, secret) if found, None otherwise
        """
        from traderbot.paths import get_data_dir

        prefix = self._profile.name.upper().replace("-", "_").replace(" ", "_")

        if service == "kalshi":
            api_key = os.environ.get(f"KALSHI_API_KEY_PROFILE_{prefix}")
            pem = os.environ.get(f"KALSHI_PRIVATE_KEY_PEM_PROFILE_{prefix}")
            if not pem:
                path = os.environ.get(f"KALSHI_PRIVATE_KEY_PATH_PROFILE_{prefix}")
                if path:
                    from pathlib import Path
                    p = Path(path)
                    if p.is_file():
                        pem = p.read_text()

            if not api_key or not pem:
                env_path = get_data_dir() / ".env"
                if env_path.exists():
                    api_key = api_key or _env_file_get_value(env_path, f"KALSHI_API_KEY_PROFILE_{prefix}")
                    pem = pem or _env_file_get_value(env_path, f"KALSHI_PRIVATE_KEY_PEM_PROFILE_{prefix}")
                    if not pem:
                        pem_path = _env_file_get_value(env_path, f"KALSHI_PRIVATE_KEY_PATH_PROFILE_{prefix}")
                        if pem_path:
                            from pathlib import Path
                            p = Path(pem_path)
                            if p.is_file():
                                pem = p.read_text()

            if api_key and pem:
                return (api_key, pem)
        else:
            env_name = f"{service.upper()}_API_KEY_PROFILE_{prefix}"
            val = os.environ.get(env_name)
            if not val:
                env_path = get_data_dir() / ".env"
                if env_path.exists():
                    val = _env_file_get_value(env_path, env_name)
            if val:
                return (val, "")

        return None

    def has_credentials(self, service: str) -> bool:
        return self.get_credentials(service) is not None


def _env_file_get_value(env_path: os.PathLike, key: str) -> str | None:
    from pathlib import Path

    path = Path(env_path)
    if not path.exists():
        return None

    lines = path.read_text().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            i += 1
            continue
        k, _, v = stripped.partition("=")
        if k.strip() != key:
            i += 1
            continue
        v = v.strip()
        if v.startswith('"') and not v.endswith('"'):
            parts = [v[1:]]
            i += 1
            while i < len(lines):
                parts.append(lines[i])
                if lines[i].rstrip().endswith('"'):
                    break
                i += 1
            value = "\n".join(parts)
            if value.endswith('"'):
                value = value[:-1]
            return value
        return v.strip().strip("'\"")
    return None
