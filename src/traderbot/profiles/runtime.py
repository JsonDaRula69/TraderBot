"""Runtime profile resolution and configuration loading."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from traderbot.profiles.config import resolve_kalshi_credentials
from traderbot.profiles.isolation import (
    get_profile_audit_path,
    get_profile_chroma_path,
    get_profile_db_path,
)
from traderbot.profiles.registry import ProfileRegistry
from traderbot.profiles.tokens import resolve_token
from traderbot.risk.agent_limits import AgentRiskLimits

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)


def get_current_profile(**kwargs: Any) -> TradingProfile | None:
    """Read TRADERBOT_PROFILE_TOKEN env var and resolve to profile.

    Returns:
        TradingProfile if token is valid and profile exists, None otherwise
    """
    token = os.environ.get("TRADERBOT_PROFILE_TOKEN")
    if token is None:
        logger.debug("No TRADERBOT_PROFILE_TOKEN environment variable set")
        return None

    resolution = resolve_token(token)
    if resolution is None:
        logger.warning("Invalid or revoked token: %s", "****" + token[-4:] if len(token) > 4 else "****")
        return None

    profile_name, agent_id = resolution
    logger.debug("Token resolved to profile '%s' for agent '%s'", profile_name, agent_id)

    registry = ProfileRegistry()
    profile = registry.get_profile(profile_name)

    if profile is None:
        logger.warning("Profile '%s' not found in registry", profile_name)
        return None

    logger.info("Loaded profile '%s' (mode=%s)", profile.name, profile.mode)
    return profile


def load_profile_config(
    profile: TradingProfile,
) -> dict[str, Any]:
    """Load profile-specific configuration.

    Returns:
        Dictionary containing:
            - credentials: dict[str, tuple[str, str]] — service → (key, secret)
            - paper_mode: bool — True for paper trading, False for live
            - paths: dict[str, Path] — db, chroma, audit paths
            - limits: dict[str, float | int] — risk limits from AgentRiskLimits
    """
    config: dict[str, Any] = {}

    try:
        kalshi_key, kalshi_secret = resolve_kalshi_credentials(profile)
        config["credentials"] = {
            "kalshi": (kalshi_key, kalshi_secret)
        }
    except ValueError as e:
        logger.warning("Failed to resolve Kalshi credentials: %s", e)
        config["credentials"] = {}

    config["paper_mode"] = profile.paper_mode

    config["paths"] = {
        "db": get_profile_db_path(profile, "decisions.db").parent,
        "chroma": get_profile_chroma_path(profile),
        "audit": get_profile_audit_path(profile),
    }

    limits = AgentRiskLimits(profile)
    config["limits"] = {
        "max_position_per_market_pct": limits.max_position_per_market_pct,
        "max_daily_loss_pct": limits.max_daily_loss_pct,
        "max_drawdown_pct": limits.max_drawdown_pct,
        "max_open_positions": limits.max_open_positions,
        "min_liquidity_threshold": limits.min_liquidity_threshold,
        "min_edge_pct": limits.min_edge_pct,
    }

    logger.debug(
        "Loaded config for profile '%s': paper_mode=%s, paths=%s",
        profile.name,
        config["paper_mode"],
        {k: str(v) for k, v in config["paths"].items()},
    )

    return config


def get_runtime_context(**kwargs: Any) -> dict[str, Any]:
    """Get full runtime context (profile + config).

    Convenience function that calls get_current_profile() and load_profile_config().

    Returns:
        Dictionary containing:
            - profile: TradingProfile | None
            - config: dict[str, Any] | None (None if no profile)
    """
    profile = get_current_profile()

    if profile is None:
        logger.debug("No profile available, returning empty context")
        return {
            "profile": None,
            "config": None,
        }

    config = load_profile_config(
        profile,
    )

    return {
        "profile": profile,
        "config": config,
    }
