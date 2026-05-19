import hashlib
import json
import logging
import random
import sqlite3
from pathlib import Path

from experiments.v3.db_schema import create_tables
from experiments.v3.llm_client import LLMClient, LLMResponse
from experiments.v3.market_selector import select_markets
from experiments.v3.treatment_interface import (
    AccuracyData,
    ForecastData,
    MarketData,
    PriceData,
    PriorDecisions,
    TechnicalData,
    TreatmentContext,
    TreatmentInterface,
)

logger = logging.getLogger(__name__)

NUM_TIMESTEPS = 5
POSITION_SIZE_CENTS = 100

def _load_openclaw_context(
    workspace_dir: str | Path | None = None,
    file_list: list[str] | None = None,
) -> str:
    """Read OpenClaw workspace files and format them as a system context string.

    Args:
        workspace_dir: Path to the OpenClaw workspace. Defaults to
            ~/.openclaw/workspace.
        file_list: List of filenames to include. Defaults to a curated list
            of production agent context files.

    Returns:
        Formatted string containing all found workspace files, or empty
        string if the directory doesn't exist.
    """
    if file_list is None:
        file_list = [
            "AGENTS.md",
            "SOUL.md",
            "TOOLS.md",
            "BOOTSTRAP.md",
            "HEARTBEAT.md",
            "IDENTITY.md",
            "USER.md",
            "SESSION-STATE.md",
        ]

    if workspace_dir is None:
        workspace_dir = Path.home() / ".openclaw" / "workspace"
    else:
        workspace_dir = Path(workspace_dir)

    if not workspace_dir.is_dir():
        logger.warning("OpenClaw workspace not found at %s, skipping context", workspace_dir)
        return ""

    sections: list[str] = []
    for filename in file_list:
        filepath = workspace_dir / filename
        if filepath.is_file():
            content = filepath.read_text(encoding="utf-8").strip()
            if content:
                sections.append(f"=== {filename} ===\n{content}")

    if not sections:
        logger.warning("No OpenClaw workspace files found in %s", workspace_dir)
        return ""

    return "\n\n".join(sections)


class Harness:
    def __init__(self, conn: sqlite3.Connection, llm_client: LLMClient, seed: int = 42, workspace_dir: str | Path | None = None, openclaw_files: list[str] | None = None):
        self.conn = conn
        self.llm = llm_client
        self.rng = random.Random(seed)
        self.seed = seed
        self.system_context = _load_openclaw_context(workspace_dir, openclaw_files)

    def run(
        self,
        treatments: list[TreatmentInterface],
        run_id: str,
        replicates: int = 3,
        markets_per_cell: int = 2,
    ) -> None:
        create_tables(self.conn)

        all_tickers = select_markets(
            self.conn, markets_per_cell=markets_per_cell, seed=self.seed,
        )
        flat_tickers = [t for tickers in all_tickers.values() for t in tickers]
        if not flat_tickers:
            logger.warning("No markets selected for run_id=%s", run_id)
            return

        treatment_names = json.dumps([t.name for t in treatments])
        self.conn.execute(
            "INSERT OR REPLACE INTO experiment_runs "
            "(run_id, treatment_names_json, num_markets, num_replicates, seed, timestamp, status) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'), ?)",
            (run_id, treatment_names, len(flat_tickers), replicates, self.seed, "running"),
        )
        self.conn.commit()

        completed = self._get_completed_market_replicates(run_id)

        for ticker in flat_tickers:
            for replicate in range(replicates):
                if (ticker, replicate) in completed:
                    logger.info("Skipping %s rep=%d (already done)", ticker, replicate)
                    continue
                self._run_market(treatments, run_id, ticker, replicate)
                self._checkpoint(run_id, ticker, replicate)

        self.conn.execute(
            "UPDATE experiment_runs SET status = ? WHERE run_id = ?",
            ("completed", run_id),
        )
        self.conn.commit()

    def _run_market(
        self,
        treatments: list[TreatmentInterface],
        run_id: str,
        ticker: str,
        replicate: int,
    ) -> None:
        ordered = self._randomize_treatment_order(treatments, ticker, replicate)

        for timestep in range(NUM_TIMESTEPS):
            ctx = self._build_treatment_context(ticker, timestep)
            if ctx is None:
                logger.warning("Cannot build context for %s ts=%d, skipping", ticker, timestep)
                continue

            for treatment in ordered:
                prompt = treatment.format_prompt(ctx)
                response = self.llm.call(prompt)

                if not treatment.validate_response({"decision": response.decision,
                                                     "estimated_prob": response.estimated_prob,
                                                     "confidence": response.confidence,
                                                     "reasoning": response.reasoning}):
                    logger.warning(
                        "Invalid response from %s for %s ts=%d: decision=%s",
                        treatment.name, ticker, timestep, response.decision,
                    )
                    continue

                self._store_decision(run_id, ticker, timestep, treatment.name, replicate, response)

    def _randomize_treatment_order(
        self, treatments: list[TreatmentInterface], ticker: str, replicate: int,
    ) -> list[TreatmentInterface]:
        key = f"{ticker}:{replicate}:{self.seed}"
        sub_seed = int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2**32)
        local_rng = random.Random(sub_seed)
        ordered = list(treatments)
        local_rng.shuffle(ordered)
        return ordered

    def _build_treatment_context(self, ticker: str, timestep: int) -> TreatmentContext | None:
        market_row = self.conn.execute(
            "SELECT ticker, city, strike_type, threshold, resolution_date, "
            "floor_strike, ceiling_strike, settlement_result "
            "FROM markets WHERE ticker = ?",
            (ticker,),
        ).fetchone()
        if market_row is None:
            return None

        market = MarketData(
            ticker=market_row[0],
            city=market_row[1] or "",
            strike_type=market_row[2] or "between",
            threshold=market_row[3] or 0.0,
            resolution_date=market_row[4] or "",
            floor_strike=market_row[5],
            ceiling_strike=market_row[6],
            settlement_result=market_row[7],
        )

        forecast_row = self.conn.execute(
            "SELECT forecast_temp_f, source, days_before, timestep "
            "FROM forecast_snapshots WHERE ticker = ? AND timestep = ? "
            "ORDER BY id DESC LIMIT 1",
            (ticker, timestep),
        ).fetchone()
        forecast = ForecastData(
            forecast_temp_f=forecast_row[0] if forecast_row else 0.0,
            source=forecast_row[1] if forecast_row else "unknown",
            days_before=forecast_row[2] if forecast_row else 0,
            timestep=forecast_row[3] if forecast_row else timestep,
        )

        accuracy_row = self.conn.execute(
            "SELECT city, lead_time, mae, bias, sample_count, low_confidence "
            "FROM forecast_accuracy WHERE city = ? ORDER BY id DESC LIMIT 1",
            (market.city,),
        ).fetchone()
        accuracy = AccuracyData(
            city=accuracy_row[0] if accuracy_row else market.city,
            lead_time=accuracy_row[1] if accuracy_row else 0,
            mae=accuracy_row[2] if accuracy_row else 0.0,
            bias=accuracy_row[3] if accuracy_row else 0.0,
            sample_count=accuracy_row[4] if accuracy_row else 0,
            low_confidence=bool(accuracy_row[5]) if accuracy_row else False,
        )

        ob_row = self.conn.execute(
            "SELECT best_yes_bid, best_no_bid, implied_prob "
            "FROM orderbook_snapshots WHERE ticker = ? AND timestep = ? "
            "ORDER BY id DESC LIMIT 1",
            (ticker, timestep),
        ).fetchone()

        mp_row = self.conn.execute(
            "SELECT yes_price, no_price, trade_count, open_interest "
            "FROM market_prices WHERE ticker = ? AND timestep = ? "
            "ORDER BY id DESC LIMIT 1",
            (ticker, timestep),
        ).fetchone()

        yes_price = ob_row[0] if ob_row else (mp_row[0] if mp_row else 0.5)
        no_price = ob_row[1] if ob_row else (mp_row[1] if mp_row else 0.5)
        trade_count = mp_row[2] if mp_row else 0
        open_interest = mp_row[3] if mp_row else 0
        implied_prob = ob_row[2] if ob_row else yes_price

        prices = PriceData(
            yes_price=yes_price,
            no_price=no_price,
            trade_count=trade_count,
            open_interest=open_interest,
            implied_prob=implied_prob,
        )

        technicals = TechnicalData(
            rsi=50.0, bollinger_position=0.5,
            ema5=prices.implied_prob, ema20=prices.implied_prob,
            signal_direction="neutral", signal_confidence=0.5,
        )

        prior_decisions = self.conn.execute(
            "SELECT decision, estimated_prob, confidence, reasoning "
            "FROM treatment_decisions WHERE ticker = ? AND timestep < ? AND run_id = ("
            "SELECT run_id FROM experiment_runs ORDER BY timestamp DESC LIMIT 1)",
            (ticker, timestep),
        ).fetchall()
        prior = PriorDecisions(
            decisions=[{"decision": r[0], "estimated_prob": r[1],
                        "confidence": r[2], "reasoning": r[3]} for r in prior_decisions],
        )

        return TreatmentContext(
            market=market,
            forecast=forecast,
            accuracy=accuracy,
            prices=prices,
            technicals=technicals,
            prior=prior,
            timestep=timestep,
            remaining=NUM_TIMESTEPS - timestep,
            system_context=self.system_context,
        )

    def _store_decision(
        self,
        run_id: str,
        ticker: str,
        timestep: int,
        treatment_name: str,
        replicate: int,
        response: LLMResponse,
    ) -> None:
        self.conn.execute(
            "INSERT INTO treatment_decisions "
            "(run_id, ticker, timestep, treatment_name, replicate, "
            "decision, estimated_prob, confidence, reasoning, position_size_cents) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, ticker, timestep, treatment_name, replicate,
             response.decision, response.estimated_prob, response.confidence,
             response.reasoning, POSITION_SIZE_CENTS),
        )
        self.conn.commit()

    def checkpoint(self) -> None:
        self.conn.commit()

    def resume(self, run_id: str) -> None:
        pass

    def _get_completed_market_replicates(self, run_id: str) -> set[tuple[str, int]]:
        cur = self.conn.execute(
            "SELECT status FROM experiment_runs WHERE run_id = ?",
            (run_id,),
        )
        row = cur.fetchone()
        if row is None:
            return set()

        cur = self.conn.execute(
            "SELECT ticker, replicate FROM treatment_decisions WHERE run_id = ? "
            "GROUP BY ticker, replicate "
            "HAVING COUNT(DISTINCT timestep) = ? AND COUNT(DISTINCT treatment_name) = ("
            "  SELECT COUNT(DISTINCT treatment_name) FROM treatment_decisions WHERE run_id = ?"
            ")",
            (run_id, NUM_TIMESTEPS, run_id),
        )
        return {(row[0], row[1]) for row in cur.fetchall()}

    def _checkpoint(self, run_id: str, ticker: str, replicate: int) -> None:
        self.conn.execute(
            "UPDATE experiment_runs SET status = ? WHERE run_id = ?",
            (f"checkpoint:{ticker}:{replicate}", run_id),
        )
        self.conn.commit()

        from experiments.v3.db_schema import verify_schema
        verify_schema(self.conn)
