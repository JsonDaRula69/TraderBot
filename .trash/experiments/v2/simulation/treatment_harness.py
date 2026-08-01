"""Redesigned experiment harness: tests what TraderBot should provide to an agent.

Runs the SAME LLM agent (glm-5.1:cloud via Ollama) across 4 treatments.
The only difference between treatments is what context TraderBot provides.

Treatments:
  - control: Market price only (current status quo - edge ~ 0)
  - raw_data: Forecast + market price + historical context, no probability estimate
  - structured_prob: estimated_prob from BinCal + confidence + market price
  - calibration_bundle: estimated_prob + confidence interval + sample size +
        forecast bias + model disagreement + market price

The independent variable is what TraderBot provides.
The dependent variable is agent decision quality (Brier, P&L, calibration, timing).

Usage:
  python -m experiments.simulation.treatment_harness \
      --db experiments/v2_experiment_data.db \
      --treatment control \
      --output experiments/results/treatment_control.jsonl \
      --model glm-5.1:cloud
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path

from experiments.methodologies.db_utils import (
    get_connection,
    get_market,
    get_market_prices,
)

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    import urllib.error
    import urllib.request
    _HAS_HTTPX = False

logger = logging.getLogger(__name__)

TREATMENTS = ("control", "raw_data", "structured_prob", "calibration_bundle")
NUM_TIMESTEPS = 5
_OLLAMA_MODEL = "glm-5.1:cloud"
_REQUEST_TIMEOUT = 120


# --- v2 data loaders ---

def _load_forecast(conn: sqlite3.Connection, ticker: str, timestep: int) -> dict:
    """Load forecast from v2 forecasts table."""
    row = conn.execute(
        "SELECT ticker, timestep, days_before, forecast_temp_f, source "
        "FROM forecasts WHERE ticker = ? AND timestep = ?",
        (ticker, timestep),
    ).fetchone()
    return dict(row) if row else {}


def _compute_delta(strike_type: str, forecast_temp: float, threshold: float) -> float:
    """Compute delta between forecast and strike threshold.

    Positive delta always means forecast supports YES resolution.
    - between: delta = forecast_temp - threshold - 0.5 (distance from band center)
    - less:    delta = threshold - forecast_temp (below threshold supports YES)
    - greater: delta = forecast_temp - threshold (above threshold supports YES)
    """
    if strike_type == "between":
        return forecast_temp - threshold - 0.5
    elif strike_type == "less":
        return threshold - forecast_temp
    elif strike_type == "greater":
        return forecast_temp - threshold
    else:
        raise ValueError(f"Unknown strike_type: {strike_type}")


def _build_market_question(strike_type: str, city: str, threshold: float) -> str:
    """Construct market question from strike type, city, and threshold."""
    if strike_type == "between":
        return f"Market: Will the high temp in {city} be {int(threshold)}-{int(threshold)+1}\u00b0F?"
    elif strike_type == "less":
        return f"Market: Will the high temp in {city} be <{int(threshold)}\u00b0F?"
    elif strike_type == "greater":
        return f"Market: Will the high temp in {city} be >{int(threshold)}\u00b0F?"
    else:
        return f"Market: Will the high temp in {city} cross {threshold}\u00b0F?"


# --- Prompt Templates ---

CONTROL_PROMPT = """You are a prediction market trader. You must decide whether to trade on this weather market.

{question}
City: {city_name}
Resolution date: {resolution_date}
Current market prices: YES={yes_price}, NO={no_price}

This is timestep {timestep} of 5. You have {remaining} timesteps remaining before settlement.

{prior_decisions_section}

Based ONLY on the market price, decide:
- buy_yes: if you believe the true probability is significantly above the YES price
- buy_no: if you believe the true probability is significantly below the YES price
- skip: if you cannot form a confident opinion from market price alone

Respond ONLY with a JSON object:
{{"decision": "buy_yes" | "buy_no" | "skip", "estimated_prob": float, "confidence": float, "reasoning": string}}

estimated_prob: your estimate of the probability the market resolves YES (0.0 to 1.0)
confidence: how confident you are in your estimate (0.0 to 1.0)
reasoning: brief explanation of your thinking"""

RAW_DATA_PROMPT = """You are a prediction market trader with access to weather forecast data.

{question}
City: {city_name}
Resolution date: {resolution_date}
Strike type: {strike_type_description}

Forecast at timestep {timestep} of 5 ({days_before} days before resolution):
- Forecast high temp: {forecast_temp_f}\u00b0F

Current market prices: YES={yes_price}, NO={no_price}
Forecast delta: {delta:+.1f}\u00b0F (positive = forecast supports YES)

This is timestep {timestep} of 5. You have {remaining} timesteps remaining before settlement.

{prior_decisions_section}

Analyze the forecast data and market prices to decide:
- buy_yes: if you believe the market will resolve YES and the YES price is too low
- buy_no: if you believe the market will resolve NO and the YES price is too high
- skip: if the edge is thin or confidence is low

Respond ONLY with a JSON object:
{{"decision": "buy_yes" | "buy_no" | "skip", "estimated_prob": float, "confidence": float, "reasoning": string}}

estimated_prob: your estimate of the probability the market resolves YES (0.0 to 1.0)
confidence: how confident you are in your estimate (0.0 to 1.0)
reasoning: brief explanation analyzing the forecast data"""

STRUCTURED_PROB_PROMPT = """You are a prediction market trader. TraderBot has computed a probability estimate from historical forecast accuracy data.

{question}
City: {city_name}
Resolution date: {resolution_date}
Strike type: {strike_type_description}

TraderBot Analysis:
- Forecast: {forecast_temp_f}\u00b0F high (delta: {delta:+.1f}\u00b0F)
- Estimated probability of YES: {estimated_prob:.1%}
- Confidence: {confidence:.1%} (based on {sample_count} historical samples in this delta range)
- Historical accuracy for similar forecasts: {historical_accuracy}

Current market prices: YES={yes_price}, NO={no_price}
Edge = |estimated_prob - YES_price| = {edge:.1%}

This is timestep {timestep} of 5. You have {remaining} timesteps remaining.

{prior_decisions_section}

The TraderBot estimate is a starting point - you may agree, disagree, or adjust based on your own reasoning. Decide:
- buy_yes: if you believe YES is likely and the YES price is too low
- buy_no: if you believe NO is likely and the YES price is too high
- skip: if the edge is thin or you disagree with the estimate

Respond ONLY with a JSON object:
{{"decision": "buy_yes" | "buy_no" | "skip", "estimated_prob": float, "confidence": float, "reasoning": string}}

estimated_prob: YOUR estimate (may differ from TraderBot's)
confidence: how confident you are (0.0 to 1.0)
reasoning: brief explanation - do you agree with TraderBot? Why or why not?"""

CALIBRATION_BUNDLE_PROMPT = """You are a prediction market trader. TraderBot provides a calibration bundle with probability estimate, uncertainty range, and forecast quality metrics.

{question}
City: {city_name}
Resolution date: {resolution_date}
Strike type: {strike_type_description}

=== TraderBot Calibration Bundle ===

Probability Estimate:
  - Estimated probability of YES: {estimated_prob:.1%}
  - 95% confidence interval: [{ci_lower:.1%}, {ci_upper:.1%}]
  - Point estimate reliability: {confidence:.1%}

Historical Context:
  - Sample size in this delta range: {sample_count} forecasts
  - Historical accuracy for similar deltas: {historical_accuracy}
  - Recent forecast bias: {forecast_bias} (this market's forecasts have been {bias_direction})
  - Forecast model agreement: High (single model with ensemble spread of {ensemble_spread}\u00b0F)

Forecast Data:
  - Current forecast: {forecast_temp_f}\u00b0F (delta: {delta:+.1f}\u00b0F)
  - Forecast evolution: {forecast_evolution}
  - Trend: Forecasts have been {trend_direction} over the past {trend_days} days

Market Data:
  - YES price: {yes_price}
  - NO price: {no_price}
  - Edge (estimate - market): {edge:.1%}

This is timestep {timestep} of 5. You have {remaining} timesteps remaining.

{prior_decisions_section}

The calibration bundle gives you structured data with uncertainty quantification. Use it to form YOUR OWN probability estimate - you may agree, disagree, or adjust. Consider:
- Is the confidence interval narrow enough to justify a trade?
- Does the forecast bias affect your decision?
- Is the historical sample size sufficient to trust the estimate?
- Should you wait for more data (later timesteps) or act now?

Respond ONLY with a JSON object:
{{"decision": "buy_yes" | "buy_no" | "skip", "estimated_prob": float, "confidence": float, "reasoning": string}}

estimated_prob: YOUR estimate (informed by but not necessarily equal to TraderBot's)
confidence: how confident you are (0.0 to 1.0)
reasoning: brief explanation of how you used the calibration bundle"""

# --- BinCal computation ---

_BINS = [
    (float("-inf"), -8, "(-inf,-8)"),
    (-8, -4, "[-8,-4)"),
    (-4, -2, "[-4,-2)"),
    (-2, 0, "[-2,0)"),
    (0, 2, "[0,2)"),
    (2, 4, "[2,4)"),
    (4, 8, "[4,8)"),
    (8, float("inf"), "[8,+inf)"),
]


def _sigmoid(delta, k=0.4):
    return 1.0 / (1.0 + math.exp(-k * delta))


def _compute_bincal(conn, ticker, strike_type, threshold, forecast_temp):
    """Compute BinCal estimate using v2 delta semantics.

    Delta is always positive when forecast supports YES.
    Falls back to sigmoid when calibration_bins table lacks data.
    """
    if forecast_temp is None:
        return {"estimated_prob": 0.5, "confidence": 0.1, "sample_count": 0,
                "historical_accuracy": "no forecast data", "ci_lower": 0.3, "ci_upper": 0.7}

    delta = _compute_delta(strike_type, forecast_temp, threshold)

    bin_label = None
    for lower, upper, label in _BINS:
        if lower <= delta < upper:
            bin_label = label
            break
    if bin_label is None:
        bin_label = _BINS[-1][2]

    # Try calibration_bins (may not exist in v2 DB)
    try:
        row = conn.execute(
            "SELECT count, actual_rate FROM calibration_bins WHERE methodology='bin_cal' AND bin_label=?",
            (bin_label,),
        ).fetchone()
    except sqlite3.OperationalError:
        row = None

    if row and row[0] >= 10:
        count, actual_rate = row
        correct = round(actual_rate * count)
        alpha = correct + 1
        beta_param = count - correct + 1
        estimated_prob = alpha / (alpha + beta_param)
        confidence = min(1.0, count / 50.0)
        var = (alpha * beta_param) / ((alpha + beta_param) ** 2 * (alpha + beta_param + 1))
        std = var ** 0.5
        ci_lower = max(0.01, estimated_prob - 1.96 * std)
        ci_upper = min(0.99, estimated_prob + 1.96 * std)
        return {"estimated_prob": estimated_prob, "confidence": confidence,
                "sample_count": count, "historical_accuracy": f"{actual_rate:.0%} ({count} forecasts)",
                "ci_lower": ci_lower, "ci_upper": ci_upper}

    prob = _sigmoid(delta)
    abs_delta = abs(delta)
    if abs_delta < 1:
        conf = 0.2 + 0.1 * abs_delta
    elif abs_delta < 4:
        conf = 0.3 + 0.1 * (abs_delta - 1)
    else:
        conf = min(0.85, 0.6 + 0.05 * (abs_delta - 4))
    ci_width = 0.4 - 0.05 * min(abs_delta, 6)
    return {"estimated_prob": prob, "confidence": conf,
            "sample_count": row[0] if row else 0,
            "historical_accuracy": f"{row[1]:.0%}" if row and row[1] is not None else "insufficient data",
            "ci_lower": max(0.01, prob - ci_width / 2), "ci_upper": min(0.99, prob + ci_width / 2)}


# --- LLM call ---

_OLLAMA_CLOUD_URL = "https://ollama.com/api/generate"
_OLLAMA_API_KEY = "a805f58ea5514f149e59bf61c3d4945a.ZASFClNBFdSaMsi3XNgYoNAI"


def _call_ollama(url, prompt, model, timeout=_REQUEST_TIMEOUT):
    """Call Ollama. Tries cloud first (fast, no local bottleneck), falls back to local."""
    payload_dict = {"model": model, "prompt": prompt, "stream": False}
    cloud_headers = {"Authorization": f"Bearer {_OLLAMA_API_KEY}", "Content-Type": "application/json"}

    # Try cloud first
    try:
        if _HAS_HTTPX:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(_OLLAMA_CLOUD_URL, json=payload_dict, headers=cloud_headers)
                resp.raise_for_status()
                data = resp.json()
                return data.get("response", "")
        else:
            payload = json.dumps(payload_dict).encode()
            req = urllib.request.Request(_OLLAMA_CLOUD_URL, data=payload, headers={**{"Content-Type": "application/json"}, **{"Authorization": f"Bearer {_OLLAMA_API_KEY}"}})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
                return data.get("response", "")
    except Exception as e:
        logger.debug("Cloud Ollama failed, trying local: %s", e)

    # Fallback to local Ollama
    local_url = f"{url}/api/generate"
    try:
        if _HAS_HTTPX:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(local_url, json=payload_dict)
                resp.raise_for_status()
                data = resp.json()
                return data.get("response", "")
        else:
            payload = json.dumps(payload_dict).encode()
            req = urllib.request.Request(local_url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
                return data.get("response", "")
    except Exception as e:
        logger.warning("Both cloud and local Ollama failed: %s", e)
        return ""


def _parse_agent_response(raw):
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if m:
        raw = m.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = raw[start:end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"decision": "skip", "estimated_prob": 0.5, "confidence": 0.1, "reasoning": "JSON parse error"}


# --- Forecast evolution ---

def _compute_forecast_evolution(conn, ticker, current_timestep):
    """Compute forecast trend from v2 forecasts table."""
    rows = conn.execute(
        "SELECT timestep, forecast_temp_f FROM forecasts WHERE ticker=? AND timestep<=? ORDER BY timestep",
        (ticker, current_timestep),
    ).fetchall()
    if len(rows) < 2:
        return {"trend_direction": "unknown", "trend_days": 0, "forecast_evolution": "insufficient data", "ensemble_spread": 2.0}
    temps = [r[1] for r in rows if r[1] is not None]
    if len(temps) < 2:
        return {"trend_direction": "stable", "trend_days": 0, "forecast_evolution": "no change", "ensemble_spread": 2.0}
    mid = len(temps) // 2
    early_avg = sum(temps[:mid]) / mid if mid > 0 else temps[0]
    late_avg = sum(temps[mid:]) / (len(temps) - mid) if len(temps) > mid else temps[-1]
    delta = late_avg - early_avg
    if abs(delta) < 1.0:
        direction = "stable"
    elif delta > 0:
        direction = "rising"
    else:
        direction = "falling"
    spread = statistics.stdev(temps) if len(temps) >= 2 else 2.0
    evolution_parts = [f"T{r[0]}: {r[1]:.1f}\u00b0F" for r in rows if r[1] is not None]
    evolution = " -> ".join(evolution_parts)
    return {"trend_direction": direction, "trend_days": len(temps) - 1, "forecast_evolution": evolution, "ensemble_spread": round(spread, 1)}


def _build_strike_description(strike_type: str, threshold: float) -> str:
    """Human-readable description of the strike type for prompts."""
    if strike_type == "between":
        return f"Settles YES if high temp is in [{int(threshold)}, {int(threshold)+1})\u00b0F band"
    elif strike_type == "less":
        return f"Settles YES if high temp < {int(threshold)}\u00b0F"
    elif strike_type == "greater":
        return f"Settles YES if high temp > {int(threshold)}\u00b0F"
    else:
        return f"Settles YES if high temp crosses {threshold}\u00b0F"


# --- Treatment runner ---

def run_treatment(db_path, treatment, ollama_url="http://localhost:11434", model=_OLLAMA_MODEL, output=None):
    if treatment not in TREATMENTS:
        raise ValueError(f"Unknown treatment '{treatment}'. Available: {', '.join(TREATMENTS)}")
    conn = get_connection(str(db_path))
    conn.execute("""CREATE TABLE IF NOT EXISTS treatment_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL, timestep INTEGER NOT NULL, treatment TEXT NOT NULL,
        decision TEXT NOT NULL, estimated_prob REAL NOT NULL, confidence REAL NOT NULL,
        reasoning TEXT, forecast_temp REAL, delta REAL, yes_price REAL, no_price REAL,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (ticker) REFERENCES markets(ticker),
        UNIQUE(ticker, timestep, treatment))""")
    conn.commit()
    markets = conn.execute("SELECT ticker FROM markets ORDER BY ticker").fetchall()
    results = []
    for (ticker,) in markets:
        market = get_market(conn, ticker)
        if not market:
            logger.warning("No market data for %s, skipping", ticker)
            continue

        strike_type = market["strike_type"]
        threshold = market["threshold"]
        city_name = market["city"]
        settlement_result = market.get("result", "unknown")

        # Prefer title from markets table, fallback to constructed question
        title = market.get("title")
        if title:
            question = f"Market: {title}"
        else:
            question = _build_market_question(strike_type, city_name, threshold)

        market_decisions = []
        for timestep in range(0, NUM_TIMESTEPS):
            # Skip timesteps already completed for this treatment+ticker
            existing = conn.execute(
                "SELECT 1 FROM treatment_decisions WHERE ticker=? AND timestep=? AND treatment=?",
                (ticker, timestep, treatment),
            ).fetchone()
            if existing:
                logger.debug("Skipping %s ts=%d for %s (already completed)", ticker, timestep, treatment)
                continue

            forecast = _load_forecast(conn, ticker, timestep)
            if not forecast:
                logger.warning("No forecast for %s ts=%d, skipping", ticker, timestep)
                continue

            prices_row = get_market_prices(conn, ticker, timestep)
            if prices_row:
                yes_price = prices_row.get("yes_price", 0.5)
                no_price = 1.0 - yes_price
            else:
                yes_price, no_price = 0.5, 0.5

            forecast_temp = forecast.get("forecast_temp_f")
            if forecast_temp is None:
                logger.warning("No forecast_temp_f for %s ts=%d, skipping", ticker, timestep)
                continue

            delta = _compute_delta(strike_type, forecast_temp, threshold)
            remaining = NUM_TIMESTEPS - timestep - 1
            days_before = forecast.get("days_before", remaining + 1)

            prior_lines = [f"  Timestep {d['timestep']}: decided {d['decision']}, prob={d.get('estimated_prob', '?')}, confidence={d.get('confidence', '?')}" for d in market_decisions[-5:]]
            prior_section = "Your prior decisions for this market:\n" + "\n".join(prior_lines) if prior_lines else "No prior decisions for this market."

            prompt = _build_prompt(treatment, market, question, city_name, strike_type,
                                   threshold, forecast_temp, days_before,
                                   yes_price, no_price, delta,
                                   timestep, remaining, prior_section, conn, ticker)

            raw_response = _call_ollama(ollama_url, prompt, model)
            if not raw_response:
                decision = {"decision": "skip", "estimated_prob": 0.5, "confidence": 0.1, "reasoning": "LLM unavailable"}
            else:
                decision = _parse_agent_response(raw_response)
                decision.setdefault("decision", "skip")
                decision.setdefault("estimated_prob", 0.5)
                decision.setdefault("confidence", 0.1)
            decision["estimated_prob"] = max(0.01, min(0.99, float(decision.get("estimated_prob", 0.5))))
            decision["confidence"] = max(0.01, min(1.0, float(decision.get("confidence", 0.5))))
            decision.update({"timestep": timestep, "ticker": ticker, "treatment": treatment,
                             "forecast_temp": forecast_temp, "delta": delta, "yes_price": yes_price, "no_price": no_price})
            market_decisions.append(decision)
            conn.execute("""INSERT OR REPLACE INTO treatment_decisions
                (ticker, timestep, treatment, decision, estimated_prob, confidence, reasoning, forecast_temp, delta, yes_price, no_price, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ticker, timestep, treatment, decision["decision"], decision["estimated_prob"],
                 decision["confidence"], decision.get("reasoning", ""), decision.get("forecast_temp"),
                 decision.get("delta"), decision.get("yes_price"), decision.get("no_price"),
                 datetime.now(timezone.utc).isoformat()))
            conn.commit()
            logger.info("  %s ts=%d: decision=%s prob=%.3f conf=%.3f", ticker, timestep, decision["decision"], decision["estimated_prob"], decision["confidence"])

        results.append({"ticker": ticker, "treatment": treatment, "settlement_result": settlement_result,
                        "strike_type": strike_type, "threshold": threshold,
                        "city": city_name, "decisions": market_decisions})
        logger.info("Market %s (%s): %d decisions, settled %s", ticker, treatment, len(market_decisions), settlement_result)

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
        logger.info("Wrote %d market results to %s", len(results), out_path)
    conn.close()
    return results


def _build_prompt(treatment, market, question, city_name, strike_type,
                  threshold, forecast_temp, days_before,
                  yes_price, no_price, delta,
                  timestep, remaining, prior_section, conn, ticker):
    resolution_date = market.get("resolution_date", "unknown")
    strike_type_description = _build_strike_description(strike_type, threshold)

    common = {
        "question": question,
        "city_name": city_name,
        "resolution_date": resolution_date,
        "strike_type_description": strike_type_description,
        "forecast_temp_f": f"{forecast_temp:.1f}" if forecast_temp is not None else "N/A",
        "days_before": days_before,
        "yes_price": yes_price,
        "no_price": no_price,
        "delta": delta,
        "timestep": timestep,
        "remaining": remaining,
        "prior_decisions_section": prior_section,
    }

    if treatment == "control":
        return CONTROL_PROMPT.format(**common)
    elif treatment == "raw_data":
        return RAW_DATA_PROMPT.format(**common)
    elif treatment == "structured_prob":
        cal = _compute_bincal(conn, ticker, strike_type, threshold, forecast_temp)
        edge = abs(cal["estimated_prob"] - yes_price)
        common.update({"estimated_prob": cal["estimated_prob"], "confidence": cal["confidence"],
                       "sample_count": cal["sample_count"], "historical_accuracy": cal["historical_accuracy"], "edge": edge})
        return STRUCTURED_PROB_PROMPT.format(**common)
    elif treatment == "calibration_bundle":
        cal = _compute_bincal(conn, ticker, strike_type, threshold, forecast_temp)
        evo = _compute_forecast_evolution(conn, ticker, timestep)
        edge = abs(cal["estimated_prob"] - yes_price)
        bias_direction = "above threshold trending warmer" if delta > 0 else "below threshold trending cooler"
        if abs(delta) < 1:
            bias_direction = "near threshold with mixed signals"
        common.update({"estimated_prob": cal["estimated_prob"], "confidence": cal["confidence"],
                       "sample_count": cal["sample_count"], "historical_accuracy": cal["historical_accuracy"],
                       "ci_lower": cal["ci_lower"], "ci_upper": cal["ci_upper"], "edge": edge,
                       "forecast_bias": f"{delta:+.1f}\u00b0F from threshold", "bias_direction": bias_direction,
                       "ensemble_spread": evo["ensemble_spread"], "forecast_evolution": evo["forecast_evolution"],
                       "trend_direction": evo["trend_direction"], "trend_days": evo["trend_days"]})
        return CALIBRATION_BUNDLE_PROMPT.format(**common)
    else:
        raise ValueError(f"Unknown treatment: {treatment}")


def score_treatment(results):
    """Score treatment results using markets.result (yes/no)."""
    total_decisions, trades, skips, pnl_cents = 0, 0, 0, 0
    correct_predictions, total_traded = 0, 0
    brier_scores = []
    for market in results:
        settlement = market["settlement_result"]
        for d in market["decisions"]:
            total_decisions += 1
            prob = d["estimated_prob"]
            if d["decision"] == "skip":
                skips += 1
                continue
            trades += 1
            actual_outcome = 1.0 if settlement == "yes" else 0.0
            brier_scores.append((prob - actual_outcome) ** 2)
            yes_price = d.get("yes_price", 0.5)
            trade_correct = False
            if d["decision"] == "buy_yes":
                if settlement == "yes":
                    pnl_cents += int((1.0 - yes_price) * 100)
                    trade_correct = True
                else:
                    pnl_cents -= int(yes_price * 100)
            elif d["decision"] == "buy_no":
                if settlement == "no":
                    pnl_cents += int(yes_price * 100)
                    trade_correct = True
                else:
                    pnl_cents -= int((1.0 - yes_price) * 100)
            if trade_correct:
                correct_predictions += 1
            total_traded += 1
    avg_brier = sum(brier_scores) / len(brier_scores) if brier_scores else None
    win_rate = correct_predictions / total_traded if total_traded > 0 else None
    return {"treatment": results[0]["treatment"] if results else "unknown",
            "total_decisions": total_decisions, "trades": trades, "skips": skips,
            "skip_rate": skips / total_decisions if total_decisions > 0 else 0,
            "brier_score": round(avg_brier, 4) if avg_brier is not None else None,
            "pnl_cents": pnl_cents, "pnl_dollars": round(pnl_cents / 100, 2),
            "win_rate": round(win_rate, 4) if win_rate is not None else None,
            "total_traded": total_traded, "correct_predictions": correct_predictions}


def main():
    parser = argparse.ArgumentParser(description="Treatment experiment harness (v2 schema)")
    parser.add_argument("--db", required=True, help="Path to v2 experiment_data.db")
    parser.add_argument("--treatment", required=True, choices=TREATMENTS)
    parser.add_argument("--output", required=True, help="Path to output JSONL file")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--model", default=_OLLAMA_MODEL)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    results = run_treatment(db_path=args.db, treatment=args.treatment,
                            ollama_url=args.ollama_url, model=args.model, output=args.output)
    scores = score_treatment(results)
    print(f"\n{'='*60}")
    print(f"Treatment: {args.treatment}")
    print(f"  Markets: {len(results)}")
    print(f"  Total decisions: {scores['total_decisions']}")
    print(f"  Trades: {scores['trades']}, Skips: {scores['skips']} (skip rate: {scores['skip_rate']:.1%})")
    if scores["brier_score"] is not None:
        print(f"  Brier score: {scores['brier_score']:.4f}")
    print(f"  P&L: ${scores['pnl_dollars']:.2f}")
    if scores["win_rate"] is not None:
        print(f"  Win rate: {scores['win_rate']:.1%} ({scores['correct_predictions']}/{scores['total_traded']})")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
