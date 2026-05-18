"""LLM Synthesis methodology — uses Ollama (glm-5.1) for single-prompt probability estimation."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .base import MethodologyInterface, MethodologyResult
from .db_utils import get_market, get_market_prices
from .ticker_parser import parse_weather_ticker

try:
    import httpx

    _HAS_HTTPX = True
except ImportError:
    import urllib.error
    import urllib.request

    _HAS_HTTPX = False

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
You are a weather market analyst. Estimate the probability that the following prediction market resolves YES.

Market: {question}
Forecast (timestep {timestep}/10, {forecast_date}):
- High temp: {temp_max_f}°F
- Low temp: {temp_min_f}°F
- Humidity: {humidity_max_pct}%
- Wind: {wind_speed_max_kmh} km/h
- Precipitation: {precip_mm}mm
- Weather code: {weather_code}

Threshold: {strike_value}°F ({direction})
Current market: YES={yes_price}, NO={no_price}
{prior_decisions_summary}

Respond ONLY with a JSON object:
{{"estimated_prob": float, "confidence": float, "reasoning": string}}"""

_OLLAMA_ENDPOINT = "/api/generate"
_OLLAMA_MODEL = "glm-5.1"
_REQUEST_TIMEOUT = 120


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences and extract inner JSON content."""
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()


def _parse_llm_response(raw: str) -> dict:
    """Parse the LLM response, stripping code fences, and extract JSON."""
    cleaned = _strip_code_fences(raw)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def _build_prior_decisions_summary(prior_decisions: list) -> str:
    """Format prior decisions for the prompt."""
    if not prior_decisions:
        return "No prior decisions for this market."
    lines = []
    for d in prior_decisions:
        if isinstance(d, dict):
            lines.append(
                f"- timestep {d.get('timestep', '?')}: "
                f"prob={d.get('estimated_prob', '?')}, "
                f"decision={d.get('decision', '?')}"
            )
        else:
            lines.append(f"- {d}")
    return "Prior decisions:\n" + "\n".join(lines)


def _call_ollama_httpx(url: str, prompt: str, timeout: int) -> str:
    """Call Ollama using httpx."""
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            url,
            json={"model": _OLLAMA_MODEL, "prompt": prompt, "stream": False},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["response"]


def _call_ollama_urllib(url: str, prompt: str, timeout: int) -> str:
    """Call Ollama using urllib (fallback when httpx is unavailable)."""
    payload = json.dumps({"model": _OLLAMA_MODEL, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
        return data["response"]


def _call_ollama(base_url: str, prompt: str, timeout: int = _REQUEST_TIMEOUT) -> str:
    """Call Ollama, trying both httpx and urllib, with URL fallback for Docker."""
    urls = [f"{base_url}{_OLLAMA_ENDPOINT}"]
    if "localhost" in base_url or "127.0.0.1" in base_url:
        docker_url = f"http://host.docker.internal:11434{_OLLAMA_ENDPOINT}"
        if docker_url not in urls:
            urls.append(docker_url)
    elif "host.docker.internal" in base_url:
        local_url = f"http://localhost:11434{_OLLAMA_ENDPOINT}"
        if local_url not in urls:
            urls.append(local_url)

    call_fn = _call_ollama_httpx if _HAS_HTTPX else _call_ollama_urllib

    last_err = None
    for url in urls:
        try:
            return call_fn(url, prompt, timeout)
        except Exception as exc:
            logger.debug("Ollama call failed for %s: %s", url, exc)
            last_err = exc
    raise last_err  # type: ignore[misc]


class LLMSynthesisMethodology(MethodologyInterface):
    """Estimate probability via single-prompt LLM synthesis using Ollama (glm-5.1).

    Sends market context and forecast data to the LLM, parses the structured
    JSON response for probability, confidence, and reasoning.  Falls back to
    (0.5, 0.1, {reasoning: "fallback"}) on any failure.
    """

    NAME = "llm_synthesis"

    def __init__(self, db_path: Path, ollama_url: str = "http://localhost:11434"):
        super().__init__(db_path)
        self.ollama_url = ollama_url.rstrip("/")

    def estimate(
        self,
        ticker: str,
        forecast: dict,
        timestep: int,
        prior_decisions: list,
    ) -> MethodologyResult:
        try:
            return self._estimate(ticker, forecast, timestep, prior_decisions)
        except Exception as e:
            logger.warning("LLM synthesis fallback for %s: %s", ticker, e)
            return MethodologyResult(
                estimated_prob=0.5,
                confidence=0.1,
                reasoning={"reasoning": "fallback", "error": str(e)},
            )

    def _estimate(
        self,
        ticker: str,
        forecast: dict,
        timestep: int,
        prior_decisions: list,
    ) -> MethodologyResult:
        parsed = parse_weather_ticker(ticker)
        city = parsed["city"]
        direction = parsed["direction"]
        strike_value = parsed["strike_value"]

        market = get_market(self.conn, ticker)
        question = (
            market.get("question", f"Will {direction} threshold {strike_value}°F be met in {city}?")
            if market
            else f"Will {direction} threshold {strike_value}°F be met in {city}?"
        )

        prices = get_market_prices(self.conn, ticker, timestep)
        if prices:
            yes_price = prices.get("yes_price", 0.5)
            no_price = prices.get("no_price", 1.0 - yes_price)
        else:
            yes_price = 0.5
            no_price = 0.5

        prompt = _PROMPT_TEMPLATE.format(
            question=question,
            timestep=timestep,
            forecast_date=forecast.get("date", "unknown"),
            temp_max_f=forecast.get("temp_max_f", "N/A"),
            temp_min_f=forecast.get("temp_min_f", "N/A"),
            humidity_max_pct=forecast.get("humidity_max_pct", "N/A"),
            wind_speed_max_kmh=forecast.get("wind_speed_max_kmh", "N/A"),
            precip_mm=forecast.get("precip_mm", "N/A"),
            weather_code=forecast.get("weather_code", "N/A"),
            strike_value=strike_value,
            direction=direction,
            yes_price=yes_price,
            no_price=no_price,
            prior_decisions_summary=_build_prior_decisions_summary(prior_decisions),
        )

        raw_response = _call_ollama(self.ollama_url, prompt)
        parsed_response = _parse_llm_response(raw_response)

        estimated_prob = float(parsed_response.get("estimated_prob", 0.5))
        confidence = float(parsed_response.get("confidence", 0.5))
        reasoning_text = parsed_response.get("reasoning", "")

        reasoning = {
            "methodology": self.NAME,
            "city": city,
            "direction": direction,
            "strike_value": strike_value,
            "timestep": timestep,
            "llm_reasoning": str(reasoning_text),
        }

        return MethodologyResult(
            estimated_prob=estimated_prob,
            confidence=confidence,
            reasoning=reasoning,
        )
