"""Tests for the three-loop cron architecture."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from traderbot.cron_loops import (
    DECISION_LOOP_CRON,
    HEARTBEAT_LOOP_CRON,
    LOOP_DEFINITIONS,
    MARKET_CLOSE_HOUR,
    MARKET_DAYS,
    MARKET_OPEN_HOUR,
    NEWS_IMPACT_THRESHOLD,
    NEWS_LOOP_CRON,
    CronLoopConfig,
    DecisionLoopConfig,
    DecisionLoopPayload,
    HeartbeatLoopConfig,
    HeartbeatLoopPayload,
    NewsLoopConfig,
    NewsLoopPayload,
    build_payload,
    get_loop_config,
)


class TestCronExpressions:
    def test_decision_loop_cron_matches_market_hours(self) -> None:
        fields = DECISION_LOOP_CRON.split()
        assert len(fields) == 5
        minute, hour, _, _, weekday = fields
        assert minute == "*/5"
        hour_parts = hour.split("-")
        assert int(hour_parts[0]) == MARKET_OPEN_HOUR
        assert int(hour_parts[1]) == MARKET_CLOSE_HOUR
        day_parts = weekday.split("-")
        assert int(day_parts[0]) == min(MARKET_DAYS)
        assert int(day_parts[1]) == max(MARKET_DAYS)

    def test_heartbeat_loop_cron_every_six_hours(self) -> None:
        fields = HEARTBEAT_LOOP_CRON.split()
        assert len(fields) == 5
        minute, hour, _, _, _ = fields
        assert minute == "0"
        assert hour == "*/6"

    def test_news_loop_cron_is_none(self) -> None:
        assert NEWS_LOOP_CRON is None

    def test_decision_loop_cron_format_valid(self) -> None:
        cron_pattern = r"^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)$"
        assert re.match(cron_pattern, DECISION_LOOP_CRON)

    def test_heartbeat_loop_cron_format_valid(self) -> None:
        cron_pattern = r"^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)$"
        assert re.match(cron_pattern, HEARTBEAT_LOOP_CRON)


class TestDecisionLoopPayload:
    def test_default_payload(self) -> None:
        payload = DecisionLoopPayload()
        assert payload.session_target == "isolated"
        assert payload.kind == "agentTurn"
        assert "decision loop" in payload.message.lower()

    def test_json_serializable(self) -> None:
        payload = DecisionLoopPayload()
        data = payload.model_dump(mode="json")
        assert data["session_target"] == "isolated"
        assert data["kind"] == "agentTurn"

    def test_strict_mode_rejects_extra(self) -> None:
        with pytest.raises(ValidationError):
            DecisionLoopPayload(extra_field="bad")

    def test_literal_fields_reject_invalid(self) -> None:
        with pytest.raises(ValidationError):
            DecisionLoopPayload(session_target="main")

    def test_message_matches_docs(self) -> None:
        payload = DecisionLoopPayload()
        assert "SESSION-STATE.md" in payload.message
        assert "risk-check" in payload.message


class TestHeartbeatLoopPayload:
    def test_default_payload(self) -> None:
        payload = HeartbeatLoopPayload()
        assert payload.session_target == "isolated"
        assert payload.kind == "agentTurn"
        assert "HEARTBEAT" in payload.message

    def test_json_serializable(self) -> None:
        payload = HeartbeatLoopPayload()
        data = payload.model_dump(mode="json")
        assert data["session_target"] == "isolated"

    def test_strict_mode_rejects_extra(self) -> None:
        with pytest.raises(ValidationError):
            HeartbeatLoopPayload(extra_field="bad")

    def test_message_matches_docs(self) -> None:
        payload = HeartbeatLoopPayload()
        assert "circuit breaker" in payload.message.lower()
        assert "Bayesian" in payload.message
        assert "learnings" in payload.message.lower()


class TestNewsLoopPayload:
    def test_basic_payload(self) -> None:
        payload = NewsLoopPayload(topic="fed-rate-cut", impact_score=0.85)
        assert payload.session_target == "main"
        assert payload.kind == "systemEvent"
        assert payload.topic == "fed-rate-cut"
        assert payload.impact_score == 0.85

    def test_auto_generated_message(self) -> None:
        payload = NewsLoopPayload(topic="fed-rate-cut", impact_score=0.9)
        assert "fed-rate-cut" in payload.message
        assert "sentiment" in payload.message

    def test_custom_message_overrides(self) -> None:
        payload = NewsLoopPayload(
            topic="fed-rate-cut",
            impact_score=0.9,
            message="Custom alert message",
        )
        assert payload.message == "Custom alert message"

    def test_relevant_markets_default(self) -> None:
        payload = NewsLoopPayload(topic="test", impact_score=0.5)
        assert payload.relevant_markets == []

    def test_relevant_markets_with_values(self) -> None:
        payload = NewsLoopPayload(
            topic="test",
            impact_score=0.8,
            relevant_markets=["KXBTCD-26MAR31-T55000", "KXINX-26JUN31-T6000"],
        )
        assert len(payload.relevant_markets) == 2

    def test_impact_score_bounds_valid(self) -> None:
        NewsLoopPayload(topic="test", impact_score=0.0)
        NewsLoopPayload(topic="test", impact_score=1.0)

    def test_impact_score_rejects_negative(self) -> None:
        with pytest.raises(ValidationError):
            NewsLoopPayload(topic="test", impact_score=-0.1)

    def test_impact_score_rejects_above_one(self) -> None:
        with pytest.raises(ValidationError):
            NewsLoopPayload(topic="test", impact_score=1.1)

    def test_strict_mode_rejects_extra(self) -> None:
        with pytest.raises(ValidationError):
            NewsLoopPayload(topic="test", impact_score=0.5, extra="bad")

    def test_event_driven_threshold(self) -> None:
        assert NEWS_IMPACT_THRESHOLD == 0.7

    def test_json_serializable(self) -> None:
        payload = NewsLoopPayload(topic="test", impact_score=0.75)
        data = payload.model_dump(mode="json")
        assert data["session_target"] == "main"
        assert data["kind"] == "systemEvent"


class TestLoopConfigs:
    def test_decision_loop_config(self) -> None:
        cfg = DecisionLoopConfig()
        assert cfg.name == "decision_loop"
        assert cfg.cron_expression == DECISION_LOOP_CRON
        assert cfg.loop_type == "decision"
        assert cfg.session_target == "isolated"
        assert cfg.payload_type == "agentTurn"

    def test_heartbeat_loop_config(self) -> None:
        cfg = HeartbeatLoopConfig()
        assert cfg.name == "heartbeat_loop"
        assert cfg.cron_expression == HEARTBEAT_LOOP_CRON
        assert cfg.loop_type == "heartbeat"
        assert cfg.session_target == "isolated"
        assert cfg.payload_type == "agentTurn"

    def test_news_loop_config(self) -> None:
        cfg = NewsLoopConfig()
        assert cfg.name == "news_loop"
        assert cfg.cron_expression is None
        assert cfg.loop_type == "news"
        assert cfg.session_target == "main"
        assert cfg.payload_type == "systemEvent"

    def test_loop_definitions_contains_all_three(self) -> None:
        assert len(LOOP_DEFINITIONS) == 3
        types = {cfg.loop_type for cfg in LOOP_DEFINITIONS}
        assert types == {"decision", "heartbeat", "news"}

    def test_loop_definitions_instances(self) -> None:
        assert isinstance(LOOP_DEFINITIONS[0], DecisionLoopConfig)
        assert isinstance(LOOP_DEFINITIONS[1], HeartbeatLoopConfig)
        assert isinstance(LOOP_DEFINITIONS[2], NewsLoopConfig)

    def test_cron_loop_config_rejects_extra(self) -> None:
        with pytest.raises(ValidationError):
            CronLoopConfig(
                name="test",
                cron_expression="* * * * *",
                loop_type="decision",
                session_target="isolated",
                payload_type="agentTurn",
                extra="bad",
            )

    def test_cron_loop_config_valid_loop_types(self) -> None:
        for lt in ("decision", "heartbeat", "news"):
            CronLoopConfig(
                name=f"{lt}_loop",
                cron_expression="* * * * *",
                loop_type=lt,
                session_target="isolated",
                payload_type="agentTurn",
            )

    def test_decision_loop_config_isolation(self) -> None:
        cfg = DecisionLoopConfig()
        assert cfg.session_target == "isolated"
        assert cfg.payload_type == "agentTurn"

    def test_news_loop_config_main_session(self) -> None:
        cfg = NewsLoopConfig()
        assert cfg.session_target == "main"
        assert cfg.payload_type == "systemEvent"


class TestGetLoopConfig:
    def test_get_decision(self) -> None:
        cfg = get_loop_config("decision")
        assert isinstance(cfg, DecisionLoopConfig)

    def test_get_heartbeat(self) -> None:
        cfg = get_loop_config("heartbeat")
        assert isinstance(cfg, HeartbeatLoopConfig)

    def test_get_news(self) -> None:
        cfg = get_loop_config("news")
        assert isinstance(cfg, NewsLoopConfig)

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown loop type"):
            get_loop_config("nonexistent")


class TestBuildPayload:
    def test_decision_payload(self) -> None:
        payload = build_payload("decision")
        assert isinstance(payload, DecisionLoopPayload)
        assert payload.kind == "agentTurn"
        assert payload.session_target == "isolated"

    def test_heartbeat_payload(self) -> None:
        payload = build_payload("heartbeat")
        assert isinstance(payload, HeartbeatLoopPayload)
        assert payload.kind == "agentTurn"

    def test_news_payload(self) -> None:
        payload = build_payload("news", topic="test", impact_score=0.8)
        assert isinstance(payload, NewsLoopPayload)
        assert payload.kind == "systemEvent"
        assert payload.topic == "test"

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown loop type"):
            build_payload("nonexistent")

    def test_news_payload_missing_topic_raises(self) -> None:
        with pytest.raises(ValidationError):
            build_payload("news", impact_score=0.8)
