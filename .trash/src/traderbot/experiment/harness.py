"""Within-subjects experiment harness.

Executes treatment conditions across stratified market samples,
recording agent decisions for each (treatment, market, timestep) cell.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from traderbot.analysis.indicators import bollinger_bands, ema
from traderbot.analysis.indicators import rsi as calc_rsi
from traderbot.experiment.methodologies.db_utils import select_markets
from traderbot.experiment.shared import (
    AccuracyData,
    ForecastData,
    MarketData,
    PriceData,
    PriorDecisions,
    TechnicalData,
    TreatmentContext,
    TreatmentInterface,
    ValidatedDecision,
)
from traderbot.llm.client import LLMClient, LLMClientError

if TYPE_CHECKING:
    import sqlite3

logger = logging.getLogger(__name__)


def _load_market_row(conn: sqlite3.Connection, ticker: str) -> dict | None:
    """Fetch a single market row from the markets table."""
    row = conn.execute("SELECT * FROM markets WHERE ticker = ?", (ticker,)).fetchone()
    if row is None:
        return None
    cols = [desc[0] for desc in conn.execute("SELECT * FROM markets LIMIT 0").description]
    return dict(zip(cols, row, strict=False))


def _load_forecasts(conn: sqlite3.Connection, ticker: str) -> list[dict]:
    """Fetch forecast snapshots for a market."""
    rows = conn.execute(
        "SELECT forecast_temp_f, source, days_before FROM forecast_snapshots WHERE ticker = ?",
        (ticker,),
    ).fetchall()
    return [{"forecast_temp_f": r[0], "source": r[1], "days_before": r[2]} for r in rows]


def _load_price_history(conn: sqlite3.Connection, ticker: str) -> list[dict]:
    """Fetch price history from market_prices, ordered by timestep."""
    rows = conn.execute(
        "SELECT timestep, yes_price_cents, no_price_cents FROM market_prices "
        "WHERE ticker = ? ORDER BY timestep",
        (ticker,),
    ).fetchall()
    return [{"timestep": r[0], "yes_price_cents": r[1], "no_price_cents": r[2]} for r in rows]


def _build_market_data(row: dict) -> MarketData:
    """Construct MarketData from a DB row dict."""
    return MarketData(
        ticker=row["ticker"],
        strike_type=row.get("strike_type") or "between",
        threshold=row.get("strike_value") or 0.0,
        expiration=datetime.fromisoformat(row.get("resolution_date", "2099-12-31")),
        category=row.get("city_prefix", ""),
    )


def _build_forecast_data(forecasts: list[dict]) -> ForecastData:
    """Build ForecastData from the first available forecast snapshot."""
    if forecasts:
        f = forecasts[0]
        return ForecastData(
            forecast_temp_f=f["forecast_temp_f"],
            source=f["source"],
            days_before=f["days_before"],
        )
    return ForecastData(forecast_temp_f=0.0, source="none", days_before=0)


def _build_accuracy_data(conn: sqlite3.Connection, ticker: str) -> AccuracyData:
    """Build AccuracyData from prior decisions for this ticker."""
    rows = conn.execute(
        "SELECT estimated_prob, confidence FROM agent_decisions WHERE ticker = ? LIMIT 50",
        (ticker,),
    ).fetchall()
    return AccuracyData(
        brier_score=None,
        calibration_error=None,
        sample_size=len(rows),
    )


def _build_price_data(price_history: list[dict], current: dict) -> PriceData:
    """Build PriceData from price history and current timestep."""
    history = [p["yes_price_cents"] for p in price_history]
    spread = abs(current["yes_price_cents"] - current["no_price_cents"])
    return PriceData(
        current_yes_cents=current["yes_price_cents"],
        current_no_cents=current["no_price_cents"],
        history=history,
        spread_cents=spread,
    )


def _build_technical_data(price_history: list[dict]) -> TechnicalData:
    """Build TechnicalData — computed from price history."""
    prices = [p["yes_price_cents"] for p in price_history]
    rsi_val = None
    bb_upper = None
    bb_lower = None
    ema_short = None
    ema_long = None
    if len(prices) >= 2:
        rsi_val = calc_rsi(prices, period=14)
        bb = bollinger_bands(prices, period=20, k=2.0)
        bb_upper = bb.upper
        bb_lower = bb.lower
        if len(prices) >= 5:
            ema_short = ema(prices, 5)
        if len(prices) >= 20:
            ema_long = ema(prices, 20)
    return TechnicalData(
        rsi=rsi_val,
        bb_upper=bb_upper,
        bb_lower=bb_lower,
        ema_short=ema_short,
        ema_long=ema_long,
    )


def _build_prior_decisions(
    conn: sqlite3.Connection, run_id: str, ticker: str, treatment_name: str
) -> PriorDecisions:
    """Fetch prior decisions for this run/ticker/treatment to pass as context."""
    rows = conn.execute(
        "SELECT decision, estimated_prob, confidence, reasoning, timestep "
        "FROM agent_decisions WHERE run_id = ? AND ticker = ? AND treatment = ? "
        "ORDER BY timestep",
        (run_id, ticker, treatment_name),
    ).fetchall()
    decisions = [
        {
            "decision": r[0],
            "estimated_prob": r[1],
            "confidence": r[2],
            "reasoning": r[3],
            "timestep": r[4],
        }
        for r in rows
    ]
    return PriorDecisions(decisions=decisions)


def _control_decision(current_yes_cents: int) -> ValidatedDecision:
    """Generate a control decision using market-implied probability.

    For the bypass_llm control treatment, we skip the full signal pipeline
    (which requires OrderBook data we don't have in the experiment DB)
    and derive a straightforward decision from the current market price.
    """
    estimated_prob = current_yes_cents / 100.0
    if estimated_prob > 0.55:
        decision: str = "buy_yes"
    elif estimated_prob < 0.45:
        decision = "buy_no"
    else:
        decision = "skip"
    confidence = min(1.0, abs(estimated_prob - 0.5) * 2)
    return ValidatedDecision(
        decision=decision,
        estimated_prob=estimated_prob,
        confidence=confidence,
        reasoning="Control: market-implied probability",
    )


def _record_decision(
    conn: sqlite3.Connection,
    run_id: str,
    treatment_name: str,
    ticker: str,
    timestep: int,
    vd: ValidatedDecision,
) -> None:
    """Insert a validated decision into agent_decisions."""
    conn.execute(
        "INSERT INTO agent_decisions "
        "(run_id, treatment, ticker, timestep, decision, estimated_prob, confidence, reasoning, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            treatment_name,
            ticker,
            timestep,
            vd.decision,
            vd.estimated_prob,
            vd.confidence,
            vd.reasoning,
            datetime.now(UTC).isoformat(),
        ),
    )
    conn.commit()


class Harness:
    """Execute within-subjects experiments across treatment conditions.

    Parameters
    ----------
    conn : sqlite3.Connection
        Connection to the experiment database.
    llm_client : LLMClient
        Client for querying the LLM provider.
    seed : int
        Random seed for market stratification (passed to select_markets).
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        llm_client: LLMClient,
        seed: int = 42,
    ) -> None:
        self.conn = conn
        self.llm_client = llm_client
        self.seed = seed

    def run(
        self,
        treatment_instances: list[TreatmentInterface],
        run_id: str,
        replicates: int = 3,
        markets_per_cell: int = 2,
    ) -> None:
        """Run the experiment: all treatments across all markets and timesteps.

        Parameters
        ----------
        treatment_instances : list[TreatmentInterface]
            Treatment objects implementing TreatmentInterface.
        run_id : str
            Unique identifier for this experiment run.
        replicates : int
            Number of times to repeat the full market set.
        markets_per_cell : int
            Number of markets per stratification cell.
        """
        cells = select_markets(self.conn, markets_per_cell, self.seed)

        tickers: list[str] = []
        for cell_tickers in cells.values():
            tickers.extend(cell_tickers)

        if not tickers:
            logger.warning("No markets selected for experiment run %s", run_id)
            return

        logger.info(
            "Running experiment %s: %d tickers, %d replicates, %d treatments",
            run_id,
            len(tickers),
            replicates,
            len(treatment_instances),
        )

        for rep in range(replicates):
            logger.info("Replicate %d/%d", rep + 1, replicates)

            for ticker in tickers:
                self._run_ticker(treatment_instances, run_id, ticker)

    def _run_ticker(
        self,
        treatment_instances: list[TreatmentInterface],
        run_id: str,
        ticker: str,
    ) -> None:
        """Run all treatments for a single market across its timesteps."""
        market_row = _load_market_row(self.conn, ticker)
        if market_row is None:
            logger.warning("Market %s not found in DB, skipping", ticker)
            return

        forecasts = _load_forecasts(self.conn, ticker)
        price_history = _load_price_history(self.conn, ticker)

        if not price_history:
            logger.warning("No price data for %s, skipping", ticker)
            return

        market_data = _build_market_data(market_row)
        forecast_data = _build_forecast_data(forecasts)
        accuracy_data = _build_accuracy_data(self.conn, ticker)
        technical_data = _build_technical_data(price_history)

        for price_point in price_history:
            timestep = price_point["timestep"]
            price_data = _build_price_data(price_history, price_point)

            for treatment in treatment_instances:
                try:
                    vd = self._execute_treatment(
                        treatment=treatment,
                        market_data=market_data,
                        forecast_data=forecast_data,
                        accuracy_data=accuracy_data,
                        price_data=price_data,
                        technical_data=technical_data,
                        run_id=run_id,
                        ticker=ticker,
                        timestep=timestep,
                    )
                    _record_decision(
                        self.conn,
                        run_id,
                        treatment.name,
                        ticker,
                        timestep,
                        vd,
                    )
                except Exception:
                    logger.exception(
                        "Treatment %s failed for %s timestep %d, skipping",
                        treatment.name,
                        ticker,
                        timestep,
                    )

    def _execute_treatment(
        self,
        treatment: TreatmentInterface,
        market_data: MarketData,
        forecast_data: ForecastData,
        accuracy_data: AccuracyData,
        price_data: PriceData,
        technical_data: TechnicalData,
        run_id: str,
        ticker: str,
        timestep: int,
    ) -> ValidatedDecision:
        """Execute a single treatment: either bypass LLM or query + validate."""
        prior = _build_prior_decisions(self.conn, run_id, ticker, treatment.name)

        # Build context (step 2 of 8-step loop)
        ctx = TreatmentContext(
            market=market_data,
            forecast=forecast_data,
            accuracy=accuracy_data,
            prices=price_data,
            technical=technical_data,
            prior=prior,
        )

        if treatment.bypass_llm:
            # Control treatment: use market-implied probability directly
            return _control_decision(price_data.current_yes_cents)

        # Step 3: format_prompt
        prompt = treatment.format_prompt(ctx)

        # Step 4: Query LLM
        try:
            response_text = self.llm_client.query(prompt)
        except LLMClientError:
            logger.warning(
                "LLM query failed for %s/%s timestep %d, using skip decision",
                treatment.name,
                ticker,
                timestep,
            )
            raise

        # Step 5: Parse JSON response
        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse LLM response as JSON for %s/%s timestep %d: %.200s",
                treatment.name,
                ticker,
                timestep,
                response_text,
            )
            raise

        # Step 6: validate_response
        return treatment.validate_response(parsed)
