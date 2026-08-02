"""MCP auth helpers — per-agent tool-layer access control (DD-011).

DD-011 requires per-agent category isolation: the MCP tool layer must
enforce that an agent can only access its enabled categories. This module
implements ``check_category_access``, which tools call after authenticating
a profile to gate category-scoped operations.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from traderbot.kalshi.models import MarketCategory

if TYPE_CHECKING:
    from traderbot.profiles.models import TradingProfile

logger = logging.getLogger(__name__)


def check_category_access(
    profile: TradingProfile,
    agent_id: str | None,
    category: str | None,
    tool_name: str,
) -> dict[str, str] | None:
    """Validate whether a profile may access a market category (DD-011).

    Returns ``None`` when access is allowed, or an ``{"error": ...}`` dict
    when denied. Rules, evaluated in order:

    1. ``category is None`` → allowed (tools without a category skip the check).
    2. Empty ``enabled_categories`` (sysadmin) → allowed (all categories).
    3. Unknown category string → ``{"error": "Unknown category: ..."}``.
    4. Valid category not in ``enabled_categories`` → denied.
    5. Otherwise → allowed.

    Args:
        profile: The authenticated trading profile.
        agent_id: The requesting agent (may be None for non-agent callers).
        category: The market category to check (may be None).
        tool_name: The MCP tool name, for logging.
    """
    if category is None:
        return None

    try:
        parsed = MarketCategory(category.lower())
    except ValueError:
        logger.debug("tool=%s agent=%s unknown category %r", tool_name, agent_id, category)
        return {"error": f"Unknown category: {category}"}

    if not profile.is_category_enabled(parsed):
        logger.debug(
            "tool=%s agent=%s category=%s denied (not enabled)",
            tool_name,
            agent_id,
            parsed.value,
        )
        return {"error": f"Category '{category}' not enabled for agent '{agent_id}'"}

    return None
