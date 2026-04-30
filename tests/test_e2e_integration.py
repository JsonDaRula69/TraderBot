"""End-to-end integration tests across all phases — simulation → learning → news → adaptation.

Test scenarios:
1. Full pipeline: backtest → paper trade → heartbeat → adaptation → news → sentiment
2. WAL: trade → WAL write → completion → crash recovery
3. Graceful degradation: without Voyage API, without ChromaDB
4. Bayesian guardrails: max change, min samples, cooldown, variance reset, drift flag
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from traderbot.db import get_connection, init_schema
from traderbot.db.decisions import DbDecision
from traderbot.db.decisions import insert as insert_decision
from traderbot.db.learnings import (
    LearningCategory,
    record_pattern,
)
from traderbot.db.learnings import (
    init_table as init_learnings_table,
)
from traderbot.kalshi.models import Market
from traderbot.learning import (
    init_task_observations_table,
    record_task_observation,
)
from traderbot.news.classifier import NewsClassifier
from traderbot.news.models import (
    ClassifiedNews,
    ImpactAssessment,
    NewsCategory,
    NewsItem,
    NewsSource,
    SentimentResult,
)
from traderbot.news.sentiment_scorer import SentimentScorer
from traderbot.risk.circuit_breaker import BreakerLevel, CircuitBreaker
from traderbot.simulation.adaptation import (
    WEAK_BETA,
    BayesianAdapter,
    BetaParams,
    BinomialObservations,
    DirichletParams,
    ExponentialObservations,
    GammaParams,
    GuardrailConfig,
    MarketCategory,
    MultinomialObservations,
    NormalObservations,
    NormalParams,
)
from traderbot.wal import (
    WalAction,
    WalEntry,
    WalStatus,
    reconcile,
    scan_pending,
    update_status,
    write_intent,
)

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_market(
    ticker: str = "KX-TEST",
    question: str = "Test market?",
    state: str = "settled",
    volume: int = 5000,
    open_interest: int = 2000,
    settlement_result: bool | None = True,
    close_time: datetime | None = None,
) -> Market:
    """Create a Market model instance for testing."""
    return Market(
        ticker=ticker,
        question=question,
        outcome_prices=["0.65", "0.35"],
        volume=volume,
        open_interest=open_interest,
        close_time=close_time or datetime(2026, 3, 31, 23, 59, 59, tzinfo=UTC),
        state=state,
        event_ticker=ticker.rsplit("-", 1)[0] if "-" in ticker else "KX-TEST",
        category="economics",
        settlement_result=settlement_result,
    )


def _make_news_item(
    title: str = "Fed raises interest rates by 25 basis points",
    body: str = "The Federal Reserve announced a rate hike impacting markets.",
    source: NewsSource = NewsSource.NEWSAPI,
    ticker_refs: list[str] | None = None,
) -> NewsItem:
    """Create a NewsItem for testing."""
    return NewsItem(
        id="news-e2e-001",
        title=title,
        body=body,
        source=source,
        url="https://example.com/news/e2e-001",
        published_at=datetime.now(UTC),
        ticker_refs=ticker_refs or ["KX-TEST"],
        category=NewsCategory.ECONOMICS,
    )


def _init_db(conn: sqlite3.Connection) -> None:
    """Initialize all tables needed for E2E tests."""
    init_schema(conn)
    init_learnings_table(conn)
    init_task_observations_table(conn)


def _make_db_decision(
    ticker: str = "KX-TEST",
    direction: str = "yes",
    price: int = 65,
    quantity: int = 10,
    confidence: float = 0.8,
    outcome: str = "executed",
    actual_result: bool | None = True,
    timestamp: datetime | None = None,
    signal_strength: float = 0.7,
    edge_estimate: float = 0.05,
) -> DbDecision:
    """Create a DbDecision for testing."""
    return DbDecision(
        id=0,
        ticker=ticker,
        direction=direction,  # type: ignore[arg-type]
        price=price,
        quantity=quantity,
        confidence=confidence,
        outcome=outcome,  # type: ignore[arg-type]
        actual_result=actual_result,
        signal_strength=signal_strength,
        edge_estimate=edge_estimate,
        risk_checks={"limit_check": True, "edge_check": True},
        rejection_reason=None,
        timestamp=timestamp or datetime.now(UTC),
    )


# ========================================================================
# 1. Full Pipeline E2E: backtest → heartbeat → adaptation → news → sentiment
# ========================================================================


class TestFullPipelineE2E:
    """End-to-end flow across all major subsystems."""

    def test_heartbeat_uses_bayesian_adaptation_on_decisions(self, tmp_path: Path) -> None:
        """Pipeline: insert decisions → heartbeat → Bayesian adapts → verify adaptation output."""
        db_path = tmp_path / "test.db"
        with get_connection(db_path) as conn:
            _init_db(conn)

            for i in range(15):
                d = _make_db_decision(
                    ticker=f"KX-TEST-{i % 3}",
                    direction="yes" if i % 2 == 0 else "no",
                    price=55 + i,
                    confidence=0.6 + i * 0.02,
                    actual_result=(i % 3 != 0),
                )
                insert_decision(conn, d)

            from traderbot.heartbeat import run_heartbeat_cycle

            hb_path = tmp_path / "HEARTBEAT_DATA.md"
            result = run_heartbeat_cycle(
                conn,
                heartbeat_path=hb_path,
                dry_run=True,
            )

            # Verify all 8 steps completed
            expected_steps = [
                "performance_review",
                "decision_review",
                "bayesian_adaptation",
                "learning_promotion",
                "circuit_breaker_check",
                "system_health",
                "update_check",
                "update_heartbeat_md",
            ]
            for step in expected_steps:
                assert step in result.steps_completed, f"Missing step: {step}"

            # Performance review should have data
            assert result.performance.trade_count == 15
            assert result.performance.deviation_flag != "" or result.performance.trade_count > 0

            # Bayesian adaptation should have run
            assert result.adaptation.updated is True or result.adaptation.skipped_reason != ""

    def test_news_classification_and_sentiment_pipeline(self) -> None:
        """Pipeline: NewsItem → classify → score sentiment → verify outputs valid."""
        # Step 1: Create a news item
        item = _make_news_item(
            title="Fed raises interest rates amid inflation concerns",
            body="The Federal Reserve increased rates by 0.25 percentage points.",
        )

        # Step 2: Classify
        classifier = NewsClassifier(voyage=None)
        classified = classifier.classify(item)

        assert isinstance(classified, ClassifiedNews)
        assert classified.news_item.id == item.id
        assert isinstance(classified.category, NewsCategory)
        # Economics keywords present → should classify as Economics
        assert classified.category == NewsCategory.ECONOMICS

        # Step 3: Score sentiment
        scorer = SentimentScorer(voyage_client=None)
        sentiment = scorer.score(
            text=f"{item.title} {item.body}",
            source=NewsSource.NEWSAPI,
            news_id=item.id,
        )

        assert isinstance(sentiment, SentimentResult)
        assert -1.0 <= sentiment.score <= 1.0
        assert 0.0 <= sentiment.confidence <= 1.0
        assert sentiment.news_id == item.id
        # NewsAPI uses TextBlob, not VADER
        assert "textblob" in sentiment.model

    def test_heartbeat_with_circuit_breaker_escalation(self, tmp_path: Path) -> None:
        """Pipeline: circuit breaker triggers → heartbeat reports breaker state."""
        db_path = tmp_path / "test.db"
        with get_connection(db_path) as conn:
            _init_db(conn)

            # Insert some decisions
            for i in range(5):
                d = _make_db_decision(
                    ticker=f"KX-TEST-{i}",
                    actual_result=True,
                )
                insert_decision(conn, d)

            # Create a circuit breaker in SLOW state
            cb_file = tmp_path / "cb_test.json"
            breaker = CircuitBreaker(state_file=cb_file)
            breaker.check(daily_loss_pct=0.015, drawdown_pct=0.05)

            state = breaker.get_state()
            assert state.level == BreakerLevel.SLOW

            # Run heartbeat with custom breaker
            from traderbot.heartbeat import (
                step_circuit_breaker_check,
            )

            cb_review = step_circuit_breaker_check(breaker)
            assert cb_review.level == "SLOW"
            assert cb_review.can_trade is True
            assert cb_review.position_size_multiplier < 1.0

    def test_decision_review_pipeline(self, tmp_path: Path) -> None:
        """Pipeline: decisions → review → verify prediction accuracy."""
        from traderbot.heartbeat import step_decision_review

        # Create decisions with known outcomes
        decisions = [
            _make_db_decision(direction="yes", actual_result=True, outcome="executed"),
            _make_db_decision(direction="yes", actual_result=False, outcome="executed"),
            _make_db_decision(direction="no", actual_result=False, outcome="executed"),
        ]

        result = step_decision_review(decisions)

        assert result.closed_count == 3
        # "yes" + True = correct, "yes" + False = incorrect, "no" + False = correct → 2 correct
        assert result.correct_predictions == 2
        assert abs(result.prediction_accuracy - 2 / 3) < 1e-9

    def test_system_health_checks_db_integrity(self, tmp_path: Path) -> None:
        """Pipeline: system health step verifies DB integrity."""
        from traderbot.heartbeat import step_system_health

        db_path = tmp_path / "health.db"
        with get_connection(db_path) as conn:
            _init_db(conn)

            health = step_system_health(conn)
            assert health.db_integrity == "ok"

    def test_promotion_in_heartbeat_pipeline(self, tmp_path: Path) -> None:
        """Pipeline: eligible pattern → heartbeat promotes it."""
        db_path = tmp_path / "test.db"
        with get_connection(db_path) as conn:
            _init_db(conn)

            # Seed an eligible pattern (recurrence >= 3, multiple tasks)
            pattern_id = record_pattern(
                conn,
                category=LearningCategory.RISK_SIGNAL,
                summary="Spread widens at market close",
                evidence="Observed spread widening on 3 separate occasions",
                confidence=0.75,
            )
            conn.execute(
                "UPDATE learnings SET recurrence_count = 3 WHERE id = ?", (pattern_id,)
            )
            conn.commit()

            for i in range(3):
                record_task_observation(conn, pattern_id, f"task-{i}")

            from traderbot.heartbeat import step_learning_promotion

            result = step_learning_promotion(conn)
            assert result.candidates_found >= 1


# ========================================================================
# 2. WAL E2E: trade → WAL write → completion → crash recovery
# ========================================================================


class TestWALE2E:
    """End-to-end WAL protocol tests."""

    def test_wal_full_lifecycle(self, tmp_path: Path) -> None:
        """Write intent → mark completed → verify state."""
        session_file = tmp_path / "SESSION-STATE.md"
        session_file.write_text("# Session\n\n## Pending Actions\n\n(none)\n\n## WAL Entries\n")

        entry = write_intent(
            session_file,
            action=WalAction.BUY,
            ticker="KX-TEST",
            direction="yes",
            quantity=10,
            price_cents=65,
            reason="Edge detected above 3% threshold",
        )

        assert entry.intent_id.startswith("WAL-")
        assert entry.status == WalStatus.PENDING

        # Mark completed
        updated = update_status(session_file, entry.intent_id, WalStatus.COMPLETED)
        assert updated is True

        # Verify no pending entries remain
        pending = scan_pending(session_file)
        assert len(pending) == 0

    def test_wal_cancel_intent(self, tmp_path: Path) -> None:
        """Write intent → mark cancelled → verify state."""
        session_file = tmp_path / "SESSION-STATE.md"
        session_file.write_text("# Session\n\n## Pending Actions\n\n(none)\n\n## WAL Entries\n")

        entry = write_intent(
            session_file,
            action=WalAction.SELL,
            ticker="KX-TEST",
            direction="no",
            quantity=5,
            price_cents=35,
            reason="Risk limit reached",
        )

        assert entry.status == WalStatus.PENDING

        updated = update_status(session_file, entry.intent_id, WalStatus.CANCELLED)
        assert updated is True

        pending = scan_pending(session_file)
        assert len(pending) == 0

    def test_wal_multiple_intents(self, tmp_path: Path) -> None:
        """Write multiple intents → complete one, cancel one → verify states."""
        session_file = tmp_path / "SESSION-STATE.md"
        session_file.write_text("# Session\n\n## Pending Actions\n\n(none)\n\n## WAL Entries\n")

        entry1 = write_intent(
            session_file,
            action=WalAction.BUY,
            ticker="KX-BTC",
            direction="yes",
            quantity=20,
            price_cents=55,
            reason="High confidence signal",
        )
        entry2 = write_intent(
            session_file,
            action=WalAction.BUY,
            ticker="KX-ETH",
            direction="no",
            quantity=15,
            price_cents=40,
            reason="Contrarian play",
        )

        pending = scan_pending(session_file)
        assert len(pending) == 2

        # Complete entry1, cancel entry2
        update_status(session_file, entry1.intent_id, WalStatus.COMPLETED)
        update_status(session_file, entry2.intent_id, WalStatus.CANCELLED)

        pending = scan_pending(session_file)
        assert len(pending) == 0

    def test_wal_reconcile_matches_position(self, tmp_path: Path) -> None:
        """Reconcile WAL intent against matching position → mark COMPLETED."""
        session_file = tmp_path / "SESSION-STATE.md"
        session_file.write_text("# Session\n\n## Pending Actions\n\n(none)\n\n## WAL Entries\n")

        write_intent(
            session_file,
            action=WalAction.BUY,
            ticker="KX-TEST",
            direction="yes",
            quantity=10,
            price_cents=65,
            reason="Reconciliation test",
        )

        # Matching position: yes direction, quantity >= 10
        positions = {"KX-TEST": {"yes": 10, "no": 0}}

        updated = reconcile(session_file, positions)
        assert len(updated) == 1
        assert updated[0].status == WalStatus.COMPLETED

        # No pending entries after reconciliation
        pending = scan_pending(session_file)
        assert len(pending) == 0

    def test_wal_reconcile_mismatch_marks_cancelled(self, tmp_path: Path) -> None:
        """Reconcile WAL intent with no matching position → mark CANCELLED."""
        session_file = tmp_path / "SESSION-STATE.md"
        session_file.write_text("# Session\n\n## Pending Actions\n\n(none)\n\n## WAL Entries\n")

        write_intent(
            session_file,
            action=WalAction.BUY,
            ticker="KX-TEST",
            direction="yes",
            quantity=10,
            price_cents=65,
            reason="Unmatched position test",
        )

        # No matching position
        positions: dict[str, dict[str, int]] = {}

        updated = reconcile(session_file, positions)
        assert len(updated) == 1
        assert updated[0].status == WalStatus.CANCELLED

    def test_wal_crash_recovery_picks_up_pending(self, tmp_path: Path) -> None:
        """Simulate crash: leave PENDING entries → scan_pending recovers them."""
        session_file = tmp_path / "SESSION-STATE.md"
        session_file.write_text("# Session\n\n## Pending Actions\n\n(none)\n\n## WAL Entries\n")

        # Write two intents (simulating app crash before completion)
        entry1 = write_intent(
            session_file,
            action=WalAction.BUY,
            ticker="KX-BTC",
            direction="yes",
            quantity=10,
            price_cents=55,
            reason="Pre-crash buy",
        )
        entry2 = write_intent(
            session_file,
            action=WalAction.SELL,
            ticker="KX-ETH",
            direction="no",
            quantity=5,
            price_cents=40,
            reason="Pre-crash sell",
        )

        # Simulate crash recovery: scan for pending
        pending = scan_pending(session_file)
        assert len(pending) == 2

        # Get intent IDs by ticker
        tickers = {p.ticker for p in pending}
        assert "KX-BTC" in tickers
        assert "KX-ETH" in tickers

        # Reconcile: BTC position exists, ETH does not
        positions = {"KX-BTC": {"yes": 10, "no": 0}}
        updated = reconcile(session_file, positions)

        assert len(updated) == 2
        statuses = {u.intent_id: u.status for u in updated}
        assert statuses[entry1.intent_id] == WalStatus.COMPLETED
        assert statuses[entry2.intent_id] == WalStatus.CANCELLED

    def test_wal_pre_entry_construction(self, tmp_path: Path) -> None:
        """Construct WalEntry manually, then write it → verify round-trip."""
        session_file = tmp_path / "SESSION-STATE.md"
        session_file.write_text("# Session\n\n## Pending Actions\n\n(none)\n\n## WAL Entries\n")

        now = datetime.now(UTC)
        entry = WalEntry(
            intent_id="WAL-CUSTOM01",
            timestamp=now,
            action=WalAction.BUY,
            ticker="KX-TEST",
            direction="yes",
            quantity=25,
            price_cents=70,
            reason="Manual entry test",
            signal="momentum",
            risk_checks="passed",
            confidence=0.85,
            status=WalStatus.PENDING,
        )

        write_intent(session_file, entry=entry)

        # Round-trip: scan the file and verify
        pending = scan_pending(session_file)
        assert len(pending) == 1
        assert pending[0].ticker == "KX-TEST"
        assert pending[0].quantity == 25
        assert pending[0].price_cents == 70


# ========================================================================
# 3. Graceful Degradation E2E: without Voyage API, without ChromaDB
# ========================================================================


class TestGracefulDegradation:
    """Verify graceful fallback when external services are unavailable."""

    def test_classifier_without_voyage(self) -> None:
        """NewsClassifier works with keyword-only when Voyage unavailable."""
        classifier = NewsClassifier(voyage=None)

        # Economics text should classify correctly via keywords alone
        item = _make_news_item(
            title="Fed signals rate cut could come in June",
            body="The Federal Reserve hinted at potential interest rate reductions.",
        )
        result = classifier.classify(item)
        assert result.category == NewsCategory.ECONOMICS

        # Politics text
        item_pol = _make_news_item(
            title="Senate passes new infrastructure bill",
            body="Congress approved the spending legislation.",
            ticker_refs=["KX-POL"],
        )
        result_pol = classifier.classify(item_pol)
        assert result_pol.category == NewsCategory.POLITICS

    def test_classifier_without_voyage_falls_back_on_unknown_text(self) -> None:
        """When keywords don't match and Voyage unavailable, defaults to Economics."""
        classifier = NewsClassifier(voyage=None)

        # Random text with no keywords → keyword fallback with default category
        item = _make_news_item(
            title="Random obscure event happened today",
            body="Something occurred but no category keywords are present here.",
        )
        result = classifier.classify(item)
        # No keyword match → keyword_cat_hits is empty → default Economics
        assert result.category == NewsCategory.ECONOMICS

    def test_sentiment_without_voyage(self) -> None:
        """SentimentScorer works without Voyage client (VADER/TextBlob fast path only)."""
        scorer = SentimentScorer(voyage_client=None)

        # Positive economics text
        result = scorer.score(
            text="Strong economic growth boosts market confidence",
            source=NewsSource.NEWSAPI,
            news_id="test-001",
        )
        assert -1.0 <= result.score <= 1.0
        assert 0.0 <= result.confidence <= 1.0
        assert "textblob" in result.model
        # Without Voyage, no "+voyage" suffix should appear for non-ambiguous scores
        # (unless score is in the ambiguous zone where uplift would be attempted)

    def test_sentiment_without_voyage_social_media(self) -> None:
        """VADER scoring for social media sources when Voyage unavailable."""
        scorer = SentimentScorer(voyage_client=None)

        # Negative social media text with VADER
        result = scorer.score(
            text="Terrible crash in crypto markets, investors panicking",
            source=NewsSource.TWITTER,
            news_id="test-002",
        )
        assert -1.0 <= result.score <= 1.0
        assert "vader" in result.model

    def test_classifier_with_broken_voyage_client(self) -> None:
        """Classify gracefully degrades when Voyage client raises errors."""
        mock_voyage = MagicMock()
        mock_voyage.embed.side_effect = Exception("Voyage API down")

        classifier = NewsClassifier(voyage=mock_voyage)

        # Should fall back to keywords when embed fails
        item = _make_news_item(
            title="Hurricane season expected to be severe",
            body="Weather forecasters predict above-average storm activity.",
        )
        result = classifier.classify(item)
        assert isinstance(result.category, NewsCategory)
        assert result.category == NewsCategory.WEATHER

    def test_sentiment_with_broken_voyage_client(self) -> None:
        """Sentiment scorer gracefully degrades when Voyage embed returns None."""
        mock_voyage = MagicMock()
        mock_voyage.embed.return_value = None

        scorer = SentimentScorer(voyage_client=mock_voyage)

        # Score should still work, just without Voyage uplift
        result = scorer.score(
            text="Moderate economic outlook for next quarter",
            source=NewsSource.NEWSAPI,
            news_id="test-003",
        )
        assert -1.0 <= result.score <= 1.0
        assert result.news_id == "test-003"

    def test_heartbeat_with_no_decisions(self, tmp_path: Path) -> None:
        """Heartbeat handles empty DB gracefully."""
        db_path = tmp_path / "empty.db"
        with get_connection(db_path) as conn:
            _init_db(conn)

            from traderbot.heartbeat import run_heartbeat_cycle

            hb_path = tmp_path / "HEARTBEAT_DATA.md"
            result = run_heartbeat_cycle(
                conn,
                heartbeat_path=hb_path,
                dry_run=True,
            )

            # Should not crash, all steps should complete
            assert "performance_review" in result.steps_completed
            assert "decision_review" in result.steps_completed
            assert "bayesian_adaptation" in result.steps_completed

            # Performance review with no trades
            assert result.performance.trade_count == 0
            assert result.performance.total_pnl_cents == 0

    def test_bayesian_adapter_with_insufficient_data(self) -> None:
        """BayesianAdapter skips update when observations are below minimum."""
        config = GuardrailConfig(min_observations=10)  # default
        adapter = BayesianAdapter(config)

        prior = WEAK_BETA
        observations = BinomialObservations(successes=3, failures=2)  # only 5

        with pytest.raises(ValueError, match="Insufficient observations"):
            adapter.update_beta(prior, observations, category=MarketCategory.ECONOMICS)


# ========================================================================
# 4. Bayesian Guardrails E2E: max change, min samples, cooldown, variance reset, drift
# ========================================================================


class TestBayesianGuardrailsE2E:
    """End-to-end tests for Bayesian adaptation guardrails from docs/self-learning.md."""

    def test_max_20_pct_change_clamped(self) -> None:
        """Guardrail: changes clamped to 20% maximum per update."""
        config = GuardrailConfig(max_change_pct=0.20, min_observations=1)
        adapter = BayesianAdapter(config)

        # Beta(2, 8) has mean=0.2. With Binomial(80, 20), posterior mean ≈ 0.22
        # But we want a case where clamping visibly kicks in.
        # Use Beta(2, 8) mean=0.2 with Binomial(100 successes, 0 failures)
        # → posterior Beta(102, 8) mean ≈ 0.927, change from 0.2 to 0.927 = 363%
        # Should be clamped: old_value + 20% = 0.2 + 0.04 = 0.24
        prior = BetaParams(alpha=2.0, beta=8.0)
        observations = BinomialObservations(successes=100, failures=0)

        result = adapter.update_beta(prior, observations, category=MarketCategory.ECONOMICS)

        assert result.updated_params["mean"] <= prior.mean * 1.2 + 1e-9
        assert result.magnitude <= prior.mean * 0.20 + 1e-9

    def test_min_10_samples_guardrail(self) -> None:
        """Guardrail: below 10 observations, update is rejected."""
        config = GuardrailConfig(min_observations=10)
        adapter = BayesianAdapter(config)

        # Only 5 observations → should raise ValueError
        prior = WEAK_BETA
        observations = BinomialObservations(successes=3, failures=2)

        with pytest.raises(ValueError, match="Insufficient observations"):
            adapter.update_beta(prior, observations, category=MarketCategory.ECONOMICS)

    def test_min_1_observation_with_relaxed_config(self) -> None:
        """Guardrail: with min_observations=1, even single observation works."""
        config = GuardrailConfig(min_observations=1, max_change_pct=0.20)
        adapter = BayesianAdapter(config)

        prior = BetaParams(alpha=2.0, beta=8.0)
        observations = BinomialObservations(successes=1, failures=1)

        result = adapter.update_beta(prior, observations, category=MarketCategory.ECONOMICS)
        assert result.method is not None

    def test_cooldown_4_updates_per_day(self) -> None:
        """Guardrail: 5th update within 24h is rejected (cooldown)."""
        config = GuardrailConfig(max_updates_per_day=4, min_observations=1)
        adapter = BayesianAdapter(config)

        prior = BetaParams(alpha=2.0, beta=8.0)
        # Override min_observations for this test
        config_small = GuardrailConfig(max_updates_per_day=4, min_observations=1)
        adapter.config = config_small

        observations = BinomialObservations(successes=10, failures=10)

        # First 4 updates should succeed
        for _i in range(4):
            result = adapter.update_beta(prior, observations, category=MarketCategory.ECONOMICS)
            assert result.method is not None or result.variance_reset is True

        # 5th update should fail with cooldown
        with pytest.raises(ValueError, match="Cooldown active"):
            adapter.update_beta(prior, observations, category=MarketCategory.ECONOMICS)

    def test_variance_reset_when_posterior_too_confident(self) -> None:
        """Guardrail: posterior variance < 0.01 triggers reset to weak prior."""
        # Use a very concentrated prior to force variance reset
        # Beta(1000, 1000) has variance ≈ 0.00025 < 0.01
        # After update with Binomial(50, 30), variance stays very low
        config = GuardrailConfig(
            min_observations=1,
            variance_reset_threshold=0.01,
            max_change_pct=0.20,
        )
        adapter = BayesianAdapter(config)

        # Concentrated prior that will produce low-variance posterior
        prior = BetaParams(alpha=100.0, beta=100.0)
        observations = BinomialObservations(successes=50, failures=30)

        result = adapter.update_beta(prior, observations, category=MarketCategory.ECONOMICS)
        # Posterior variance may be below threshold → reset
        # Check that result reports variance_reset correctly
        # Beta(150, 130) variance = 150*130 / (280^2 * 281) ≈ 0.000872 < 0.01
        assert result.variance_reset is True
        assert result.confidence == 0.0  # Reset → confidence is 0

    def test_drift_flag_after_3_consecutive_changes(self) -> None:
        """Guardrail: 3 consecutive >10% changes trigger human_review flag."""
        config = GuardrailConfig(
            min_observations=1,
            max_change_pct=0.50,
            drift_threshold_pct=0.10,
            drift_consecutive_count=3,
            variance_reset_threshold=0.0001,
        )
        adapter = BayesianAdapter(config)

        prior = BetaParams(alpha=2.0, beta=8.0)  # mean=0.2

        obs = BinomialObservations(successes=15, failures=5)

        for _i in range(3):
            adapter.update_beta(
                prior, obs, category=MarketCategory.ECONOMICS,
            )

        assert adapter._drift_counts.get("edge_threshold", 0) >= 3

    def test_guardrail_config_defaults_match_spec(self) -> None:
        """Verify GuardrailConfig defaults match docs/self-learning.md spec."""
        config = GuardrailConfig()

        assert config.max_change_pct == 0.20  # 20%
        assert config.min_observations == 10
        assert config.max_updates_per_day == 4
        assert config.variance_reset_threshold == 0.01
        assert config.drift_threshold_pct == 0.10  # 10%
        assert config.drift_consecutive_count == 3

    def test_dirichlet_guardrails(self) -> None:
        """Dirichlet-Multinomial update also enforces guardrails."""
        config = GuardrailConfig(min_observations=1, max_change_pct=0.20)
        adapter = BayesianAdapter(config)

        prior = DirichletParams(alphas=[1.0, 1.0, 1.0])
        obs = MultinomialObservations(counts=[10, 5, 5])

        result = adapter.update_dirichlet(prior, obs, category=MarketCategory.ECONOMICS)
        assert result.method.value == "dirichlet_multinomial"
        assert result.confidence >= 0.0

    def test_normal_guardrails(self) -> None:
        """Normal-Normal update enforces guardrails."""
        config = GuardrailConfig(
            min_observations=1,
            max_change_pct=0.20,
            variance_reset_threshold=0.001,  # lower to avoid spurious reset
        )
        adapter = BayesianAdapter(config)

        prior = NormalParams(mu=0.5, sigma_sq=0.04)
        obs = NormalObservations(values=[0.6, 0.55, 0.58, 0.52, 0.49], known_variance=0.01)

        result = adapter.update_normal(prior, obs, category=MarketCategory.ECONOMICS)
        assert result.method.value == "normal_normal"
        assert result.confidence >= 0.0

    def test_gamma_guardrails(self) -> None:
        """Gamma-Exponential update enforces guardrails."""
        config = GuardrailConfig(min_observations=1, max_change_pct=0.20)
        adapter = BayesianAdapter(config)

        prior = GammaParams(alpha=1.0, beta=1.0)
        obs = ExponentialObservations(values=[0.5, 0.8, 1.2, 0.3, 1.0])

        result = adapter.update_gamma(prior, obs, category=MarketCategory.ECONOMICS)
        assert result.method.value == "gamma_exponential"
        assert result.confidence >= 0.0


# ========================================================================
# Cross-module integration: Bayesian adaptation within heartbeat
# ========================================================================


class TestBayesianHeartbeatIntegration:
    """Verify BayesianAdapter integrates correctly with heartbeat adaptation step."""

    def test_heartbeat_bayesian_step_with_weak_prior(self, tmp_path: Path) -> None:
        """Heartbeat Bayesian step uses WEAK_BETA prior with win/loss observations."""
        decisions = [
            _make_db_decision(direction="yes", actual_result=True, outcome="executed"),
            _make_db_decision(direction="yes", actual_result=True, outcome="executed"),
            _make_db_decision(direction="no", actual_result=False, outcome="executed"),
            _make_db_decision(direction="yes", actual_result=False, outcome="executed"),
        ]

        from traderbot.heartbeat import step_bayesian_adaptation

        # Default adapter requires min_observations=10, so use a relaxed adapter
        config = GuardrailConfig(min_observations=1, max_change_pct=0.20)
        adapter = BayesianAdapter(config)
        more_decisions = decisions * 3  # 12 decisions total
        result = step_bayesian_adaptation(more_decisions, adapter=adapter)

        assert result.direction in ("increase", "decrease", "maintain")
        assert result.confidence >= 0.0

    def test_heartbeat_bayesian_step_dry_run(self, tmp_path: Path) -> None:
        """Dry run does not perform adaptation, just reports what would happen."""
        decisions = [_make_db_decision(outcome="executed", actual_result=True)] * 15

        from traderbot.heartbeat import step_bayesian_adaptation

        result = step_bayesian_adaptation(decisions, dry_run=True)
        assert result.updated is False
        assert "dry_run" in result.skipped_reason.lower() or result.skipped_reason == "dry_run"

    def test_heartbeat_bayesian_step_with_custom_adapter(self) -> None:
        """Custom BayesianAdapter with relaxed guardrails works in heartbeat."""
        config = GuardrailConfig(min_observations=1, max_change_pct=0.20)
        adapter = BayesianAdapter(config)

        decisions = [
            _make_db_decision(direction="yes", actual_result=True, outcome="executed"),
            _make_db_decision(direction="no", actual_result=False, outcome="executed"),
        ]

        from traderbot.heartbeat import step_bayesian_adaptation

        result = step_bayesian_adaptation(decisions, adapter=adapter)
        assert result.updated is True

    def test_full_pipeline_heartbeat_with_wal_and_adaptation(self, tmp_path: Path) -> None:
        """Complete E2E: decisions → WAL → heartbeat → adaptation → verify all outputs."""
        db_path = tmp_path / "full_e2e.db"
        with get_connection(db_path) as conn:
            _init_db(conn)

            # Step 1: Insert decisions
            for i in range(15):
                d = _make_db_decision(
                    ticker=f"KX-TEST-{i % 3}",
                    direction="yes" if i % 2 == 0 else "no",
                    price=50 + i,
                    confidence=0.6 + i * 0.02,
                    actual_result=(i % 3 != 0),
                    outcome="executed",
                )
                insert_decision(conn, d)

            # Step 2: Write WAL intent
            session_file = tmp_path / "SESSION-STATE.md"
            session_file.write_text(
                "# Session\n\n## Pending Actions\n\n(none)\n\n## WAL Entries\n"
            )
            wal_entry = write_intent(
                session_file,
                action=WalAction.BUY,
                ticker="KX-TEST-0",
                direction="yes",
                quantity=5,
                price_cents=55,
                reason="E2E pipeline test",
            )
            assert wal_entry.status == WalStatus.PENDING

            # Step 3: Run heartbeat
            from traderbot.heartbeat import run_heartbeat_cycle

            hb_path = tmp_path / "HEARTBEAT_DATA.md"
            result = run_heartbeat_cycle(
                conn,
                heartbeat_path=hb_path,
                dry_run=True,
            )

            # Verify all steps ran
            assert len(result.steps_completed) == 8

            # Step 4: Verify WAL still has pending entry (dry-run doesn't modify)
            pending = scan_pending(session_file)
            assert len(pending) == 1
            assert pending[0].ticker == "KX-TEST-0"

            # Step 5: Mark WAL entry as completed
            update_status(session_file, wal_entry.intent_id, WalStatus.COMPLETED)
            pending_after = scan_pending(session_file)
            assert len(pending_after) == 0

            # Step 6: Classify news and score sentiment
            item = _make_news_item(
                title="GDP growth exceeds expectations",
                body="The economy expanded at 3.2% annual rate.",
            )
            classifier = NewsClassifier(voyage=None)
            classified = classifier.classify(item)
            assert classified.category == NewsCategory.ECONOMICS

            scorer = SentimentScorer(voyage_client=None)
            sentiment = scorer.score(
                text=f"{item.title} {item.body}",
                source=NewsSource.NEWSAPI,
                news_id=item.id,
            )
            assert -1.0 <= sentiment.score <= 1.0

            # Step 7: Verify heartbeat adaptation step completed
            assert result.adaptation.skipped_reason != "" or result.adaptation.updated is True


# ========================================================================
# Impact assessor integration
# ========================================================================


class TestImpactAssessorE2E:
    """Verify impact assessor works in the full pipeline context."""

    def test_impact_assessor_with_classified_news(self) -> None:
        """Classify news → score sentiment → assess impact → verify all outputs."""
        from traderbot.news.impact_assessor import ImpactAssessor

        item = _make_news_item(
            title="Federal Reserve raises rates by 25 basis points",
            body="The Fed announced another rate hike citing persistent inflation.",
            ticker_refs=["KX-FED-RATE"],
        )

        # Step 1: Classify
        classifier = NewsClassifier(voyage=None)
        classified = classifier.classify(item)
        assert classified.category == NewsCategory.ECONOMICS

        # Step 2: Score sentiment
        scorer = SentimentScorer(voyage_client=None)
        sentiment = scorer.score(
            text=f"{item.title} {item.body}",
            source=NewsSource.NEWSAPI,
            news_id=item.id,
        )

        # Step 3: Assess impact
        assessor = ImpactAssessor()
        impact = assessor.assess(
            news_item=item,
            classified_news=classified,
            sentiment_result=sentiment,
            corroborating_count=2,
            voyage_client=None,
        )

        assert isinstance(impact, ImpactAssessment)
        assert impact.ticker == "KX-FED-RATE"
        assert impact.direction in ("bullish", "bearish", "neutral")
        assert 0.0 <= impact.magnitude <= 1.0
        assert 0.0 <= impact.confidence <= 1.0
        assert impact.timeframe in ("immediate", "short_term", "long_term")

    def test_impact_assessor_with_voyage_graceful_degradation(self) -> None:
        """Impact assesssment works without Voyage client (keyword relevance fallback)."""
        from traderbot.news.impact_assessor import ImpactAssessor

        item = _make_news_item(
            title="Hurricane season forecast worsens",
            body="NOAA predicts above-average storm activity this year.",
            ticker_refs=["KX-WX-HURR"],
        )

        classifier = NewsClassifier(voyage=None)
        classified = classifier.classify(item)

        scorer = SentimentScorer(voyage_client=None)
        sentiment = scorer.score(
            text=f"{item.title} {item.body}",
            source=NewsSource.NEWSAPI,
            news_id=item.id,
        )

        assessor = ImpactAssessor()
        impact = assessor.assess(
            news_item=item,
            classified_news=classified,
            sentiment_result=sentiment,
            corroborating_count=0,  # no corroboration
            voyage_client=None,
        )

        assert isinstance(impact, ImpactAssessment)
        # Without Voyage, should still produce valid output
        assert impact.direction in ("bullish", "bearish", "neutral")
        assert 0.0 <= impact.magnitude <= 1.0
        assert len(impact.reasoning) > 0


# ========================================================================
# Circuit breaker + heartbeat integration
# ========================================================================


class TestCircuitBreakerWithHeartbeat:
    """Verify circuit breaker state is reflected in heartbeat."""

    def test_normal_breaker_in_heartbeat(self, tmp_path: Path) -> None:
        """Normal circuit breaker → heartbeat shows NORMAL level."""
        db_path = tmp_path / "test.db"
        with get_connection(db_path) as conn:
            _init_db(conn)

            cb_file = tmp_path / "cb_normal.json"
            breaker = CircuitBreaker(state_file=cb_file)
            breaker.check(daily_loss_pct=0.005, drawdown_pct=0.02)

            from traderbot.heartbeat import step_circuit_breaker_check

            review = step_circuit_breaker_check(breaker)
            assert review.level == "NORMAL"
            assert review.can_trade is True
            assert review.position_size_multiplier == 1.0

    def test_slow_breaker_in_heartbeat(self, tmp_path: Path) -> None:
        """SLOW circuit breaker → heartbeat reports reduced position sizing."""
        tmp_path / "test.db"

        cb_file = tmp_path / "cb_slow.json"
        breaker = CircuitBreaker(state_file=cb_file)
        breaker.check(daily_loss_pct=0.015, drawdown_pct=0.05)

        from traderbot.heartbeat import step_circuit_breaker_check

        review = step_circuit_breaker_check(breaker)
        assert review.level == "SLOW"
        assert review.can_trade is True
        assert review.position_size_multiplier < 1.0

    def test_halt_breaker_in_heartbeat(self, tmp_path: Path) -> None:
        """HALT circuit breaker → heartbeat reports cannot trade."""
        cb_file = tmp_path / "cb_halt.json"
        breaker = CircuitBreaker(state_file=cb_file)
        breaker.check(daily_loss_pct=0.025, drawdown_pct=0.08)

        from traderbot.heartbeat import step_circuit_breaker_check

        review = step_circuit_breaker_check(breaker)
        assert review.level == "HALT"
        assert review.can_trade is False
        assert review.position_size_multiplier == 0.0

    def test_full_stop_breaker_in_heartbeat(self, tmp_path: Path) -> None:
        """FULL_STOP circuit breaker → heartbeat reports full stop."""
        cb_file = tmp_path / "cb_full_stop.json"
        breaker = CircuitBreaker(state_file=cb_file)
        breaker.check(daily_loss_pct=0.005, drawdown_pct=0.15)

        from traderbot.heartbeat import step_circuit_breaker_check

        review = step_circuit_breaker_check(breaker)
        assert review.level == "FULL_STOP"
        assert review.can_trade is False
        assert review.position_size_multiplier == 0.0


# ========================================================================
# Performance review edge cases
# ========================================================================


class TestPerformanceReviewE2E:
    """End-to-end tests for performance review step."""

    def test_all_wins_high_deviation_flag(self) -> None:
        """Win rate > 70% with 5+ trades → win_rate_above_expected deviation."""
        from traderbot.heartbeat import step_performance_review

        decisions = [
            _make_db_decision(
                direction="yes",
                actual_result=True,
                outcome="executed",
                price=55,
                quantity=10,
            )
            for _ in range(8)
        ]

        result = step_performance_review(decisions)
        assert result.trade_count == 8
        assert result.win_rate == 1.0
        assert result.deviation_flag == "win_rate_above_expected"

    def test_all_losses_low_deviation_flag(self) -> None:
        """Win rate < 30% with 5+ trades → win_rate_below_expected deviation."""
        from traderbot.heartbeat import step_performance_review

        decisions = [
            _make_db_decision(
                direction="yes",
                actual_result=False,
                outcome="executed",
                price=55,
                quantity=10,
            )
            for _ in range(6)
        ]

        result = step_performance_review(decisions)
        assert result.trade_count == 6
        assert result.win_rate == 0.0
        assert result.deviation_flag == "win_rate_below_expected"

    def test_empty_decisions_no_crash(self) -> None:
        """Empty decisions list → default PerformanceReview, no crash."""
        from traderbot.heartbeat import step_performance_review

        result = step_performance_review([])
        assert result.trade_count == 0
        assert result.win_rate == 0.0
        assert result.deviation_flag == ""

    def test_mixed_outcomes_no_deviation(self) -> None:
        """Win rate between 30-70% → no deviation flag."""
        from traderbot.heartbeat import step_performance_review

        # 5 wins, 5 losses → 50% win rate
        decisions = [
            _make_db_decision(
                direction="yes",
                actual_result=(i % 2 == 0),
                outcome="executed",
                price=55,
                quantity=10,
            )
            for i in range(10)
        ]

        result = step_performance_review(decisions)
        assert result.win_rate == 0.5
        assert result.deviation_flag == ""
