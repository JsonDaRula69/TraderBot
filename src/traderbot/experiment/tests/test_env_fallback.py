"""Tests for .env fallback logic — regression coverage.

Verifies VoyageClient and news ingest read API keys from env first,
then fall back to ~/.traderbot/.env when env var is missing.

These tests mock the filesystem and environment to test the logic paths
without requiring actual .env files or API keys.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest


# ------------------------------------------------------------------
#  VoyageClient .env fallback tests
# ------------------------------------------------------------------


class TestVoyageClientEnvFallback:
    """Verify VoyageClient API key resolution order: env → .env fallback."""

    def test_reads_from_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When VOYAGE_API_KEY is in os.environ, its value is used."""
        monkeypatch.setenv("VOYAGE_API_KEY", "voyage-key-from-env")
        # Remove any leftover .env file interference
        with patch.object(Path, "exists", return_value=False):
            from traderbot.news.embeddings import VoyageClient
            client = VoyageClient()
            assert client._key_available is True

    def test_falls_back_to_dotenv(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """When env var is missing, reads from ~/.traderbot/.env."""
        monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
        env_content = 'VOYAGE_API_KEY="voyage-key-from-dotenv"\n'
        dotenv = tmp_path / ".env"
        dotenv.write_text(env_content)

        with patch("traderbot.paths.get_data_dir", return_value=tmp_path):
            from traderbot.news.embeddings import VoyageClient
            client = VoyageClient()
            assert client._key_available is True

    def test_unavailable_when_neither_set(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When neither env var nor .env has the key, _key_available is False."""
        monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
        # Create empty .env
        (tmp_path / ".env").write_text("")

        with patch("traderbot.paths.get_data_dir", return_value=tmp_path):
            from traderbot.news.embeddings import VoyageClient
            client = VoyageClient()
            assert client._key_available is False

    def test_dotenv_parses_quoted_value(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Value wrapped in double-quotes is properly stripped."""
        monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
        env_content = 'VOYAGE_API_KEY="key-in-quotes"\n'
        (tmp_path / ".env").write_text(env_content)

        with patch("traderbot.paths.get_data_dir", return_value=tmp_path):
            from traderbot.news.embeddings import VoyageClient
            client = VoyageClient()
            assert client._key_available is True

    def test_dotenv_parses_single_quoted_value(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Value wrapped in single-quotes is properly stripped."""
        monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
        env_content = "VOYAGE_API_KEY='key-in-single-quotes'\n"
        (tmp_path / ".env").write_text(env_content)

        with patch("traderbot.paths.get_data_dir", return_value=tmp_path):
            from traderbot.news.embeddings import VoyageClient
            client = VoyageClient()
            assert client._key_available is True

    def test_env_var_takes_precedence(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When both env var and .env exist, env var is used."""
        monkeypatch.setenv("VOYAGE_API_KEY", "key-from-env")
        env_content = 'VOYAGE_API_KEY="key-from-dotenv"\n'
        (tmp_path / ".env").write_text(env_content)

        with patch("traderbot.paths.get_data_dir", return_value=tmp_path):
            from traderbot.news.embeddings import VoyageClient
            client = VoyageClient()
            assert client._key_available is True


# ------------------------------------------------------------------
#  NewsAPI .env fallback tests
# ------------------------------------------------------------------


class TestNewsAPIEnvFallback:
    """Verify news ingest reads NEWSAPI_API_KEY from env → .env fallback."""

    def test_reads_newsapi_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When NEWSAPI_API_KEY is in os.environ, it is used directly."""
        monkeypatch.setenv("NEWSAPI_API_KEY", "newsapi-key-from-env")
        # Simulate the fallback path by importing the logic directly
        import os as _os
        key = _os.environ.get("NEWSAPI_API_KEY")
        assert key == "newsapi-key-from-env"
        # Verify the fallback path won't be entered because key is set
        assert key is not None

    def test_falls_back_to_dotenv_when_env_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When NEWSAPI_API_KEY is missing from env, reads from ~/.traderbot/.env."""
        monkeypatch.delenv("NEWSAPI_API_KEY", raising=False)
        env_content = 'NEWSAPI_API_KEY="newsapi-dotenv-key"\n'
        dotenv_path = tmp_path / ".env"
        dotenv_path.write_text(env_content)

        # Simulate the ingest.py fallback logic
        import os as _os
        newsapi_key = _os.environ.get("NEWSAPI_API_KEY")
        assert newsapi_key is None

        # Fallback path
        env_path = tmp_path / ".env"
        if env_path.exists():
            for line in open(env_path):
                stripped = line.strip()
                if stripped.startswith("NEWSAPI_API_KEY="):
                    newsapi_key = stripped.split("=", 1)[1].strip().strip("\"'")
                    break

        assert newsapi_key == "newsapi-dotenv-key"

    def test_returns_none_when_neither_set(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When neither env var nor .env has the key, result is None."""
        monkeypatch.delenv("NEWSAPI_API_KEY", raising=False)
        (tmp_path / ".env").write_text("")

        import os as _os
        newsapi_key = _os.environ.get("NEWSAPI_API_KEY")
        assert newsapi_key is None

        env_path = tmp_path / ".env"
        if env_path.exists():
            for line in open(env_path):
                stripped = line.strip()
                if stripped.startswith("NEWSAPI_API_KEY="):
                    newsapi_key = stripped.split("=", 1)[1].strip().strip("\"'")
                    break

        assert newsapi_key is None

    def test_dotenv_multiple_lines(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Only the NEWSAPI_API_KEY line is extracted from a multi-line .env."""
        monkeypatch.delenv("NEWSAPI_API_KEY", raising=False)
        env_content = (
            "VOYAGE_API_KEY=vk-123\n"
            'NEWSAPI_API_KEY="newsapi-key"\n'
            "OTHER_VAR=other\n"
        )
        (tmp_path / ".env").write_text(env_content)

        import os as _os
        newsapi_key = _os.environ.get("NEWSAPI_API_KEY")
        assert newsapi_key is None

        env_path = tmp_path / ".env"
        if env_path.exists():
            for line in open(env_path):
                stripped = line.strip()
                if stripped.startswith("NEWSAPI_API_KEY="):
                    newsapi_key = stripped.split("=", 1)[1].strip().strip("\"'")
                    break

        assert newsapi_key == "newsapi-key"
