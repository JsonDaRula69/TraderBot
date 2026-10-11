from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class ErrorPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True, extra="ignore", frozen=True)

    code: str = ""
    message: str = ""
    details: str = ""


class KalshiError(Exception):
    retryable: bool = False

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message: str = message


class ConfigurationError(KalshiError):
    pass


class AuthenticationError(KalshiError):
    pass


class RateLimitError(KalshiError):
    retryable: bool = True


class RetryExhaustedError(RuntimeError):
    pass


class KalshiAPIError(KalshiError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        details: str,
        status_code: int,
        path: str,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.code: str = code
        self.details: str = details
        self.status_code: int = status_code
        self.path: str = path
        self.retryable: bool = retryable
