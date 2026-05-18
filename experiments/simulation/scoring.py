"""Scoring pipeline for simulation harness output.

Reads JSONL decision records and experiment DB settlement/price data,
computing per-methodology metrics: Brier score, calibration curve,
edge realization rate, P&L, entry timing analysis, and confidence-weighted
accuracy.
"""

import sys
from pathlib import Path

# Ensure experiments/ is on the path so `python -m simulation.scoring` works from any cwd
_experiments_root = Path(__file__).resolve().parent.parent
if str(_experiments_root) not in sys.path:
    sys.path.insert(0, str(_experiments_root))

import argparse  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import sqlite3  # noqa: E402
from typing import Any  # noqa: E402


def load_jsonl(path: str) -> list[dict[str, Any]]:
    """Parse JSONL file into list of decision dicts."""
    decisions: list[dict[str, Any]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                decisions.append(json.loads(line))
    return decisions


def load_settlements(db_path: str, tickers: set[str]) -> dict[str, int]:
    """Load settlement outcomes from DB as {ticker: 0|1}."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT ticker, settlement_result FROM markets "
        "WHERE settlement_result IS NOT NULL"
    )
    settlements: dict[str, int] = {}
    for row in cursor:
        t = row["ticker"]
        if t in tickers:
            settlements[t] = 1 if row["settlement_result"] == "yes" else 0
    conn.close()
    return settlements


def load_prices(db_path: str) -> dict[tuple[str, int], float]:
    """Load market prices as {(ticker, timestep): yes_price}."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT ticker, timestep, yes_price FROM market_prices")
    prices: dict[tuple[str, int], float] = {}
    for row in cursor:
        prices[(row["ticker"], row["timestep"])] = row["yes_price"]
    conn.close()
    return prices


def compute_brier(
    decisions: list[dict[str, Any]], settlements: dict[str, int]
) -> float | None:
    """Mean of (estimated_prob - actual_outcome)^2 across all decisions."""
    squared_errors: list[float] = []
    for d in decisions:
        actual = settlements.get(d["ticker"])
        if actual is None:
            continue
        squared_errors.append((d["estimated_prob"] - actual) ** 2)
    if not squared_errors:
        return None
    return sum(squared_errors) / len(squared_errors)


def compute_calibration(
    decisions: list[dict[str, Any]], settlements: dict[str, int]
) -> dict[str, Any]:
    """Bucket predictions into deciles; report predicted vs actual win rate.

    Also fits a simple OLS slope (actual ~ predicted) as a summary calibration
    statistic: 1.0 = perfect, < 1 = overconfident.
    """
    buckets: dict[int, dict[str, list[float]]] = {
        i: {"predicted": [], "actual": []} for i in range(10)
    }

    for d in decisions:
        actual = settlements.get(d["ticker"])
        if actual is None:
            continue
        p = d["estimated_prob"]
        idx = min(int(p * 10), 9)
        buckets[idx]["predicted"].append(p)
        buckets[idx]["actual"].append(float(actual))

    cal_buckets: list[dict[str, Any]] = []
    all_predicted: list[float] = []
    all_actual: list[float] = []

    for i in range(10):
        preds = buckets[i]["predicted"]
        actuals = buckets[i]["actual"]
        if preds:
            bucket_pred_rate = sum(preds) / len(preds)
            bucket_actual_rate = sum(actuals) / len(actuals)
            cal_buckets.append(
                {
                    "bucket": i,
                    "range": f"{i / 10:.1f}-{(i + 1) / 10:.1f}",
                    "count": len(preds),
                    "predicted_rate": round(bucket_pred_rate, 4),
                    "actual_rate": round(bucket_actual_rate, 4),
                }
            )
            all_predicted.extend(preds)
            all_actual.extend(actuals)

    slope = None
    if len(all_predicted) >= 2:
        n = len(all_predicted)
        sum_x = sum(all_predicted)
        sum_y = sum(all_actual)
        sum_xy = sum(x * y for x, y in zip(all_predicted, all_actual, strict=True))
        sum_x2 = sum(x * x for x in all_predicted)
        denom = n * sum_x2 - sum_x * sum_x
        if denom != 0:
            slope = (n * sum_xy - sum_x * sum_y) / denom

    return {"buckets": cal_buckets, "slope": round(slope, 4) if slope is not None else None}


def compute_edge_realization(
    decisions: list[dict[str, Any]],
    settlements: dict[str, int],
    prices: dict[tuple[str, int], float],
) -> float | None:
    """% of positive-edge trades where the market settled in the predicted direction.

    Edge for YES = estimated_prob - yes_price.
    Edge for NO  = (1 - estimated_prob) - no_price.
    """
    positive_edge = 0
    realized = 0

    for d in decisions:
        actual = settlements.get(d["ticker"])
        if actual is None:
            continue

        key = (d["ticker"], d["timestep"])
        yes_price = prices.get(key)
        if yes_price is None:
            continue

        decision = d["decision"]
        if decision == "YES":
            edge = d["estimated_prob"] - yes_price
            predicted_correct = actual == 1
        else:
            edge = (1.0 - d["estimated_prob"]) - (1.0 - yes_price)
            predicted_correct = actual == 0

        if edge > 0:
            positive_edge += 1
            if predicted_correct:
                realized += 1

    if positive_edge == 0:
        return None
    return realized / positive_edge


def compute_pnl(
    decisions: list[dict[str, Any]],
    settlements: dict[str, int],
    prices: dict[tuple[str, int], float],
) -> dict[str, Any]:
    """Cumulative P&L and per-timestep average P&L."""
    total_pnl = 0
    pnl_by_timestep: dict[int, list[int]] = {}

    for d in decisions:
        pos_size = d.get("position_size_cents")
        if not pos_size:
            continue

        actual = settlements.get(d["ticker"])
        if actual is None:
            continue

        key = (d["ticker"], d["timestep"])
        yes_price = prices.get(key)
        if yes_price is None:
            continue

        decision = d["decision"]
        if decision == "YES":
            pnl_cents = pos_size * (1.0 - yes_price) if actual == 1 else -pos_size * yes_price
        else:
            pnl_cents = pos_size * yes_price if actual == 0 else -pos_size * (1.0 - yes_price)

        pnl_int = round(pnl_cents)
        total_pnl += pnl_int

        ts = d["timestep"]
        if ts not in pnl_by_timestep:
            pnl_by_timestep[ts] = []
        pnl_by_timestep[ts].append(pnl_int)

    timing: dict[str, float] = {}
    for ts in sorted(pnl_by_timestep):
        vals = pnl_by_timestep[ts]
        timing[str(ts)] = round(sum(vals) / len(vals))

    return {"total_pnl_cents": total_pnl, "timing_analysis": timing}


def pearson_correlation(xs: list[float], ys: list[float]) -> float | None:
    """Compute Pearson correlation coefficient; None if undefined."""
    n = len(xs)
    if n < 2:
        return None

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    std_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    std_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))

    if std_x == 0 or std_y == 0:
        return None
    return cov / (std_x * std_y)


def compute_confidence_correlation(
    decisions: list[dict[str, Any]], settlements: dict[str, int]
) -> float | None:
    """Pearson correlation between confidence and absolute error.

    A negative correlation is desirable: higher confidence → smaller error.
    """
    confidences: list[float] = []
    errors: list[float] = []

    for d in decisions:
        actual = settlements.get(d["ticker"])
        if actual is None:
            continue
        confidences.append(d["confidence"])
        errors.append(abs(d["estimated_prob"] - actual))

    if not confidences:
        return None
    return pearson_correlation(confidences, errors)


def extract_methodology(decisions: list[dict[str, Any]]) -> str:
    """Extract methodology name from the first decision."""
    for d in decisions:
        if "methodology" in d:
            return str(d["methodology"])
    return "unknown"


def score(input_path: str, db_path: str) -> dict[str, Any]:
    """Run the full scoring pipeline and return a result dict."""
    decisions = load_jsonl(input_path)
    methodology = extract_methodology(decisions) if decisions else "unknown"

    if not decisions:
        return {
            "methodology": methodology,
            "num_decisions": 0,
            "brier_score": None,
            "calibration": {"buckets": [], "slope": None},
            "edge_realization_rate": None,
            "total_pnl_cents": 0,
            "timing_analysis": {},
            "confidence_correlation": None,
        }

    tickers = {d["ticker"] for d in decisions}
    settlements = load_settlements(db_path, tickers)
    prices = load_prices(db_path)

    brier = compute_brier(decisions, settlements)
    calibration = compute_calibration(decisions, settlements)
    edge_rate = compute_edge_realization(decisions, settlements, prices)
    pnl_data = compute_pnl(decisions, settlements, prices)
    conf_corr = compute_confidence_correlation(decisions, settlements)

    return {
        "methodology": methodology,
        "num_decisions": len(decisions),
        "brier_score": round(brier, 4) if brier is not None else None,
        "calibration": calibration,
        "edge_realization_rate": round(edge_rate, 4) if edge_rate is not None else None,
        "total_pnl_cents": pnl_data["total_pnl_cents"],
        "timing_analysis": pnl_data["timing_analysis"],
        "confidence_correlation": round(conf_corr, 4) if conf_corr is not None else None,
    }


def format_markdown_table(results: dict[str, Any]) -> str:
    """Render results as a markdown table."""
    timing = results.get("timing_analysis", {})
    timing_str = ", ".join(
        f"t{ts}={v}" for ts, v in sorted(timing.items(), key=lambda kv: int(kv[0]))
    )
    slope = results.get("calibration", {}).get("slope", "N/A")

    lines = [
        "| Metric | Value |",
        "|--------|-------|",
        f"| Methodology | {results['methodology']} |",
        f"| Decisions | {results['num_decisions']} |",
        f"| Brier Score | {results['brier_score']} |",
        f"| Calibration Slope | {slope} |",
        f"| Edge Realization Rate | {results['edge_realization_rate']} |",
        f"| Total P&L (cents) | {results['total_pnl_cents']} |",
        f"| Timing P&L | {timing_str} |",
        f"| Confidence Correlation | {results['confidence_correlation']} |",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score simulation harness JSONL output against experiment DB."
    )
    parser.add_argument(
        "--input", "-i", required=True, help="Path to JSONL input file"
    )
    parser.add_argument(
        "--db", "-d",
        default="experiments/experiment_data.db",
        help="Path to experiment SQLite DB (default: experiments/experiment_data.db)",
    )
    parser.add_argument(
        "--output", "-o", help="Write JSON summary to file (default: stdout)"
    )
    parser.add_argument(
        "--markdown", "-m", action="store_true",
        help="Also print a markdown summary table to stdout",
    )

    args = parser.parse_args()

    # Resolve default DB path relative to repo root when needed
    db_path = args.db
    if not Path(db_path).exists() and not db_path.startswith("/"):
        alt = Path(__file__).resolve().parent.parent.parent / db_path
        if alt.exists():
            db_path = str(alt)

    results = score(args.input, db_path)
    json_out = json.dumps(results, indent=2, default=str)

    if args.output:
        with open(args.output, "w") as f:
            f.write(json_out)
        print(f"Results written to {args.output}")
    else:
        print(json_out)

    if args.markdown:
        print()
        print(format_markdown_table(results))


if __name__ == "__main__":
    main()
