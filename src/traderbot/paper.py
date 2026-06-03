"""Paper trading balance computation.

Single-source-of-truth for paper portfolio value. Both `traderbot trade`
and `traderbot performance` call this function so balance tracking is
consistent across the codebase.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from traderbot.paths import _resolve_db_path
from traderbot.db import get_connection
from traderbot.db.positions import list_all
from traderbot.profiles.models import TradingProfile as Profile

logger = logging.getLogger(__name__)


@dataclass
class PaperBalance:
    initial_cents: int
    cost_at_risk_cents: int
    settled_payout_cents: int
    remaining_cents: int
    open_position_count: int

    @property
    def net_pnl_cents(self) -> int:
        return self.settled_payout_cents - (self.initial_cents - self.remaining_cents)


def compute_paper_balance(
    profile: Profile | None, db_path: Path | None = None
) -> PaperBalance | None:
    """Compute paper portfolio balance from SQLite positions.

    Formula: remaining = initial_balance - cost(at open) + settlement_payouts

    Settlement payouts:
    - YES won → +100¢ per contract
    - NO won → +100¢ per contract (NO side pays $1 when correct)
    - Lost → 0¢ payout (cost already counted as sunk)

    Returns None if not a paper profile or no profile given.
    """
    if not profile or not profile.paper_mode or not profile.initial_balance_cents:
        return None

    initial = profile.initial_balance_cents
    resolved = _resolve_db_path(db_path)
    total_cost = 0
    total_payout = 0
    open_count = 0

    with get_connection(resolved) as conn:
        for pos in list_all(conn):
            total_cost += pos.avg_price * pos.quantity
            if pos.settlement_result is True:
                total_payout += 100 * pos.quantity
            elif pos.settlement_result is False:
                pass
            else:
                open_count += 1

    remaining = initial - total_cost + total_payout
    return PaperBalance(
        initial_cents=initial,
        cost_at_risk_cents=total_cost - total_payout,
        settled_payout_cents=total_payout,
        remaining_cents=remaining,
        open_position_count=open_count,
    )


def remaining_balance(profile: Profile | None, db_path: Path | None = None) -> int:
    pb = compute_paper_balance(profile, db_path)
    if pb is None:
        return 0
    return pb.remaining_cents
