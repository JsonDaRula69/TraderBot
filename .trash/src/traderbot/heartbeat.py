"""Heartbeat cycle — 7-step self-review, adaptation, and health check."""

from __future__ import annotations

import contextlib
import logging
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from traderbot.db import positions
from traderbot.db.decisions import DbDecision, list_by_date_range
from traderbot.kalshi.models import MarketCategory
from traderbot.learning import (
    HEARTBEAT_INTERVAL_HOURS,
    scan_for_promotions,
)
from traderbot.paths import get_workspace_dir
from traderbot.risk.circuit_breaker import BreakerLevel, CircuitBreaker
from traderbot.simulation.adaptation import (
    WEAK_BETA,
    BayesianAdapter,
    BinomialObservations,
)
from traderbot.updater import check_for_updates

if TYPE_CHECKING:
    import sqlite3

logger = logging.getLogger(__name__)

BREAKER_ESCALATION_WEIGHTS: dict[BreakerLevel, int] = {
    BreakerLevel.SLOW: 1,
    BreakerLevel.HALT: 3,
    BreakerLevel.FULL_STOP: 5,
}

_last_processed_transition_ts: float = 0.0

# Tracks the transition timestamp of the last FULL_STOP event that triggered
# a recovery experiment, so we only fire once per escalation.
_last_full_stop_experiment_ts: float = 0.0

_MIN_MARKETS_FOR_RECOVERY = 10


def _default_heartbeat_path() -> Path:
    """Return the path to HEARTBEAT_DATA.md.

    Inside the Docker sandbox, CWD is /workspace which IS the workspace root.
    get_workspace_dir() returns CWD/.openclaw/workspace which would double-nest.
    Check if HEARTBEAT_DATA.md exists at CWD first — if yes, use that directly.
    """
    from pathlib import Path as _Path

    cwd = _Path.cwd()
    if (cwd / "HEARTBEAT_DATA.md").exists() and not (cwd / "AGENTS.md").exists():
        # We're inside the sandbox workspace — the workspace root IS CWD
        return cwd / "HEARTBEAT_DATA.md"
    return get_workspace_dir() / "HEARTBEAT_DATA.md"


DEFAULT_HEARTBEAT_PATH = _default_heartbeat_path()


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


class WsHealthReview(BaseModel):
    """Step 5.5: WS daemon health check."""

    model_config = ConfigDict(strict=True, extra="forbid")

    pid: int | None = None
    pid_alive: bool = False
    connected: bool = False
    status: str = "unknown"  # healthy, stale, disconnected, not_running


class SystemHealthReview(BaseModel):
    """Step 6: System health and connectivity."""

    model_config = ConfigDict(strict=True, extra="forbid")

    balance_cents: int | None = None
    api_connectivity: str = "unknown"
    db_integrity: str = "unknown"
    data_freshness: str = "unknown"
    alerts: list[str] = Field(default_factory=list)


class TokenStalenessReview(BaseModel):
    """Step 6.5: Profile token staleness check."""

    model_config = ConfigDict(strict=True, extra="forbid")

    token_source: str = "none"
    valid: bool = False
    expired: bool = False
    profile: str = ""
    agent: str = ""
    degraded: bool = False


class RecoveryExperimentReview(BaseModel):
    """Step 5.1: Recovery experiment triggered during FULL_STOP."""

    model_config = ConfigDict(strict=True, extra="forbid")

    triggered: bool = False
    markets_available: int = 0
    treatments_run: list[str] = Field(default_factory=list)
    significant_treatment: str = ""
    p_value: float = 1.0
    effect_size: float = 0.0
    report_path: str = ""
    skipped_reason: str = ""


class HeartbeatResult(BaseModel):
    """Complete heartbeat cycle output."""

    model_config = ConfigDict(strict=True, extra="forbid")

    timestamp: datetime
    performance: PerformanceReview = Field(default_factory=PerformanceReview)
    decisions: DecisionReview = Field(default_factory=DecisionReview)
    adaptation: AdaptationReview = Field(default_factory=AdaptationReview)
    learning_promotion: LearningPromotionReview = Field(default_factory=LearningPromotionReview)
    circuit_breaker: CircuitBreakerReview = Field(default_factory=CircuitBreakerReview)
    recovery_experiment: RecoveryExperimentReview = Field(default_factory=RecoveryExperimentReview)
    ws_health: WsHealthReview = Field(default_factory=WsHealthReview)
    system_health: SystemHealthReview = Field(default_factory=SystemHealthReview)
    token_staleness: TokenStalenessReview = Field(default_factory=TokenStalenessReview)
    steps_completed: list[str] = Field(default_factory=list)
    state_path: Path | None = Field(default=None)
    state_saved: bool = Field(default=False)


# ---------------------------------------------------------------------------
# Error summary
# ---------------------------------------------------------------------------


@dataclass
class ErrorSummary:
    """Aggregated error summary from log analysis."""

    total_by_level: dict[str, int] = field(default_factory=dict)
    top_error_codes: list[tuple[int, int]] = field(default_factory=list)
    recent_errors: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


_ERROR_CODE_RE = re.compile(r"\[E(\d+)\]")


def get_error_summary(log_path: str | Path | None = None) -> ErrorSummary:
    """Parse recent log entries and return an aggregated error summary.

    Reads the log file specified by *log_path* or ``TRADERBOT_LOG_FILE`` env var.
    Returns an empty summary when no log file is available.
    """
    import os

    if log_path is None:
        log_path = os.environ.get("TRADERBOT_LOG_FILE", "")
    if not log_path:
        return ErrorSummary()

    path = Path(log_path)
    if not path.exists():
        return ErrorSummary()

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ErrorSummary()

    total_by_level: dict[str, int] = {}
    error_codes: Counter[int] = Counter()
    recent_errors: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        level = _extract_level(stripped)
        if level is None:
            continue

        total_by_level[level] = total_by_level.get(level, 0) + 1

        if level in ("ERROR", "CRITICAL"):
            match = _ERROR_CODE_RE.search(stripped)
            if match:
                error_codes[int(match.group(1))] += 1
            if len(recent_errors) < 10:
                msg = stripped.split(" | ", 3)[-1] if " | " in stripped else stripped
                recent_errors.append(msg)

    top_error_codes = error_codes.most_common(5)
    return ErrorSummary(
        total_by_level=total_by_level,
        top_error_codes=top_error_codes,
        recent_errors=recent_errors,
    )


def _extract_level(line: str) -> str | None:
    """Extract log level from a pipe-delimited or JSON log line."""
    if " | " in line:
        parts = line.split(" | ")
        if len(parts) >= 3:
            candidate = parts[2].strip()
            if candidate in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
                return candidate
    return None


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------


def step_performance_review(
    conn: sqlite3.Connection,
    decisions: list[DbDecision],
    since: datetime | None = None,
) -> PerformanceReview:
    """Step 1: Aggregate trade outcomes, compute win rate, P&L, avg confidence, Sharpe, and max drawdown."""
    executed = [d for d in decisions if d.outcome == "executed"]
    if not executed:
        return PerformanceReview(open_positions=positions.count_open(conn))

    wins = 0
    total_pnl = 0
    confidence_sum = 0.0
    trade_returns: list[float] = []
    cumulative_value = 0.0
    peak_value = 0.0
    max_drawdown = 0.0

    for d in executed:
        confidence_sum += d.confidence
        trade_return = 0.0
        if d.actual_result is True:
            wins += 1
            trade_return = (100 - d.price) * d.quantity
            total_pnl += trade_return
        elif d.actual_result is False:
            trade_return = -(d.price * d.quantity)
            total_pnl += trade_return

        cumulative_value += trade_return
        if cumulative_value > peak_value:
            peak_value = cumulative_value
        drawdown = (peak_value - cumulative_value) / peak_value if peak_value != 0 else 0.0
        if drawdown > max_drawdown:
            max_drawdown = drawdown

        trade_returns.append(trade_return)

    trade_count = len(executed)
    win_rate = wins / trade_count if trade_count else 0.0
    avg_confidence = confidence_sum / trade_count if trade_count else 0.0
    max_drawdown_pct = max_drawdown * 100

    sharpe_ratio: float | None = None
    if len(trade_returns) > 1:
        mean_return = statistics.mean(trade_returns)
        try:
            std_return = statistics.stdev(trade_returns)
        except statistics.StatisticsError:
            logger.debug("Statistics stdev failed (likely ≤1 data point), defaulting to 0.0")
            std_return = 0.0
        if std_return > 0:
            sharpe_ratio = mean_return / std_return

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
        sharpe_ratio=sharpe_ratio,
        max_drawdown_pct=max_drawdown_pct,
        deviation_flag=deviation_flag,
        open_positions=positions.count_open(conn),
    )


def step_decision_review(
    decisions: list[DbDecision],
) -> DecisionReview:
    """Step 2: Review recent decisions — prediction accuracy for closed markets."""
    closed = [d for d in decisions if d.actual_result is not None and d.outcome == "executed"]
    open_decisions = [d for d in decisions if d.actual_result is None and d.outcome == "executed"]

    correct = 0
    for d in closed:
        if (d.direction == "yes" and d.actual_result is True) or (
            d.direction == "no" and d.actual_result is False
        ):
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
    breaker: CircuitBreaker | None = None,
) -> AdaptationReview:
    """Step 3: Run Bayesian adaptation with latest observations.

    Uses Beta-Binomial update on win/loss across all executed decisions.
    Breaker escalations feed weighted negative evidence: SLOW→+1, HALT→+3, FULL_STOP→+5 failures.
    Recovery events are explicitly excluded.
    """
    if not decisions:
        return AdaptationReview(skipped_reason="no decisions to adapt from")

    executed = [d for d in decisions if d.outcome == "executed"]
    if not executed:
        return AdaptationReview(skipped_reason="no executed decisions")

    successes = sum(
        1
        for d in executed
        if (d.direction == "yes" and d.actual_result is True)
        or (d.direction == "no" and d.actual_result is False)
    )
    failures = len(executed) - successes

    breaker_failures = _compute_breaker_failures(breaker)
    total_failures = failures + breaker_failures

    if successes + total_failures < 1:
        return AdaptationReview(skipped_reason="insufficient resolved decisions")

    observations = BinomialObservations(successes=successes, failures=total_failures)
    engine = adapter or BayesianAdapter()

    if dry_run:
        obs_total = observations.total
        extra = f" (+{breaker_failures} from breaker)" if breaker_failures else ""
        return AdaptationReview(
            updated=False,
            reasoning=f"Dry run: would update Beta-Binomial with {successes} wins, {total_failures} losses ({obs_total} obs){extra}",
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


def _compute_breaker_failures(breaker: CircuitBreaker | None) -> int:
    """Compute weighted failures from breaker escalation transitions since last processing."""
    global _last_processed_transition_ts

    if breaker is None:
        return 0

    transitions = breaker.get_transitions_since(_last_processed_transition_ts)
    if not transitions:
        return 0

    weighted_failures = 0
    latest_ts = _last_processed_transition_ts
    for t in transitions:
        if t.to_level > t.from_level:
            weighted_failures += BREAKER_ESCALATION_WEIGHTS.get(t.to_level, 0)
        if t.timestamp > latest_ts:
            latest_ts = t.timestamp

    _last_processed_transition_ts = latest_ts
    return weighted_failures


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


def step_recovery_experiment(
    breaker: CircuitBreaker | None = None,
    experiment_db_path: Path | None = None,
) -> RecoveryExperimentReview:
    """Step 5.1: If FULL_STOP is active, run recovery experiment.

    Checks if the experiment DB has >= 10 markets available. If yes,
    runs all registered treatments vs control via the Harness. If any
    treatment beats control (p < 0.05 paired t-test, positive Cohen's d),
    writes a recovery report to .learnings/RECOVERY-{timestamp}.md.

    Guard: only triggers once per FULL_STOP event.
    Does NOT auto-deploy — deployment is gated by profile update.
    """
    global _last_full_stop_experiment_ts

    engine = breaker or CircuitBreaker()
    state = engine.get_state()

    if state.level != BreakerLevel.FULL_STOP:
        return RecoveryExperimentReview()

    # Check if this FULL_STOP was already processed
    transitions = engine.get_transitions_since(_last_full_stop_experiment_ts)
    full_stop_transition = None
    for t in transitions:
        if t.to_level == BreakerLevel.FULL_STOP and t.from_level < BreakerLevel.FULL_STOP:
            full_stop_transition = t

    if full_stop_transition is None:
        # Same FULL_STOP event — already ran experiment for this one
        return RecoveryExperimentReview(
            triggered=False,
            skipped_reason="already_processed_full_stop",
        )

    _last_full_stop_experiment_ts = full_stop_transition.timestamp

    # Resolve experiment DB path
    if experiment_db_path is None:
        experiment_db_path = Path.home() / ".traderbot" / "experiments" / "experiment.db"

    if not experiment_db_path.exists():
        logger.info(
            "Recovery experiment skipped: experiment DB not found at %s", experiment_db_path
        )
        return RecoveryExperimentReview(
            triggered=False,
            skipped_reason="experiment_db_not_found",
        )

    import sqlite3 as _sqlite3

    conn: sqlite3.Connection
    try:
        conn = _sqlite3.connect(str(experiment_db_path))
        from traderbot.db.experiment_schema import create_tables

        create_tables(conn)
        market_count_row = conn.execute("SELECT COUNT(*) FROM markets").fetchone()
        market_count = market_count_row[0] if market_count_row else 0
    except Exception as exc:
        logger.warning("Recovery experiment: failed to query experiment DB: %s", exc)
        return RecoveryExperimentReview(
            triggered=False,
            skipped_reason=f"db_query_failed: {exc}",
        )
    finally:
        with contextlib.suppress(Exception):
            conn.close()

    if market_count < _MIN_MARKETS_FOR_RECOVERY:
        logger.info(
            "Recovery experiment skipped: %d markets available (need >= %d)",
            market_count,
            _MIN_MARKETS_FOR_RECOVERY,
        )
        return RecoveryExperimentReview(
            triggered=False,
            markets_available=market_count,
            skipped_reason="insufficient_markets",
        )

    # Discover and register treatments
    try:
        from traderbot.experiment.registry import (
            discover_treatments,
            get_treatment,
            register_treatment,
        )

        discovered = discover_treatments()
        for _class_name, cls in discovered.items():
            register_treatment(cls().name, cls)
    except ImportError as exc:
        logger.warning("Recovery experiment: treatment registry unavailable: %s", exc)
        return RecoveryExperimentReview(
            triggered=False,
            markets_available=market_count,
            skipped_reason="registry_unavailable",
        )

    control_cls = get_treatment("control")
    if control_cls is None:
        logger.warning("Recovery experiment: control treatment not found in registry")
        return RecoveryExperimentReview(
            triggered=False,
            markets_available=market_count,
            skipped_reason="no_control_treatment",
        )

    treatment_instances = [control_cls()]
    for name in sorted(set(discovered.keys()) - {"control"}):
        cls = get_treatment(name)
        if cls is not None:
            treatment_instances.append(cls())

    treatment_names = [t.name for t in treatment_instances]

    # Run the experiment harness
    import uuid

    run_id = f"recovery-{uuid.uuid4().hex[:8]}"

    try:
        from traderbot.experiment.harness import Harness
        from traderbot.llm.client import LLMClient
        from traderbot.llm.ollama import OllamaProvider

        provider = OllamaProvider()
        llm_client = LLMClient(provider=provider)

        conn = _sqlite3.connect(str(experiment_db_path))
        from traderbot.db.experiment_schema import create_tables as _create_tables

        _create_tables(conn)
        harness = Harness(conn, llm_client, seed=42)
        harness.run(
            treatment_instances,
            run_id=run_id,
            replicates=3,
            markets_per_cell=2,
        )
        conn.close()
    except Exception as exc:
        logger.warning("Recovery experiment harness failed: %s", exc)
        return RecoveryExperimentReview(
            triggered=True,
            markets_available=market_count,
            treatments_run=treatment_names,
            skipped_reason=f"harness_failed: {exc}",
        )

    # Score the results
    try:
        from traderbot.experiment.results import score_run

        result_list = score_run(str(experiment_db_path), run_id)
    except Exception as exc:
        logger.warning("Recovery experiment scoring failed: %s", exc)
        return RecoveryExperimentReview(
            triggered=True,
            markets_available=market_count,
            treatments_run=treatment_names,
            skipped_reason=f"scoring_failed: {exc}",
        )

    # Check for significant improvement
    significant = [r for r in result_list if r.improvement]

    if not significant:
        logger.info("Recovery experiment: no treatment beats control — continuing cooldown")
        return RecoveryExperimentReview(
            triggered=True,
            markets_available=market_count,
            treatments_run=treatment_names,
        )

    best = max(significant, key=lambda r: r.effect_size)
    logger.info(
        "Recovery experiment: %s beats control (p=%.4f, d=%.3f)",
        best.treatment,
        best.p_value,
        best.effect_size,
    )

    # Write recovery report
    report_dir = Path.home() / ".traderbot" / ".learnings"
    report_dir.mkdir(parents=True, exist_ok=True)
    ts_str = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_path = report_dir / f"RECOVERY-{ts_str}.md"

    report_lines = [
        f"# Recovery Experiment Report — {ts_str}",
        "",
        "**Trigger**: Circuit breaker FULL_STOP",
        f"**Run ID**: {run_id}",
        f"**Markets available**: {market_count}",
        "",
        "## Significant Treatments",
        "",
    ]
    for r in significant:
        report_lines.append(
            f"- **{r.treatment}** vs {r.control}: "
            f"delta={r.delta_profit:+.2f}, p={r.p_value:.4f}, "
            f"Cohen's d={r.effect_size:.3f}, n={r.n_markets}"
        )
    report_lines.extend(
        [
            "",
            "## All Results",
            "",
        ]
    )
    for r in result_list:
        sig = "YES" if r.improvement else "NO"
        report_lines.append(
            f"- {r.treatment} vs {r.control}: "
            f"p={r.p_value:.4f}, d={r.effect_size:.3f}, significant={sig}"
        )
    report_lines.extend(
        [
            "",
            "## Decision",
            "",
            f"Best treatment: **{best.treatment}** (not auto-deployed — requires profile update)",
        ]
    )

    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    logger.info("Recovery report written to %s", report_path)

    return RecoveryExperimentReview(
        triggered=True,
        markets_available=market_count,
        treatments_run=treatment_names,
        significant_treatment=best.treatment,
        p_value=best.p_value,
        effect_size=best.effect_size,
        report_path=str(report_path),
    )


def step_ws_health() -> WsHealthReview:
    """Step 5.5: Verify WS daemon process liveness and status consistency."""
    import json

    from traderbot.cli.ws import DAEMON_STATUS_PATH, _get_status, _is_pid_alive

    status_data = _get_status()
    if status_data is None:
        logger.warning("WS daemon status file not found — daemon not running")
        return WsHealthReview(status="not_running")

    pid = status_data.get("pid")
    connected = status_data.get("connected", False)

    if pid is None:
        logger.warning("WS daemon status file missing PID field")
        return WsHealthReview(status="not_running")

    alive = _is_pid_alive(pid)

    if not alive:
        logger.warning("WS daemon PID %s is stale (process not found)", pid)
        stale_status = {**status_data, "connected": False}
        DAEMON_STATUS_PATH.write_text(json.dumps(stale_status, indent=2))
        return WsHealthReview(pid=pid, pid_alive=False, connected=False, status="stale")

    if not connected:
        logger.warning("WS daemon PID %s alive but reports DISCONNECTED", pid)
        return WsHealthReview(pid=pid, pid_alive=True, connected=False, status="disconnected")

    logger.info("WS daemon healthy — PID %s alive and CONNECTED", pid)
    return WsHealthReview(pid=pid, pid_alive=True, connected=True, status="healthy")


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
        row = db_conn.execute("SELECT MAX(timestamp) as latest FROM decisions").fetchone()
        if row is not None and row[0] is not None:
            latest = datetime.fromisoformat(row[0])
            age_hours = (datetime.now(UTC) - latest).total_seconds() / 3600
            freshness = f"last_data_{age_hours:.1f}h_ago"
            if age_hours > 24:
                alerts.append(f"Stale data: last decision {age_hours:.1f}h ago")
        else:
            freshness = "no_decisions_yet"
    except Exception:
        logger.debug("Failed to query decision freshness")
        freshness = "unknown"

    api_status = "not_checked"
    balance_cents: int | None = None
    try:
        import asyncio

        from traderbot.kalshi.client import KalshiClient

        client = KalshiClient()  # auto-resolve auth from profile/env
        try:
            response = await asyncio.wait_for(
                client.get("/events", params={"limit": 1}), timeout=5.0
            )
            status = response.json() if hasattr(response, "json") else response
            api_ok = isinstance(status, dict) and status.get("status") == "alive"
            if api_ok:
                from traderbot.kalshi.portfolio import PortfolioService

                ps = PortfolioService(client)
                balance_data = await ps.get_cached_balance()
                if balance_data:
                    raw = balance_data.get("balance") or balance_data.get("available_balance")
                    if raw is not None:
                        balance_cents = int(float(raw) * 100) if isinstance(raw, str) else int(raw)
        except Exception:
            logger.debug("Kalshi API health check failed on /events, trying fallback")
            try:
                response = await asyncio.wait_for(client.get("/"), timeout=5.0)
                api_ok = response.status_code < 500
            except Exception:
                logger.debug("Kalshi API health check failed on /, trying second fallback")
                try:
                    response = await asyncio.wait_for(client.get("/markets?limit=1"), timeout=5.0)
                    api_ok = response.status_code < 500
                except Exception:
                    logger.debug("Kalshi API health check failed on all endpoints")
                    api_ok = False
        finally:
            await asyncio.wait_for(client.close(), timeout=2.0)
        api_status = "ok" if api_ok else "degraded"
    except Exception:
        api_status = "unavailable"
        alerts.append("Kalshi API unreachable")

    return SystemHealthReview(
        balance_cents=balance_cents,
        api_connectivity=api_status,
        db_integrity=db_status,
        data_freshness=freshness,
        alerts=alerts,
    )


def step_token_staleness() -> TokenStalenessReview:
    """Step 6.5: Check profile token staleness.

    Calls staleness_warning() to verify the current token against the encrypted
    registry. Emits a degraded status flag if the token is invalid or expired.
    """
    from traderbot.profiles.tokens import staleness_warning

    result = staleness_warning()
    degraded = not result["valid"]
    if degraded:
        logger.warning("Token staleness detected: %s", result["message"])

    return TokenStalenessReview(
        token_source=result["token_source"],
        valid=result["valid"],
        expired=result["expired"],
        profile=result["profile"],
        agent=result["agent"],
        degraded=degraded,
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

    # Step 0: Sync settlement results from positions → decisions
    synced = _sync_settlement_before_adaptation(conn)
    if synced:
        logger.info("Heartbeat: synced %d settlement results before adaptation", synced)

    # Step 1: Performance review
    decisions = _get_decisions(conn, since)
    performance = step_performance_review(conn, decisions, since)
    steps_completed.append("performance_review")

    # Step 2: Decision review
    decision_review = step_decision_review(decisions)
    steps_completed.append("decision_review")

    # Step 3: Bayesian adaptation
    from traderbot.simulation.adapter_state import resolve_state_path

    resolved_state_path = state_path if state_path is not None else resolve_state_path()
    adapter = BayesianAdapter(state_path=resolved_state_path)
    breaker_instance = CircuitBreaker()
    adaptation = step_bayesian_adaptation(
        decisions, adapter=adapter, dry_run=dry_run, breaker=breaker_instance
    )
    steps_completed.append("bayesian_adaptation")

    # Step 4: Learning promotion
    learning_promotion = step_learning_promotion(conn, dry_run=dry_run)
    steps_completed.append("learning_promotion")

    # Step 5: Circuit breaker check
    circuit_breaker = step_circuit_breaker_check(breaker=breaker_instance)
    steps_completed.append("circuit_breaker_check")

    # Step 5.1: Recovery experiment (only on FULL_STOP)
    recovery_experiment = step_recovery_experiment(breaker=breaker_instance)
    if recovery_experiment.triggered:
        steps_completed.append("recovery_experiment")

    # Step 5.5: WS daemon health check
    ws_health = step_ws_health()
    steps_completed.append("ws_health")

    # Step 6: System health
    system_health = await step_system_health(conn)
    steps_completed.append("system_health")

    # Step 6.5: Token staleness check
    token_staleness = step_token_staleness()
    steps_completed.append("token_staleness")

    # Step 7: Update check (respects user-configured interval and enabled flag via UpdateConfig)
    update_result = check_for_updates()
    if update_result:
        logger.info(
            "Update available: v%s → v%s", update_result["current"], update_result["latest"]
        )
    steps_completed.append("update_check")

    result = HeartbeatResult(
        timestamp=now,
        performance=performance,
        decisions=decision_review,
        adaptation=adaptation,
        learning_promotion=learning_promotion,
        circuit_breaker=circuit_breaker,
        recovery_experiment=recovery_experiment,
        ws_health=ws_health,
        system_health=system_health,
        token_staleness=token_staleness,
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
        recovery_experiment=result.recovery_experiment,
        ws_health=result.ws_health,
        system_health=result.system_health,
        token_staleness=result.token_staleness,
        steps_completed=steps_completed,
    )


def _sync_settlement_before_adaptation(conn: sqlite3.Connection) -> int:
    """Bridge positions.settlement_result → decisions.actual_result before adaptation."""
    try:
        from traderbot.db.sync import sync_settlement_to_decisions

        return sync_settlement_to_decisions(conn)
    except Exception as exc:
        logger.warning("Settlement sync skipped: %s", exc)
        return 0


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
    if result.ws_health.status not in ("healthy", "unknown"):
        alert_lines += f"- ⚠️ WS daemon: {result.ws_health.status} (PID {result.ws_health.pid}, alive={result.ws_health.pid_alive}, connected={result.ws_health.connected})\n"
    if not alert_lines:
        alert_lines = "- None\n"

    staleness = result.token_staleness
    staleness_lines = "- Valid ✓\n"
    if not staleness.valid:
        status = "EXPIRED" if staleness.expired else "INVALID/REVOKED"
        staleness_lines = f"- ⚠️ {status} (source: {staleness.token_source})\n"
        if staleness.profile:
            staleness_lines += f"  Profile: {staleness.profile}\n"
        staleness_lines += "  Run `traderbot profile sync-env <profile>` to fix\n"

    # Recovery experiment section
    recovery = result.recovery_experiment
    recovery_lines = "- Not triggered\n"
    if recovery.triggered:
        recovery_lines = f"- Triggered: {recovery.markets_available} markets available\n"
        if recovery.treatments_run:
            recovery_lines += f"- Treatments: {', '.join(recovery.treatments_run)}\n"
        if recovery.significant_treatment:
            recovery_lines += f"- Significant treatment: {recovery.significant_treatment} (p={recovery.p_value:.4f}, d={recovery.effect_size:.3f})\n"
        if recovery.report_path:
            recovery_lines += f"- Report: {recovery.report_path}\n"
        elif recovery.skipped_reason:
            recovery_lines += f"- Skipped: {recovery.skipped_reason}\n"

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

### Recovery Experiment
{recovery_lines}
### WS Daemon Health
- Status: {result.ws_health.status}
- PID: {result.ws_health.pid or "N/A"}
- PID alive: {result.ws_health.pid_alive}
- Connected: {result.ws_health.connected}

### System Health
- API: {health.api_connectivity}
- DB: {health.db_integrity}
- Freshness: {health.data_freshness}

### Token Staleness
{staleness_lines}
### Alerts
{alert_lines}
"""

    path.write_text(content, encoding="utf-8")
    logger.info("Heartbeat written to %s", path)
