import json
import os
import time
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, ConfigDict, Field


class LLMDecisionSchema(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    decision: str = "skip"
    estimated_prob: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.3, ge=0.0, le=1.0)
    reasoning: str = "no reasoning provided"


@dataclass
class LLMResponse:
    decision: str
    estimated_prob: float
    confidence: float
    reasoning: str
    raw_response: str


class TokenBucket:
    def __init__(self, rate: int = 10, burst: int = 10):
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_refill = time.monotonic()

    def acquire(self) -> float:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(float(self.burst), self.tokens + elapsed * self.rate / 60.0)
        self.last_refill = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return 0.0
        wait = (1.0 - self.tokens) * 60.0 / self.rate
        self.tokens = 0.0
        return wait


class LLMClient:
    def __init__(self, model: str = "glm-5.1:cloud", timeout: float = 120.0):
        self.model = model
        self.timeout = timeout
        self.rate_limiter = TokenBucket(rate=10)
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.api_key = os.getenv("OLLAMA_API_KEY")  # optional — Ollama cloud handles auth internally

    def call(self, prompt: str) -> LLMResponse:
        max_retries = 3
        for attempt in range(max_retries):
            wait = self.rate_limiter.acquire()
            if wait > 0:
                time.sleep(wait)

            try:
                resp = httpx.post(
                    f"{self.base_url}/api/generate",
                    json={"model": self.model, "prompt": prompt, "stream": False},
                    timeout=self.timeout,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )

                if resp.status_code == 429 or resp.status_code == 503:
                    if attempt < max_retries - 1:
                        time.sleep(2**attempt)
                        continue
                    return self._fallback_response(resp.text)

                resp.raise_for_status()
                raw = resp.json().get("response", "")
                return self._parse_response(raw)

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                return self._fallback_response(str(e))

        return self._fallback_response("max retries exceeded")

    def _parse_response(self, raw: str) -> LLMResponse:
        try:
            parsed = json.loads(raw)
            return LLMResponse(
                decision=parsed.get("decision", "skip"),
                estimated_prob=float(parsed.get("estimated_prob", 0.5)),
                confidence=float(parsed.get("confidence", 0.3)),
                reasoning=parsed.get("reasoning", "no reasoning provided"),
                raw_response=raw,
            )
        except (json.JSONDecodeError, ValueError):
            return self._fallback_response(raw)

    def _fallback_response(self, raw: str) -> LLMResponse:
        return LLMResponse(
            decision="skip",
            estimated_prob=0.5,
            confidence=0.0,
            reasoning="LLM call failed or returned invalid JSON",
            raw_response=raw,
        )
