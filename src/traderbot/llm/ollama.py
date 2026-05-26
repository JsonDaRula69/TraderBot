"""Ollama local LLM provider."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OLLAMA_DEFAULT_URL = "http://localhost:11434/api/generate"
DEFAULT_TIMEOUT = 60


class OllamaConnectionError(Exception):
    """Raised when the Ollama server cannot be reached."""


class OllamaProvider:
    """Synchronous Ollama provider for the LLMClient.

    Parameters
    ----------
    model : str
        Ollama model name (e.g. ``"llama3"``).
    base_url : str, optional
        Ollama API endpoint. Defaults to ``http://localhost:11434/api/generate``.
    timeout : int, optional
        Request timeout in seconds. Defaults to 60.
    """

    def __init__(
        self,
        model: str,
        base_url: str = OLLAMA_DEFAULT_URL,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        """Send *prompt* to Ollama and return the generated text.

        Raises
        ------
        OllamaConnectionError
            If the Ollama server is unreachable or the request times out.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(self.base_url, json=payload)
                resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self.base_url}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise OllamaConnectionError(
                f"Ollama request timed out after {self.timeout}s"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise OllamaConnectionError(
                f"Ollama returned HTTP {exc.response.status_code}"
            ) from exc

        data = resp.json()
        return data.get("response", "")
