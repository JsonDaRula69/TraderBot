from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, List, Protocol, Dict
from pydantic import BaseModel, ConfigDict, Field
from traderbot.kalshi.models import PortfolioState, Market

class BacktestConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    start_date: datetime
    end_date: datetime
    strategy_name: str
    initial_bankroll: Annotated[int, Field(ge=0)]
    slippage_model: str

class BacktestTrade(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    ticker: str
    direction: Literal["yes", "no"]
    entry_price: Annotated[int, Field(ge=0)]
    exit_price: Annotated[int, Field(ge=0)]
    quantity: Annotated[int, Field(ge=1)]
    timestamp: datetime
    pnl: Annotated[int, Field(description="PnL in cents")]

class BacktestResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    total_pnl: Annotated[int, Field(description="Total PnL in cents")]
    win_rate: float
    trade_count: int
    sharpe_ratio: float
    max_drawdown: float
    brier_score: float
    edge_capture: float
    fill_rate: float
    trades: list[BacktestTrade]
    config: BacktestConfig

class Context(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    portfolio: PortfolioState
    market_data: List[Market]
    sentiment: Dict[str, object]
    risk_state: Dict[str, object]

class Strategy(Protocol):
    def on_market_open(self, context: Context) -> None:
        ...

    def on_trade(self, context: Context, trade: BacktestTrade) -> None:
        ...

    def on_settle(self, context: Context) -> None:
        ...