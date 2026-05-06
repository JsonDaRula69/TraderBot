"""Heartbeat cycle — 7-step self-review, adaptation, and health check."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from traderbot.db.decisions import DbDecision, list_by_date_range
from traderbot.kalshi.models import MarketCategory
from traderbot.learning import (
    HEARTBEAT_INTERVAL_HOURS,
    scan_for_promotions,
)
from traderbot.risk.circuit_breaker import CircuitBreaker
from traderbot.simulation.adaptation import (
    WEAK_BETA,
    BayesianAdapter,
    BinomialObservations,
)
from traderbot.updater import check_for_updates

if TYPE_CHECKING:
    import sqlite3

logger = logging.getLogger(__name__)

DEFAULT_HEARTBEAT_PATH = Path(".openclaw/workspace/HEARTBEAT_DATA.md")


# ---------------------------------------------------------------------------
# Pydantic output models
# ---------------------------------------------------------------------------


class PerformanceReview(BaseModel):
    """Step 1: Aggregated trade performance since last heartbeat."""

    model_config = ConfigDict(strict=True, extra="forbid")

    trade_count: int = 0
    win_rate: float = 0.0
    total_pnl_cents: int = 0
    avg_confidence: float = 0.0
    sharpe_ratio: float | None = None
    max_drawdown_pct: float = 0.0
    open_positions: int = 0
    deviation_flag: str = ""


class DecisionReview(BaseModel):
    """Step 2: Prediction accuracy for closed-market decisions."""

    model_config = ConfigDict(strict=True, extra="forbid")

    closed_count: int = 0
    correct_predictions: int = 0
    prediction_accuracy: float = 0.0
    open_count: int = 0
    pending_review: list[str] = Field(default_factory=list)


class AdaptationReview(BaseModel):
    """Step 3: Bayesian adaptation results."""

    model_config = ConfigDict(strict=True, extra="forbid")

    updated: bool = False
    direction: str = "maintain"
    magnitude: float = 0.0
    confidence: float = 0.0
    reasoning: str = ""
    method: str = ""
    human_review: bool = False
    variance_reset: bool = False
    skipped_reason: str = ""


class LearningPromotionReview(BaseModel):
    """Step 4: Learning promotion results."""

    model_config = ConfigDict(strict=True, extra="forbid")

    candidates_found: int = 0
    promoted: list[str] = Field(default_factory=list)
    promoted_count: int = 0


class CircuitBreakerReview(BaseModel):
    """Step 5: Circuit breaker status."""

    model_config = ConfigDict(strict=True, extra="forbid")

    level: str = "NORMAL"
    can_trade: bool = True
    daily_loss_pct: float = 0.0
    drawdown_pct: float = 0.0
    position_size_multiplier: float = 1.0
    reason: str = ""


class SystemHealthReview(BaseModel):
    """Step 6: System health and connectivity."""

    model_config = ConfigDict(strict=True, extra="forbid")

    api_connectivity: str = "unknown"
    db_integrity: str = "unknown"
    data_freshness: str = "unknown"
    alerts: list[str] = Field(default_factory=list)


class HeartbeatResult(BaseModel):
    """Complete heartbeat cycle output."""

    model_config = ConfigDict(strict=True, extra="forbid")

    timestamp: datetime
    performance: PerformanceReview = Field(default_factory=PerformanceReview)
    decisions: DecisionReview = Field(default_factory=DecisionReview)
    adaptation: AdaptationReview = Field(default_factory=AdaptationReview)
    learning_promotion: LearningPromotionReview = Field(default_factory=LearningPromotionReview)
    circuit_breaker: CircuitBreakerReview = Field(default_factory=CircuitBreakerReview)
    system_health: SystemHealthReview = Field(default_factory=SystemHealthReview)
    steps_completed: list[str] = Field(default_factory=list)
    state_path: Path | None = Field(default=None)
    state_saved: bool = Field(default=False)


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------


def step_performance_review(
    decisions: list[DbDecision],
    since: datetime | None = None,
) -> PerformanceReview:
    """Step 1: Aggregate trade outcomes, compute win rate, P&L, avg confidence."""
    executed = [d for d in decisions if d.outcome == "executed"]
    if not executed:
        return PerformanceReview()

    wins = 0
    total_pnl = 0
    confidence_sum = 0.0
    for d in executed:
        confidence_sum += d.confidence
        if d.actual_result is True:
            wins += 1
            total_pnl += (100 - d.price) * d.quantity
        elif d.actual_result is False:
            total_pnl -= d.price * d.quantity

    trade_count = len(executed)
    win_rate = wins / trade_count if trade_count else 0.0
    avg_confidence = confidence_sum / trade_count if trade_count else 0.0

    deviation_flag = ""
    if win_rate > 0.7:
        deviation_flag = "win_rate_above_expected"
    elif win_rate < 0.3 and trade_count >= 5:
        deviation_flag = "win_rate_below_expected"

    return PerformanceReview(
        trade_count=trade_count,
        win_rate=win_rate,
        total_pnl_cents=total_pnl,
        avg_confidence=avg_confidence,
        deviation_flag=deviation_flag,
    )


def step_decision_review(
    decisions: list[DbDecision],
) -> DecisionReview:
    """Step 2: Review recent decisions — prediction accuracy for closed markets."""
    closed = [d for d in decisions if d.actual_result is not None and d.outcome == "executed"]
    open_decisions = [d for d in decisions if d.actual_result is None and d.outcome == "executed"]

    correct = 0
    for d in closed:
        if (d.direction == "yes" and d.actual_result is True) or (d.direction == "no" and d.actual_result is False):
            correct += 1

    accuracy = correct / len(closed) if closed else 0.0
    pending = [d.ticker for d in open_decisions[:5]]

    return DecisionReview(
        closed_count=len(closed),
        correct_predictions=correct,
        prediction_accuracy=accuracy,
        open_count=len(open_decisions),
        pending_review=pending,
    )


def step_bayesian_adaptation(
    decisions: list[DbDecision],
    adapter: BayesianAdapter | None = None,
    dry_run: bool = False,
) -> AdaptationReview:
    """Step 3: Run Bayesian adaptation with latest observations.

    Uses Beta-Binomial update on win/loss across all executed decisions.
    """
    if not decisions:
        return AdaptationReview(skipped_reason="no decisions to adapt from")

    executed = [d for d in decisions if d.outcome == "executed"]
    if not executed:
        return AdaptationReview(skipped_reason="no executed decisions")

    successes = sum(
        1 for d in executed
        if (d.direction == "yes" and d.actual_result is True)
        or (d.direction == "no" and d.actual_result is False)
    )
    failures = len(executed) - successes

    if successes + failures < 1:
        return AdaptationReview(skipped_reason="insufficient resolved decisions")

    observations = BinomialObservations(successes=successes, failures=failures)
    engine = adapter or BayesianAdapter()

    if dry_run:
        obs_total = observations.total
        return AdaptationReview(
            updated=False,
            reasoning=f"Dry run: would update Beta-Binomial with {successes} wins, {failures} losses ({obs_total} obs)",
            skipped_reason="dry_run",
        )

    try:
        result = engine.update_beta(
            prior=WEAK_BETA,
            observations=observations,
            category=MarketCategory.ECONOMICS,
        )
        return AdaptationReview(
            updated=True,
            direction=result.direction,
            magnitude=result.magnitude,
            confidence=result.confidence,
            reasoning=result.reasoning,
            method=result.method or "",
            human_review=result.human_review,
            variance_reset=result.variance_reset,
        )
    except ValueError as exc:
        logger.warning("Bayesian adaptation skipped: %s", exc)
        return AdaptationReview(skipped_reason=str(exc))


def step_learning_promotion(
    conn: sqlite3.Connection,
    dry_run: bool = False,
) -> LearningPromotionReview:
    """Step 4: Promote learnings from pending to confirmed."""
    from traderbot.learning import promote_learning

    candidates = scan_for_promotions(conn)
    promoted_keys: list[str] = []

    if dry_run:
        return LearningPromotionReview(
            candidates_found=len(candidates),
            promoted=[f"(dry-run) {c.learning.summary[:40]}" for c in candidates],
            promoted_count=0,
        )

    for candidate in candidates:
        from traderbot.learning import get_db_pattern_key

        pattern_key = get_db_pattern_key(conn, candidate.learning.id)
        result = promote_learning(conn, candidate.learning.id)
        if result is not None:
            promoted_keys.append(pattern_key or f"learning-{candidate.learning.id}")

    return LearningPromotionReview(
        candidates_found=len(candidates),
        promoted=promoted_keys,
        promoted_count=len(promoted_keys),
    )


def step_circuit_breaker_check(
    breaker: CircuitBreaker | None = None,
) -> CircuitBreakerReview:
    """Step 5: Check circuit breaker state."""
    engine = breaker or CircuitBreaker()
    state = engine.get_state()
    return CircuitBreakerReview(
        level=state.level.name,
        can_trade=state.can_trade,
        daily_loss_pct=state.daily_loss_pct,
        drawdown_pct=state.drawdown_pct,
        position_size_multiplier=state.position_size_multiplier,
        reason=state.reason,
    )


async def step_system_health(
    db_conn: sqlite3.Connection,
) -> SystemHealthReview:
    """Step 6: Aggregate system health — API connectivity, DB integrity, data freshness."""
    alerts: list[str] = []

    # DB integrity check
    try:
        result = db_conn.execute("PRAGMA integrity_check").fetchone()
        db_ok = result is not None and result[0] == "ok"
        db_status = "ok" if db_ok else "corrupt"
    except Exception as exc:
        db_status = f"error: {exc}"
        alerts.append(f"DB integrity check failed: {exc}")

    # Data freshness: check age of most recent decision
    try:
        row = db_conn.execute(
            "SELECT MAX(timestamp) as latest FROM decisions"
        ).fetchone()
        if row is not None and row[0] is not None:
            latest = datetime.fromisoformat(row[0])
            age_hours = (datetime.now(UTC) - latest).total_seconds() / 3600
            freshness = f"last_data_{age_hours:.1f}h_ago"
            if age_hours > 24:
                alerts.append(f"Stale data: last decision {age_hours:.1f}h ago")
        else:
            freshness = "no_decisions_yet"
    except Exception:
        freshness = "unknown"

    api_status = "not_checked"
    try:
        import asyncio

        from traderbot.kalshi.client import KalshiClient
        from traderbot.kalshi.config import KalshiConfig

        config = KalshiConfig()
        client = KalshiClient(config)
        try:
            response = await asyncio.wait_for(client.get("/platform/status"), timeout=5.0)
            status = response.json() if hasattr(response, "json") else response
            api_ok = isinstance(status, dict) and status.get("status") == "alive"
        except Exception:
            try:
                response = await asyncio.wait_for(client.get("/"), timeout=5.0)
                api_ok = response.status_code < 500
            except Exception:
                api_ok = False
        finally:
            await asyncio.wait_for(client.close(), timeout=2.0)
        api_status = "ok" if api_ok else "degraded"
    except Exception:
        api_status = "unavailable"
        alerts.append("Kalshi API unreachable")

    return SystemHealthReview(
        api_connectivity=api_status,
        db_integrity=db_status,
        data_freshness=freshness,
        alerts=alerts,
    )


# ---------------------------------------------------------------------------
# Full heartbeat cycle
# ---------------------------------------------------------------------------


async def run_heartbeat_cycle(
    conn: sqlite3.Connection,
    heartbeat_path: Path | None = None,
    state_path: Path | None = None,
    since: datetime | None = None,
    dry_run: bool = False,
) -> HeartbeatResult:
    """Execute the full 7-step heartbeat cycle."""
    now = datetime.now(UTC)
    if since is None:
        since = now - timedelta(hours=HEARTBEAT_INTERVAL_HOURS)

    steps_completed: list[str] = []

    # Step 1: Performance review
    decisions = _get_decisions(conn, since)
    performance = step_performance_review(decisions, since)
    steps_completed.append("performance_review")

    # Step 2: Decision review
    decision_review = step_decision_review(decisions)
    steps_completed.append("decision_review")

    # Step 3: Bayesian adaptation
    adapter = BayesianAdapter(state_path=state_path) if state_path is not None else None
    adaptation = step_bayesian_adaptation(decisions, adapter=adapter, dry_run=dry_run)
    steps_completed.append("bayesian_adaptation")

    # Step 4: Learning promotion
    learning_promotion = step_learning_promotion(conn, dry_run=dry_run)
    steps_completed.append("learning_promotion")

    # Step 5: Circuit breaker check
    circuit_breaker = step_circuit_breaker_check()
    steps_completed.append("circuit_breaker_check")

    # Step 6: System health
    system_health = await step_system_health(conn)
    steps_completed.append("system_health")

    # Step 7: Update check (respects user-configured interval and enabled flag)
    from traderbot.update_config import UpdateConfig as _UpdateConfig

    _update_cfg = _UpdateConfig.load()
    if _update_cfg.enabled:
        update_result = check_for_updates(check_interval_hours=_update_cfg.check_interval_hours)
        if update_result:
            logger.info("Update available: v%s → v%s", update_result["current"], update_result["latest"])
    else:
        update_result = None
    steps_completed.append("update_check")

    result = HeartbeatResult(
        timestamp=now,
        performance=performance,
        decisions=decision_review,
        adaptation=adaptation,
        learning_promotion=learning_promotion,
        circuit_breaker=circuit_breaker,
        system_health=system_health,
        steps_completed=steps_completed,
    )

    # Step 8: Write HEARTBEAT_DATA.md
    hb_path = heartbeat_path or DEFAULT_HEARTBEAT_PATH
    if not dry_run:
        _write_heartbeat_md(hb_path, result)
    steps_completed.append("update_heartbeat_md")

    return HeartbeatResult(
        timestamp=result.timestamp,
        performance=result.performance,
        decisions=result.decisions,
        adaptation=result.adaptation,
        learning_promotion=result.learning_promotion,
        circuit_breaker=result.circuit_breaker,
        system_health=result.system_health,
        steps_completed=steps_completed,
    )


def _get_decisions(conn: sqlite3.Connection, since: datetime) -> list[DbDecision]:
    """Load decisions from DB since the given timestamp."""
    try:
        return list_by_date_range(conn, start=since)
    except Exception as exc:
        logger.warning("Failed to load decisions for heartbeat: %s", exc)
        return []


def _write_heartbeat_md(path: Path, result: HeartbeatResult) -> None:
    """Write structured heartbeat results to HEARTBEAT_DATA.md.

    Per OpenClaw spec, HEARTBEAT.md is an agent checklist (instructions),
    NOT a data output file. Our 7-step review data goes to HEARTBEAT_DATA.md.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    ts = result.timestamp.isoformat()
    perf = result.performance
    adapt = result.adaptation
    lrn = result.learning_promotion
    cb = result.circuit_breaker
    health = result.system_health

    # Deviation flag display
    deviation_line = ""
    if perf.deviation_flag:
        deviation_line = f"- ⚠️ Deviation: {perf.deviation_flag}\n"

    # Adaptation section
    adapt_lines = ""
    if adapt.updated:
        adapt_lines = f"- Edge threshold: {adapt.direction} (magnitude {adapt.magnitude:.4f}, confidence {adapt.confidence:.2f})\n"
        if adapt.human_review:
            adapt_lines += "- ⚠️ Drift detected — requires human review\n"
        if adapt.variance_reset:
            adapt_lines += "- ⚠️ Variance reset triggered\n"
    else:
        adapt_lines = f"- No update ({adapt.skipped_reason})\n"

    # Learning promotion section
    lrn_lines = ""
    if lrn.promoted:
        for key in lrn.promoted:
            lrn_lines += f"- Promoted: {key}\n"
    else:
        lrn_lines = "- No promotions this cycle\n"

    # Alerts
    alert_lines = ""
    for alert in health.alerts:
        alert_lines += f"- ⚠️ {alert}\n"
    if cb.level != "NORMAL":
        alert_lines += f"- ⚠️ Circuit breaker: {cb.level} — {cb.reason}\n"
    if not alert_lines:
        alert_lines = "- None\n"

    content = f"""\
# TraderBot Heartbeat Data

> 7-step self-review output. Written by `traderbot heartbeat`.
> This is NOT HEARTBEAT.md — that file is the agent checklist (instructions for the OpenClaw gateway).

## Last Heartbeat: {ts}

### Performance
- Win rate: {perf.win_rate:.0%} ({perf.trade_count} trades)
- Daily P&L: {perf.total_pnl_cents / 100:+.2f} USD
- Avg confidence: {perf.avg_confidence:.2f}
- Open positions: {perf.open_positions}
{deviation_line}
### Adaptation
{adapt_lines}
### Learnings
{lrn_lines}
### Circuit Breaker
- Level: {cb.level}
- Can trade: {cb.can_trade}
- Daily loss: {cb.daily_loss_pct:.2%}
- Drawdown: {cb.drawdown_pct:.2%}

### System Health
- API: {health.api_connectivity}
- DB: {health.db_integrity}
- Freshness: {health.data_freshness}

### Alerts
{alert_lines}
"""

    path.write_text(content)
    logger.info("Heartbeat written to %s", path)
