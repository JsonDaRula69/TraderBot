"""Tests for llm_client — LLM call handler with rate limiting, retry, and graceful degradation."""

import time
from unittest import mock

import httpx
import pytest

from experiments.v3.llm_client import LLMClient, TokenBucket

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_resp(status_code=200, json_body=None, text_body=""):
    """Build a mock httpx.Response."""
    resp = mock.MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_body or {"response": ""}
    resp.text = text_body or ""
    resp.raise_for_status = mock.MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}", request=mock.MagicMock(), response=resp
        )
    return resp


def _valid_json_response(decision="buy_yes", prob=0.62, conf=0.75, reasoning="strong signal"):
    raw = (
        '{"decision":"' + decision + '","estimated_prob":' + str(prob)
        + ',"confidence":' + str(conf) + ',"reasoning":"' + reasoning + '"}'
    )
    resp = mock.MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {"response": raw}
    resp.text = raw
    resp.raise_for_status = mock.MagicMock()
    return resp


# ---------------------------------------------------------------------------
# TokenBucket
# ---------------------------------------------------------------------------


class TestTokenBucket:
    def test_initial_tokens_are_full(self):
        tb = TokenBucket(rate=10, burst=10)
        assert tb.tokens == 10

    def test_acquire_consumes_token_when_available(self):
        tb = TokenBucket(rate=10, burst=10)
        wait = tb.acquire()
        assert wait == 0.0
        assert tb.tokens == 9.0

    def test_acquire_returns_wait_time_when_empty(self, monkeypatch):
        tb = TokenBucket(rate=10, burst=10)
        # Drain all tokens
        for _ in range(10):
            tb.acquire()
        # Next acquire should need to wait
        wait = tb.acquire()
        assert wait > 0.0


# ---------------------------------------------------------------------------
# LLMClient — API key
# ---------------------------------------------------------------------------


class TestLLMClientApiKey:
    def test_allows_missing_api_key(self, monkeypatch):
        """OLLAMA_API_KEY is optional — local Ollama handles auth internally."""
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        client = LLMClient()
        assert client.api_key is None or client.api_key == ""

    def test_constructs_when_env_var_set(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key-123")
        client = LLMClient()
        assert client.api_key == "test-key-123"


# ---------------------------------------------------------------------------
# LLMClient — parsing
# ---------------------------------------------------------------------------


class TestLLMClientParsing:
    def test_valid_json_parsed_correctly(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
        client = LLMClient()

        raw = '{"decision":"buy_yes","estimated_prob":0.62,"confidence":0.75,"reasoning":"strong"}'
        resp = client._parse_response(raw)

        assert resp.decision == "buy_yes"
        assert resp.estimated_prob == 0.62
        assert resp.confidence == 0.75
        assert resp.reasoning == "strong"
        assert resp.raw_response == raw

    def test_malformed_json_returns_fallback(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
        client = LLMClient()

        resp = client._parse_response("garbled not json @@@")

        assert resp.decision == "skip"
        assert resp.confidence == 0.1

    def test_valid_json_missing_decision_defaults_to_skip(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
        client = LLMClient()

        raw = '{"estimated_prob":0.70,"confidence":0.80}'
        resp = client._parse_response(raw)

        assert resp.decision == "skip"
        assert resp.estimated_prob == 0.70
        assert resp.confidence == 0.80


# ---------------------------------------------------------------------------
# LLMClient — call with mocked httpx
# ---------------------------------------------------------------------------


class TestLLMClientCall:
    def test_call_valid_response(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
        client = LLMClient()

        mock_post = mock.MagicMock(return_value=_valid_json_response("buy_no", 0.35, 0.70, "bearish"))
        monkeypatch.setattr(httpx, "post", mock_post)

        result = client.call("test prompt")

        assert result.decision == "buy_no"
        assert result.estimated_prob == 0.35
        assert result.confidence == 0.70
        assert result.reasoning == "bearish"

    def test_429_retry_then_200(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
        client = LLMClient()

        mock_post = mock.MagicMock()
        mock_post.side_effect = [
            _make_resp(429),
            _valid_json_response("buy_yes", 0.62, 0.75, "retry worked"),
        ]
        monkeypatch.setattr(httpx, "post", mock_post)
        # Speed up backoff sleep
        monkeypatch.setattr(time, "sleep", mock.MagicMock())

        result = client.call("test prompt")
        assert result.decision == "buy_yes"
        assert mock_post.call_count == 2

    def test_429_three_times_returns_fallback(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
        client = LLMClient()

        mock_post = mock.MagicMock()
        mock_post.side_effect = [_make_resp(429), _make_resp(429), _make_resp(429)]
        monkeypatch.setattr(httpx, "post", mock_post)
        monkeypatch.setattr(time, "sleep", mock.MagicMock())

        result = client.call("test prompt")
        assert result.decision == "skip"
        assert result.confidence == 0.1
        # 3 attempts (0, 1, 2), no more
        assert mock_post.call_count == 3

    def test_503_retry_then_success(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
        client = LLMClient()

        mock_post = mock.MagicMock()
        mock_post.side_effect = [
            _make_resp(503),
            _valid_json_response("buy_no", 0.35, 0.70, "retry after 503"),
        ]
        monkeypatch.setattr(httpx, "post", mock_post)
        monkeypatch.setattr(time, "sleep", mock.MagicMock())

        result = client.call("test prompt")
        assert result.decision == "buy_no"
        assert mock_post.call_count == 2

    def test_timeout_returns_fallback(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
        client = LLMClient()

        mock_post = mock.MagicMock()
        mock_post.side_effect = httpx.TimeoutException("timed out")
        monkeypatch.setattr(httpx, "post", mock_post)
        monkeypatch.setattr(time, "sleep", mock.MagicMock())

        result = client.call("test prompt")
        assert result.decision == "skip"
        assert result.confidence == 0.1
        # Timeout retries 3 times, all fail → fallback
        assert mock_post.call_count == 3

    def test_rate_limiting_enforced(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
        client = LLMClient()

        # Track mock time
        mock_time = mock.MagicMock()
        mock_time.return_value = 0.0
        monkeypatch.setattr(time, "monotonic", mock_time)
        monkeypatch.setattr(time, "sleep", mock.MagicMock())

        mock_post = mock.MagicMock(return_value=_valid_json_response())
        monkeypatch.setattr(httpx, "post", mock_post)

        # First 10 calls should not sleep (tokens available)
        for i in range(10):
            client.call(f"prompt {i}")

        sleep_calls_before = time.sleep.call_count

        # 11th call: tokens depleted, should sleep
        client.call("prompt 11")
        assert time.sleep.call_count > sleep_calls_before
