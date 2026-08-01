"""Tests for news/embeddings.py — VoyageClient with lazy init, rate limiting, and batch API."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest  # noqa: TC002

from traderbot.news.embeddings import (
    _RATE_LIMIT_MAX_CALLS,
    _RATE_LIMIT_WINDOW_SECS,
    EMBED_DIMENSION,
    VoyageClient,
)


def _make_mock_client() -> MagicMock:
    mock = MagicMock()
    mock.embed.return_value = MagicMock(embeddings=[[0.1] * EMBED_DIMENSION])
    mock.rerank.return_value = MagicMock(results=[])
    mock.batches.create.return_value = MagicMock(id="batch_123")
    mock.batches.retrieve.return_value = MagicMock(
        status="completed", output_file_id="file_abc"
    )
    mock.files.retrieve_content.return_value = ""
    return mock


def _make_voyage_client_with_key(monkeypatch: pytest.MonkeyPatch) -> VoyageClient:
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key-12345")
    return VoyageClient()


def _set_client(vc: VoyageClient, mock_client: MagicMock) -> None:
    vc._client = mock_client
    vc._key_available = True


VOYAGEAI_MODULE = "traderbot.news.embeddings.voyageai"


class TestVoyageClientInit:

    def test_key_available(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("VOYAGE_API_KEY", "test-key-12345")
        vc = VoyageClient()
        assert vc._key_available is True

    def test_key_not_available(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
        vc = VoyageClient()
        assert vc._key_available is False

    def test_voyageai_not_installed(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("VOYAGE_API_KEY", "test-key-12345")
        vc = VoyageClient()
        with patch(VOYAGEAI_MODULE, None):
            assert vc._is_available() is False


class TestEmbed:

    def test_embed_success(self, monkeypatch: pytest.MonkeyPatch):
        vc = _make_voyage_client_with_key(monkeypatch)
        mock_client = _make_mock_client()
        expected = [0.5] * EMBED_DIMENSION
        mock_client.embed.return_value = MagicMock(embeddings=[expected])
        _set_client(vc, mock_client)

        with patch(VOYAGEAI_MODULE, MagicMock()):
            result = vc.embed("test text")
        assert result == expected
        mock_client.embed.assert_called_once()

    def test_embed_no_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
        vc = VoyageClient()
        assert vc.embed("test") is None

    def test_embed_rate_limit(self, monkeypatch: pytest.MonkeyPatch):
        vc = _make_voyage_client_with_key(monkeypatch)
        mock_client = _make_mock_client()
        _set_client(vc, mock_client)
        now = time.monotonic()
        vc._call_timestamps = [now - 0.001] * _RATE_LIMIT_MAX_CALLS

        with patch(VOYAGEAI_MODULE, MagicMock()):
            assert vc.embed("test") is None
        mock_client.embed.assert_not_called()

    def test_embed_exception(self, monkeypatch: pytest.MonkeyPatch):
        vc = _make_voyage_client_with_key(monkeypatch)
        mock_client = _make_mock_client()
        mock_client.embed.side_effect = RuntimeError("API error")
        _set_client(vc, mock_client)

        with patch(VOYAGEAI_MODULE, MagicMock()):
            assert vc.embed("test") is None


class TestEmbedBatch:

    def test_embed_batch_success(self, monkeypatch: pytest.MonkeyPatch):
        vc = _make_voyage_client_with_key(monkeypatch)
        mock_client = _make_mock_client()
        expected = [[0.1] * EMBED_DIMENSION, [0.2] * EMBED_DIMENSION]
        mock_client.embed.return_value = MagicMock(embeddings=expected)
        _set_client(vc, mock_client)

        with patch(VOYAGEAI_MODULE, MagicMock()):
            result = vc.embed_batch(["text one", "text two"])
        assert result == expected

    def test_embed_batch_empty(self, monkeypatch: pytest.MonkeyPatch):
        vc = _make_voyage_client_with_key(monkeypatch)
        assert vc.embed_batch([]) == []

    def test_embed_batch_no_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
        vc = VoyageClient()
        assert vc.embed_batch(["text"]) is None

    def test_embed_batch_rate_limit(self, monkeypatch: pytest.MonkeyPatch):
        vc = _make_voyage_client_with_key(monkeypatch)
        mock_client = _make_mock_client()
        _set_client(vc, mock_client)
        now = time.monotonic()
        vc._call_timestamps = [now - 0.001] * _RATE_LIMIT_MAX_CALLS

        with patch(VOYAGEAI_MODULE, MagicMock()):
            assert vc.embed_batch(["text"]) is None
        mock_client.embed.assert_not_called()


class TestRerank:

    def test_rerank_success(self, monkeypatch: pytest.MonkeyPatch):
        vc = _make_voyage_client_with_key(monkeypatch)
        mock_client = _make_mock_client()

        r1 = MagicMock(index=2, relevance_score=0.9)
        r2 = MagicMock(index=0, relevance_score=0.7)
        r3 = MagicMock(index=1, relevance_score=0.5)
        mock_client.rerank.return_value = MagicMock(results=[r1, r2, r3])
        _set_client(vc, mock_client)

        with patch(VOYAGEAI_MODULE, MagicMock()):
            result = vc.rerank("query", ["doc0", "doc1", "doc2"])
        assert result == [(2, 0.9), (0, 0.7), (1, 0.5)]

    def test_rerank_empty_docs(self, monkeypatch: pytest.MonkeyPatch):
        vc = _make_voyage_client_with_key(monkeypatch)
        assert vc.rerank("query", []) == []

    def test_rerank_no_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
        vc = VoyageClient()
        assert vc.rerank("query", ["doc"]) is None

    def test_rerank_with_top_k(self, monkeypatch: pytest.MonkeyPatch):
        vc = _make_voyage_client_with_key(monkeypatch)
        mock_client = _make_mock_client()
        r1 = MagicMock(index=0, relevance_score=0.95)
        mock_client.rerank.return_value = MagicMock(results=[r1])
        _set_client(vc, mock_client)

        with patch(VOYAGEAI_MODULE, MagicMock()):
            result = vc.rerank("query", ["doc1", "doc2"], top_k=1)
        assert result == [(0, 0.95)]
        call_kwargs = mock_client.rerank.call_args[1]
        assert call_kwargs["top_k"] == 1


class TestRateLimiting:

    def test_rate_limit_allows_under_limit(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
        vc = VoyageClient()
        assert vc._check_rate_limit() is True
        assert len(vc._call_timestamps) == 1

    def test_rate_limit_blocks_over_limit(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
        vc = VoyageClient()
        now = time.monotonic()
        vc._call_timestamps = [now - 0.001] * _RATE_LIMIT_MAX_CALLS
        assert vc._check_rate_limit() is False

    def test_rate_limit_window_expiry(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
        vc = VoyageClient()
        now = time.monotonic()
        old_ts = now - _RATE_LIMIT_WINDOW_SECS - 10
        vc._call_timestamps = [old_ts] * _RATE_LIMIT_MAX_CALLS
        assert vc._check_rate_limit() is True
        assert len(vc._call_timestamps) == 1


class TestBatchAPI:

    def test_batch_submit_success(self, monkeypatch: pytest.MonkeyPatch):
        vc = _make_voyage_client_with_key(monkeypatch)
        mock_client = _make_mock_client()
        _set_client(vc, mock_client)

        with patch(VOYAGEAI_MODULE, MagicMock()):
            result = vc.embed_batch_submit(["text1", "text2"])
        assert result == "batch_123"
        mock_client.batches.create.assert_called_once()

    def test_batch_submit_empty_texts(self, monkeypatch: pytest.MonkeyPatch):
        vc = _make_voyage_client_with_key(monkeypatch)
        mock_client = _make_mock_client()
        _set_client(vc, mock_client)

        with patch(VOYAGEAI_MODULE, MagicMock()):
            result = vc.embed_batch_submit([])
        assert result is None
        mock_client.batches.create.assert_not_called()

    def test_batch_submit_no_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
        vc = VoyageClient()
        assert vc.embed_batch_submit(["text"]) is None

    def test_batch_retrieve_completed(self, monkeypatch: pytest.MonkeyPatch):
        vc = _make_voyage_client_with_key(monkeypatch)
        mock_client = _make_mock_client()

        embeddings_data = [
            {"data": {"embedding": [0.1] * EMBED_DIMENSION}},
            {"data": {"embedding": [0.2] * EMBED_DIMENSION}},
        ]
        content = "\n".join(json.dumps(obj) for obj in embeddings_data)
        mock_client.files.retrieve_content.return_value = content
        mock_client.batches.retrieve.return_value = MagicMock(
            status="completed", output_file_id="file_abc"
        )
        _set_client(vc, mock_client)

        with patch(VOYAGEAI_MODULE, MagicMock()):
            result = vc.embed_batch_retrieve("batch_123")
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] == [0.1] * EMBED_DIMENSION
        assert result[1] == [0.2] * EMBED_DIMENSION

    def test_batch_retrieve_not_ready(self, monkeypatch: pytest.MonkeyPatch):
        vc = _make_voyage_client_with_key(monkeypatch)
        mock_client = _make_mock_client()
        mock_client.batches.retrieve.return_value = MagicMock(
            status="queued", output_file_id=None
        )
        _set_client(vc, mock_client)

        with patch(VOYAGEAI_MODULE, MagicMock()):
            result = vc.embed_batch_retrieve("batch_123")
        assert result is None

    def test_batch_retrieve_no_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
        vc = VoyageClient()
        assert vc.embed_batch_retrieve("batch_123") is None


class TestEmbedBatchRetry:

    def test_embed_batch_retries_on_failure_then_succeeds(self, monkeypatch: pytest.MonkeyPatch):
        vc = _make_voyage_client_with_key(monkeypatch)
        mock_client = _make_mock_client()
        expected = [[0.1] * EMBED_DIMENSION, [0.2] * EMBED_DIMENSION]
        call_count = 0

        def embed_side_effect(texts, model, input_type):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient API error")
            return MagicMock(embeddings=expected)

        mock_client.embed.side_effect = embed_side_effect
        _set_client(vc, mock_client)

        with patch(VOYAGEAI_MODULE, MagicMock()), patch(
            "traderbot.news.embeddings.time.sleep"
        ) as mock_sleep:
            result = vc.embed_batch(["text one", "text two"])

        assert result == expected
        assert call_count == 3
        backoff_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert backoff_calls == [1, 2]

    def test_embed_batch_returns_none_after_all_retries_exhausted(self, monkeypatch: pytest.MonkeyPatch):
        vc = _make_voyage_client_with_key(monkeypatch)
        mock_client = _make_mock_client()
        mock_client.embed.side_effect = RuntimeError("permanent API failure")
        _set_client(vc, mock_client)

        with patch(VOYAGEAI_MODULE, MagicMock()), patch(
            "traderbot.news.embeddings.time.sleep"
        ) as mock_sleep:
            result = vc.embed_batch(["text one"])

        assert result is None
        assert mock_client.embed.call_count == 3
        backoff_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert backoff_calls == [1, 2]

    def test_embed_batch_succeeds_immediately(self, monkeypatch: pytest.MonkeyPatch):
        vc = _make_voyage_client_with_key(monkeypatch)
        mock_client = _make_mock_client()
        expected = [[0.1] * EMBED_DIMENSION]
        mock_client.embed.return_value = MagicMock(embeddings=expected)
        _set_client(vc, mock_client)

        with patch(VOYAGEAI_MODULE, MagicMock()), patch(
            "traderbot.news.embeddings.time.sleep"
        ) as mock_sleep:
            result = vc.embed_batch(["text one"])

        assert result == expected
        mock_client.embed.assert_called_once()
        mock_sleep.assert_not_called()

    def test_embed_batch_retry_empty_embeddings(self, monkeypatch: pytest.MonkeyPatch):
        vc = _make_voyage_client_with_key(monkeypatch)
        mock_client = _make_mock_client()
        call_count = 0

        def embed_side_effect(texts, model, input_type):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(embeddings=None)
            return MagicMock(embeddings=[[0.5] * EMBED_DIMENSION])

        mock_client.embed.side_effect = embed_side_effect
        _set_client(vc, mock_client)

        with patch(VOYAGEAI_MODULE, MagicMock()), patch(
            "traderbot.news.embeddings.time.sleep"
        ) as mock_sleep:
            result = vc.embed_batch(["text"])

        assert result == [[0.5] * EMBED_DIMENSION]
        assert call_count == 2
        mock_sleep.assert_called_once_with(1)

    def test_embed_batch_retry_with_custom_max_retries(self, monkeypatch: pytest.MonkeyPatch):
        vc = _make_voyage_client_with_key(monkeypatch)
        mock_client = _make_mock_client()

        max_retries = 2

        def embed_side_effect(texts, model, input_type):
            raise RuntimeError("permanent failure")

        mock_client.embed.side_effect = embed_side_effect
        _set_client(vc, mock_client)

        with patch(VOYAGEAI_MODULE, MagicMock()), patch(
            "traderbot.news.embeddings.time.sleep"
        ) as mock_sleep:
            result = vc.embed_batch(["text"], max_retries=max_retries)

        assert result is None
        assert mock_client.embed.call_count == max_retries
        backoff_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert backoff_calls == [1]
