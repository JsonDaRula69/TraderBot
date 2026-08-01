from __future__ import annotations

import pytest
from pydantic import ValidationError

from traderbot.cron_loops import (
    DECISION_LOOP_CRON,
    HEARTBEAT_LOOP_CRON,
    NEWS_IMPACT_THRESHOLD,
    DecisionLoopPayload,
    HeartbeatLoopPayload,
    NewsLoopPayload,
)


class TestConstants:
    def test_decision_loop_cron(self) -> None:
        assert DECISION_LOOP_CRON == "*/5 * * * *"

    def test_heartbeat_loop_cron(self) -> None:
        assert HEARTBEAT_LOOP_CRON == "*/30 * * * *"

    def test_news_impact_threshold(self) -> None:
        assert NEWS_IMPACT_THRESHOLD == 0.7


class TestDecisionLoopPayload:
    def test_defaults(self) -> None:
        p = DecisionLoopPayload()
        assert p.session_target == "isolated"
        assert p.kind == "agentTurn"
        assert "traderbot decision loop" in p.message
        assert p.channel is None
        assert p.to is None

    def test_invalid_session_target(self) -> None:
        with pytest.raises(ValidationError):
            DecisionLoopPayload(session_target="main")  # type: ignore[arg-type]

    def test_invalid_kind(self) -> None:
        with pytest.raises(ValidationError):
            DecisionLoopPayload(kind="systemEvent")  # type: ignore[arg-type]

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            DecisionLoopPayload(unknown_field="x")  # type: ignore[call-arg]


class TestHeartbeatLoopPayload:
    def test_defaults(self) -> None:
        p = HeartbeatLoopPayload()
        assert p.session_target == "isolated"
        assert p.kind == "agentTurn"
        assert "traderbot heartbeat" in p.message.lower()
        assert p.channel is None
        assert p.to is None

    def test_invalid_kind(self) -> None:
        with pytest.raises(ValidationError):
            HeartbeatLoopPayload(kind="agentTurnx")  # type: ignore[arg-type]


class TestNewsLoopPayload:
    def test_minimal(self) -> None:
        p = NewsLoopPayload(topic="weather", impact_score=0.8)
        assert p.session_target == "main"
        assert p.kind == "systemEvent"
        assert p.topic == "weather"
        assert p.impact_score == 0.8
        assert p.relevant_markets == []

    def test_with_markets(self) -> None:
        p = NewsLoopPayload(
            topic="weather", impact_score=0.8, relevant_markets=["KWEATHER-25APR15-A"]
        )
        assert p.relevant_markets == ["KWEATHER-25APR15-A"]

    def test_impact_score_clamped(self) -> None:
        with pytest.raises(ValidationError):
            NewsLoopPayload(topic="weather", impact_score=1.5)

    def test_impact_score_negative(self) -> None:
        with pytest.raises(ValidationError):
            NewsLoopPayload(topic="weather", impact_score=-0.1)
