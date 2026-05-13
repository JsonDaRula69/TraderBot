"""Shared fixtures for live Kalshi integration tests.

Parses credentials from test-keys.txt at project root, creates a temporary
.env file, patches environment variables, and tears everything down after
the test session.  No keys are ever hardcoded — they come exclusively from
test-keys.txt.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Generator

import pytest
from pydantic import SecretStr

from traderbot.kalshi.cache import MarketDataCache
from traderbot.kalshi.client import KalshiClient, KalshiConfig
from traderbot.kalshi.provider import ProdDataProvider

# ---------------------------------------------------------------------------
# Credential parsing
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_KEYS_FILE = _PROJECT_ROOT / "test-keys.txt"


def _parse_credentials(keys_file: Path) -> tuple[str, str]:
    """Extract API key and RSA private key from test-keys.txt.

    Expected format (first line):
        Kalshi API key: <KEY>       or  Kalshi Read Only API: <KEY>
    RSA key block:
        -----BEGIN RSA PRIVATE KEY-----
        ...
        -----END RSA PRIVATE KEY-----

    Returns (api_key, private_key_pem).
    """
    if not keys_file.exists():
        pytest.skip("test-keys.txt not found at project root")

    text = keys_file.read_text()

    # API key — match either "Kalshi API key:" or "Kalshi Read Only API:"
    api_match = re.search(r"Kalshi\s+(?:Read Only\s+)?API(?:\s+key)?:\s*(\S+)", text)
    if not api_match:
        pytest.skip("Could not parse Kalshi API key from test-keys.txt")
    api_key = api_match.group(1)

    # RSA private key block
    pem_match = re.search(
        r"(-----BEGIN RSA PRIVATE KEY-----.*?-----END RSA PRIVATE KEY-----)",
        text,
        re.DOTALL,
    )
    if not pem_match:
        pytest.skip("Could not parse RSA private key from test-keys.txt")
    private_key_pem = pem_match.group(1)

    if not api_key or not private_key_pem:
        pytest.skip("Missing Kalshi credentials in test-keys.txt")

    return api_key, private_key_pem


# ---------------------------------------------------------------------------
# Session-scoped fixture: temp .env + env var patching
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def temp_traderbot_env() -> Generator[Path, None, None]:
    """Create a temporary .env from test-keys.txt credentials and patch env vars.

    - Parses test-keys.txt for API key + RSA key
    - Creates a temp directory with .env file
    - Sets KALSHI_API_KEY and KALSHI_PRIVATE_KEY_PEM env vars
    - Sets TRADERBOT_TEST_ENV_PATH to the temp dir
    - Yields the temp directory path
    - Teardown: restores env vars, removes temp directory
    """
    api_key, private_key_pem = _parse_credentials(_KEYS_FILE)

    # Save original env values for restoration
    old_api_key = os.environ.get("KALSHI_API_KEY")
    old_private_key = os.environ.get("KALSHI_PRIVATE_KEY_PEM")
    old_env_path = os.environ.get("TRADERBOT_TEST_ENV_PATH")

    # Create temp directory and .env file
    tmp_path = Path(tempfile.mkdtemp(prefix="traderbot-test-"))
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"KALSHI_API_KEY={api_key}\n"
        f"KALSHI_PRIVATE_KEY_PEM={private_key_pem}\n"
    )

    # Patch environment variables (pydantic-settings reads these)
    os.environ["KALSHI_API_KEY"] = api_key
    os.environ["KALSHI_PRIVATE_KEY_PEM"] = private_key_pem
    os.environ["TRADERBOT_TEST_ENV_PATH"] = str(tmp_path)

    yield tmp_path

    # --- Teardown ---
    # Restore original env vars
    if old_api_key is not None:
        os.environ["KALSHI_API_KEY"] = old_api_key
    else:
        os.environ.pop("KALSHI_API_KEY", None)

    if old_private_key is not None:
        os.environ["KALSHI_PRIVATE_KEY_PEM"] = old_private_key
    else:
        os.environ.pop("KALSHI_PRIVATE_KEY_PEM", None)

    if old_env_path is not None:
        os.environ["TRADERBOT_TEST_ENV_PATH"] = old_env_path
    else:
        os.environ.pop("TRADERBOT_TEST_ENV_PATH", None)

    # Destroy temp directory (including .env)
    shutil.rmtree(tmp_path, ignore_errors=True)


# ---------------------------------------------------------------------------
# Function-scoped fixtures: live_client, live_provider
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
async def live_client(
    temp_traderbot_env: Path,
) -> Generator[KalshiClient, None, None]:
    """Create a KalshiClient configured with live credentials.

    Reads the API key and private key from env (set by temp_traderbot_env)
    and constructs KalshiConfig with explicit SecretStr values so we don't
    depend on file resolution.
    """
    api_key = os.environ["KALSHI_API_KEY"]
    private_key_pem = os.environ["KALSHI_PRIVATE_KEY_PEM"]

    config = KalshiConfig(
        api_key=SecretStr(api_key),
        private_key_pem=SecretStr(private_key_pem),
    )
    client = KalshiClient(config=config)
    yield client
    await client.close()


@pytest.fixture(scope="function")
async def live_provider(live_client: KalshiClient) -> ProdDataProvider:
    """Create a ProdDataProvider backed by the live KalshiClient (no cache)."""
    return ProdDataProvider(client=live_client)


@pytest.fixture(scope="function")
def live_cache() -> Generator[MarketDataCache, None, None]:
    """Create a MarketDataCache that writes to a temp directory (not ~/.traderbot)."""
    from unittest.mock import patch

    tmp_dir = Path(tempfile.mkdtemp(prefix="traderbot-cache-"))
    db_path = tmp_dir / "settlement_cache.db"
    with patch("traderbot.kalshi.cache._resolve_settlement_db_path", return_value=db_path):
        cache = MarketDataCache(profile=None)
    yield cache
    shutil.rmtree(tmp_dir, ignore_errors=True)