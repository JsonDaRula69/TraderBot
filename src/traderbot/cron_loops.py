"""Three-loop cron architecture for OpenClaw integration.

Defines Decision Loop, Heartbeat Loop, and News Loop as programmatic
Pydantic models with cron expressions and JSON payloads.

Decision Loop: isolated agentTurn every 5 min during market hours
Heartbeat Loop: isolated agentTurn every 6 hours
News Loop: systemEvent on high-impact news (impact > 0.7)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DECISION_LOOP_CRON = "*/5 9-15 * * 1-5"
HEARTBEAT_LOOP_CRON = "0 */6 * * *"
NEWS_LOOP_CRON = None

NEWS_IMPACT_THRESHOLD = 0.7

MARKET_OPEN_HOUR = 9
MARKET_CLOSE_HOUR = 15
MARKET_DAYS = range(1, 6)


class DecisionLoopPayload(BaseModel):
    """Payload for the Decision Loop agentTurn."""

    model_config = ConfigDict(strict=True, extra="forbid")

    session_target: Literal["isolated"] = "isolated"
    kind: Literal["agentTurn"] = "agentTurn"
    message: str = (
        "AUTONOMOUS: Run traderbot decision loop. "
        "Read SESSION-STATE.md for tracked markets. "
        "Execute analysis, risk-check, and trades within guard rails. "
        "Log all decisions."
    )


class HeartbeatLoopPayload(BaseModel):
    """Payload for the Heartbeat Loop agentTurn."""

    model_config = ConfigDict(strict=True, extra="forbid")

    session_target: Literal["isolated"] = "isolated"
    kind: Literal["agentTurn"] = "agentTurn"
    message: str = (
        "HEARTBEAT: Run traderbot self-improvement cycle. "
        "Check circuit breaker, review recent decisions, "
        "update Bayesian parameters, promote learnings. "
        "Write HEARTBEAT_DATA.md."
    )


class NewsLoopPayload(BaseModel):
    """Payload for the News/Sentiment Loop systemEvent."""

    model_config = ConfigDict(strict=True, extra="forbid")

    session_target: Literal["main"] = "main"
    kind: Literal["systemEvent"] = "systemEvent"
    topic: str
    impact_score: float = Field(ge=0.0, le=1.0)
    relevant_markets: list[str] = Field(default_factory=list)
    message: str = ""

    def model_post_init(self, __context: object) -> None:
        if not self.message:
            self.message = (
                f"ALERT: High-impact event detected ({self.topic}). "
                f"Run `traderbot sentiment {self.topic}` for analysis."
            )


class CronLoopConfig(BaseModel):
    """Configuration for a single cron loop."""

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str
    cron_expression: str | None
    loop_type: Literal["decision", "heartbeat", "news"]
    session_target: Literal["isolated", "main"]
    payload_type: Literal["agentTurn", "systemEvent"]


class DecisionLoopConfig(CronLoopConfig):
    """Decision Loop: isolated agentTurn every 5 min, market hours."""

    name: str = "decision_loop"
    cron_expression: str | None = DECISION_LOOP_CRON
    loop_type: Literal["decision"] = "decision"
    session_target: Literal["isolated"] = "isolated"
    payload_type: Literal["agentTurn"] = "agentTurn"


class HeartbeatLoopConfig(CronLoopConfig):
    """Heartbeat Loop: isolated agentTurn every 6 hours."""

    name: str = "heartbeat_loop"
    cron_expression: str | None = HEARTBEAT_LOOP_CRON
    loop_type: Literal["heartbeat"] = "heartbeat"
    session_target: Literal["isolated"] = "isolated"
    payload_type: Literal["agentTurn"] = "agentTurn"


class NewsLoopConfig(CronLoopConfig):
    """News Loop: systemEvent on high-impact news."""

    name: str = "news_loop"
    cron_expression: str | None = NEWS_LOOP_CRON
    loop_type: Literal["news"] = "news"
    session_target: Literal["main"] = "main"
    payload_type: Literal["systemEvent"] = "systemEvent"


LOOP_DEFINITIONS: list[CronLoopConfig] = [
    DecisionLoopConfig(),
    HeartbeatLoopConfig(),
    NewsLoopConfig(),
]


def get_loop_config(loop_type: str) -> CronLoopConfig:
    """Look up a loop configuration by type name."""
    for cfg in LOOP_DEFINITIONS:
        if cfg.loop_type == loop_type:
            return cfg
    raise ValueError(f"Unknown loop type: {loop_type!r}")


def build_payload(loop_type: str, **kwargs: object) -> BaseModel:
    """Build a JSON-serializable payload for the given loop type.

    For news loops, `topic` and `impact_score` are required.
    """
    if loop_type == "decision":
        return DecisionLoopPayload(**kwargs)
    if loop_type == "heartbeat":
        return HeartbeatLoopPayload(**kwargs)
    if loop_type == "news":
        return NewsLoopPayload(**kwargs)
    raise ValueError(f"Unknown loop type: {loop_type!r}")
