"""P&L calculation, weighted Brier score, delta profit, and skip rate for v3 experiments."""

import sqlite3
from collections import defaultdict

POSITION_SIZE = 100


def compute_pnl(decision: str, yes_price: float, settlement: str | None) -> int:
    if decision == "skip" or settlement is None:
        return 0
    if decision == "buy_yes":
        return int(POSITION_SIZE * (1.0 - yes_price)) if settlement == "YES" else int(-POSITION_SIZE * yes_price)
    if decision == "buy_no":
        return int(POSITION_SIZE * yes_price) if settlement == "NO" else int(-POSITION_SIZE * (1.0 - yes_price))
    return 0


def compute_brier(estimated_prob: float, settlement: str) -> float:
    actual = 1.0 if settlement == "YES" else 0.0
    return (estimated_prob - actual) ** 2


def compute_delta_profit(treatment_pnl: float, control_pnl: float) -> dict:
    return {
        "treatment_pnl": treatment_pnl,
        "control_pnl": control_pnl,
        "delta_profit": treatment_pnl - control_pnl,
    }


def compute_weighted_brier(
    decisions: list[dict], settlement: str, yes_price: float
) -> float:
    if not decisions:
        return 0.0
    weight = 2.0 if 0.20 <= yes_price <= 0.80 else 0.5
    briers = [compute_brier(d["estimated_prob"], settlement) for d in decisions]
    return weight * (sum(briers) / len(briers))


def compute_skip_rate(decisions: list[dict]) -> float:
    if not decisions:
        return 0.0
    skips = sum(1 for d in decisions if d["decision"] == "skip")
    return skips / len(decisions)


def score_run(conn: sqlite3.Connection, run_id: str) -> dict:
    rows = conn.execute(
        """
        SELECT td.treatment_name, td.replicate, td.ticker, td.decision,
               td.estimated_prob, m.settlement_result, mp.yes_price
        FROM treatment_decisions td
        JOIN markets m ON td.ticker = m.ticker
        LEFT JOIN market_prices mp ON td.ticker = mp.ticker AND td.timestep = mp.timestep
        WHERE td.run_id = ?
        ORDER BY td.treatment_name, td.replicate, td.ticker
        """,
        (run_id,),
    ).fetchall()

    by_treatment: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        treatment_name, replicate, ticker, decision, est_prob, settlement, yes_price = row
        by_treatment[treatment_name].append(
            {
                "replicate": replicate,
                "ticker": ticker,
                "decision": decision,
                "estimated_prob": est_prob,
                "settlement": settlement,
                "yes_price": yes_price or 0.0,
            }
        )

    treatment_metrics: dict[str, dict] = {}
    per_market: dict[str, dict] = {}

    for treatment_name, decisions in by_treatment.items():
        by_rep: dict[int, list[dict]] = defaultdict(list)
        by_ticker: dict[str, list[dict]] = defaultdict(list)
        for d in decisions:
            by_rep[d["replicate"]].append(d)
            by_ticker[d["ticker"]].append(d)

        rep_pnls = []
        for rep_decisions in by_rep.values():
            pnl = sum(
                compute_pnl(d["decision"], d["yes_price"], d["settlement"])
                for d in rep_decisions
            )
            rep_pnls.append(pnl)

        total_pnl = sum(rep_pnls) / len(rep_pnls) if rep_pnls else 0.0
        skip_rate = compute_skip_rate(decisions)

        unique_yes_prices = {d["yes_price"] for d in decisions}
        rep_yes_price = (
            sum(unique_yes_prices) / len(unique_yes_prices)
            if unique_yes_prices
            else 0.0
        )
        settlement = decisions[0]["settlement"] if decisions else None
        weighted_brier = (
            compute_weighted_brier(decisions, settlement, rep_yes_price)
            if settlement
            else 0.0
        )

        treatment_metrics[treatment_name] = {
            "total_pnl": total_pnl,
            "skip_rate": skip_rate,
            "weighted_brier": weighted_brier,
        }

    control_pnl = treatment_metrics.get("control", {}).get("total_pnl", 0.0)
    model_metrics = {
        k: v
        for k, v in treatment_metrics.items()
        if k != "control"
    }
    best_model = max(
        model_metrics.items(),
        key=lambda kv: kv[1]["total_pnl"],
        default=(None, {"total_pnl": 0.0}),
    )
    best_pnl = best_model[1]["total_pnl"]

    if by_treatment:
        for ticker, t_decisions in by_ticker.items():
            per_market[ticker] = {
                "settlement": t_decisions[0]["settlement"],
                "decision_count": len(t_decisions),
            }

    return {
        "treatments": treatment_metrics,
        "delta_profit": best_pnl - control_pnl,
        "per_market": per_market,
    }
