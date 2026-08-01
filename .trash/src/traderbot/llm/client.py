"""High-level LLM client with retry logic and pluggable providers."""

from __future__ import annotations

import logging
import time
from typing import Protocol, runtime_checkable

from traderbot.exceptions import ErrorCodes, TraderBotError
from traderbot.llm.ollama import OllamaConnectionError

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE = 1.0


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal provider interface that LLMClient relies on."""

    def generate(self, prompt: str) -> str: ...


class LLMClientError(TraderBotError):
    """Raised when the LLM client exhausts retries or hits a permanent error."""

    def __init__(self, message: str = "", error_code: int = ErrorCodes.LLM, **kwargs) -> None:
        super().__init__(message, error_code=error_code, **kwargs)


class LLMClient:
    """Synchronous LLM client with exponential-backoff retry.

    Parameters
    ----------
    provider : LLMProvider
        Any object implementing ``generate(prompt: str) -> str``
        (e.g. :class:`~traderbot.llm.ollama.OllamaProvider`).
    max_retries : int, optional
        Maximum number of retry attempts for transient errors. Defaults to 3.
    """

    def __init__(
        self,
        provider: LLMProvider,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        self.provider = provider
        self.max_retries = max_retries

    def query(self, prompt: str) -> str:
        """Send *prompt* to the provider and return the response text.

        Retries transient connection/timeout errors up to *max_retries*
        times with exponential backoff (1 s, 2 s, 4 s).

        Raises
        ------
        LLMClientError
            If all retries are exhausted or a non-transient error occurs.
        """
        last_exc: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                return self.provider.generate(prompt)
            except OllamaConnectionError as exc:
                last_exc = exc
                if attempt < self.max_retries - 1:
                    wait = BACKOFF_BASE * (2**attempt)
                    logger.warning(
                        "LLM request failed (attempt %d/%d), retrying in %.0fs: %s",
                        attempt + 1,
                        self.max_retries,
                        wait,
                        exc,
                    )
                    time.sleep(wait)
                # Non-transient / unexpected errors surface immediately
            except Exception as exc:
                raise LLMClientError(f"LLM request failed permanently: {exc}") from exc

        raise LLMClientError(
            f"LLM request failed after {self.max_retries} retries: {last_exc}"
        ) from last_exc
