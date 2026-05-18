"""Methodology-agnostic simulation orchestrator.

Runs 25 markets × 10 timesteps per methodology, records outputs and agent
decisions, then resolves against settlement_actuals AFTER all timesteps
complete. Settlement data is NEVER exposed to the agent during simulation.
"""

import argparse
import importlib
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from experiments.methodologies.base import MethodologyResult
from experiments.methodologies.db_utils import (
    get_connection,
    get_market,
    get_market_prices,
    record_agent_decision,
    record_methodology_output,
)
from experiments.methodologies.forecast_loader import load_all_forecasts, load_forecast

METHODOLOGY_REGISTRY = {
    "bin_cal": ("experiments.methodologies.bin_cal", "BinCalMethodology"),
    "logistic_reg": ("experiments.methodologies.logistic_reg", "LogisticRegMethodology"),
    "llm_synthesis": ("experiments.methodologies.llm_synthesis", "LLMSynthesisMethodology"),
    "ensemble": ("experiments.methodologies.ensemble", "EnsembleMethodology"),
}

NUM_TIMESTEPS = 10


def load_methodology(name: str, db_path: Path):
    """Dynamically import and instantiate a methodology by name."""
    if name not in METHODOLOGY_REGISTRY:
        raise ValueError(
            f"Unknown methodology '{name}'. "
            f"Available: {', '.join(METHODOLOGY_REGISTRY)}"
        )
    module_path, class_name = METHODOLOGY_REGISTRY[name]
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(db_path)


def _build_agent_context(
    market: dict,
    forecast: dict,
    prices: dict | None,
    meth_result: MethodologyResult,
    prior_decisions: list[dict],
) -> dict:
    """Construct agent context from available data, EXCLUDING settlement info."""
    return {
        "ticker": market["ticker"],
        "question": market["question"],
        "city": market["city"],
        "strike_value": market["strike_value"],
        "strike_type": market["strike_type"],
        "market_type": market.get("market_type"),
        "resolution_date": market["resolution_date"],
        "close_time": market["close_time"],
        "forecast": {
            "forecast_date": forecast.get("forecast_date"),
            "target_date": forecast.get("target_date"),
            "temp_max_f": forecast.get("temp_max_f"),
            "temp_min_f": forecast.get("temp_min_f"),
            "precip_mm": forecast.get("precip_mm"),
            "wind_speed_max_kmh": forecast.get("wind_speed_max_kmh"),
            "humidity_max_pct": forecast.get("humidity_max_pct"),
            "weather_code": forecast.get("weather_code"),
            "source": forecast.get("source"),
        },
        "prices": {
            "yes_price": prices.get("yes_price") if prices else None,
            "no_price": prices.get("no_price") if prices else None,
            "volume": prices.get("volume") if prices else None,
            "open_interest": prices.get("open_interest") if prices else None,
        },
        "methodology_output": {
            "estimated_prob": meth_result.estimated_prob,
            "confidence": meth_result.confidence,
            "reasoning": meth_result.reasoning,
        },
        "prior_decisions": prior_decisions,
    }


def _make_agent_decision(
    methodology_name: str,
    agent_context: dict,
) -> dict:
    """Derive a simulated agent decision from methodology output and context.

    Simple model: agent bets YES when estimated_prob exceeds market yes_price,
    bets NO when below, and skips when edge is marginal. Position size scales
    with edge magnitude and confidence.
    """
    estimated_prob = agent_context["methodology_output"]["estimated_prob"]
    confidence = agent_context["methodology_output"]["confidence"]
    yes_price = agent_context["prices"].get("yes_price")

    if yes_price is None:
        decision = "skip"
        edge = 0.0
        position_size_cents = 0
    else:
        edge = estimated_prob - yes_price
        if abs(edge) < 0.02:
            decision = "skip"
            position_size_cents = 0
        elif edge > 0:
            decision = "buy_yes"
            position_size_cents = min(500, int(abs(edge) * confidence * 1000))
        else:
            decision = "buy_no"
            position_size_cents = min(500, int(abs(edge) * confidence * 1000))

    return {
        "decision": decision,
        "estimated_prob": estimated_prob,
        "confidence": confidence,
        "edge_estimate": round(edge, 4),
        "position_size_cents": position_size_cents,
        "reasoning": json.dumps({
            "edge_direction": "positive" if edge > 0 else "negative" if edge < 0 else "neutral",
            "edge_magnitude": round(abs(edge), 4),
            "confidence": confidence,
        }),
    }


def _resolve_market(db: sqlite3.Connection, ticker: str) -> dict | None:
    """Fetch settlement actuals for a market — ONLY called after all timesteps."""
    row = db.execute(
        "SELECT * FROM settlement_actuals WHERE ticker = ?",
        (ticker,),
    ).fetchone()
    return dict(row) if row else None


def run_simulation(
    db_path: Path,
    methodology_name: str,
    output_path: Path | None = None,
) -> list[dict]:
    """Run the full simulation: all markets × 10 timesteps × 1 methodology.

    Args:
        db_path: Path to the experiment SQLite database.
        methodology_name: Short name of the methodology (e.g. 'bin_cal').
        output_path: Optional path for JSONL output. Defaults to
            experiments/simulation/results_{methodology_name}.jsonl

    Returns:
        List of result dicts, one per market.
    """
    db = get_connection(db_path)
    methodology = load_methodology(methodology_name, db_path)
    results: list[dict] = []

    rows = db.execute("SELECT ticker FROM markets ORDER BY ticker").fetchall()
    tickers = [row["ticker"] for row in rows]

    for ticker in tickers:
        market = get_market(db, ticker)
        if market is None:
            continue

        forecasts = load_all_forecasts(db, ticker)
        if not forecasts:
            continue

        prior_decisions: list[dict] = []

        # --- Timestep loop: settlement data is NOT accessed here ---
        for timestep in range(1, NUM_TIMESTEPS + 1):
            forecast = load_forecast(db, ticker, timestep)
            if not forecast:
                continue

            prices = get_market_prices(db, ticker, timestep)

            meth_result = methodology.estimate(
                ticker=ticker,
                forecast=forecast,
                timestep=timestep,
                prior_decisions=prior_decisions,
            )

            record_methodology_output(
                db,
                ticker,
                timestep,
                methodology_name,
                {
                    "estimated_prob": meth_result.estimated_prob,
                    "confidence": meth_result.confidence,
                    "reasoning_data": json.dumps(meth_result.reasoning),
                },
            )

            # Build agent context WITHOUT settlement data
            agent_context = _build_agent_context(
                market=market,
                forecast=forecast,
                prices=prices,
                meth_result=meth_result,
                prior_decisions=prior_decisions,
            )

            decision = _make_agent_decision(methodology_name, agent_context)

            record_agent_decision(
                db,
                ticker,
                timestep,
                methodology_name,
                decision,
            )

            prior_decisions.append({
                "timestep": timestep,
                "decision": decision["decision"],
                "estimated_prob": decision["estimated_prob"],
                "edge_estimate": decision["edge_estimate"],
                "position_size_cents": decision["position_size_cents"],
            })
        # --- End timestep loop ---

        # Settlement resolution — ONLY after all timesteps complete
        settlement = _resolve_market(db, ticker)
        settled = settlement is not None

        results.append({
            "ticker": ticker,
            "question": market["question"],
            "market_type": market.get("market_type"),
            "strike_value": market["strike_value"],
            "strike_type": market["strike_type"],
            "methodology": methodology_name,
            "settlement": {
                "settled": settled,
                "actual_temp_max_f": settlement.get("actual_temp_max_f") if settlement else None,
                "actual_temp_min_f": settlement.get("actual_temp_min_f") if settlement else None,
                "actual_precip_mm": settlement.get("actual_precip_mm") if settlement else None,
                "actual_weather_code": settlement.get("actual_weather_code") if settlement else None,
            } if settled else None,
            "decisions": prior_decisions,
            "num_timesteps_completed": len(prior_decisions),
        })

    db.close()

    # Write JSONL output
    if output_path is None:
        output_path = Path(__file__).parent / f"results_{methodology_name}.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "a") as f:
        for result in results:
            f.write(json.dumps(result) + "\n")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Run simulation harness for a methodology"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("experiments/experiment_data.db"),
        help="Path to experiment SQLite database",
    )
    parser.add_argument(
        "--methodology",
        type=str,
        required=True,
        choices=list(METHODOLOGY_REGISTRY.keys()),
        help="Methodology to run",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path for JSONL output file",
    )
    args = parser.parse_args()

    results = run_simulation(args.db, args.methodology, args.output)

    print(f"Simulation complete: {len(results)} markets processed")
    settled = sum(1 for r in results if r["settlement"] and r["settlement"]["settled"])
    print(f"  Settled: {settled}/{len(results)}")
    for r in results:
        n = r["num_timesteps_completed"]
        last = r["decisions"][-1]["decision"] if r["decisions"] else "none"
        print(f"  {r['ticker']}: {n} timesteps, last decision={last}")


if __name__ == "__main__":
    main()
