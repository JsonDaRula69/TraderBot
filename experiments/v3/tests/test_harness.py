import sqlite3

from experiments.v3.db_schema import create_tables
from experiments.v3.harness import Harness
from experiments.v3.llm_client import LLMResponse
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NUM_TIMESTEPS = 5


class MockTreatment(TreatmentInterface):
    """Minimal concrete treatment for testing."""

    def __init__(self, name: str = "mock"):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def format_prompt(self, ctx: TreatmentContext) -> str:
        return f"prompt:{self._name}:{ctx.market.ticker}:ts{ctx.timestep}"

    def validate_response(self, response: dict) -> bool:
        return response.get("decision") in ("buy_yes", "buy_no", "skip")


class MockLLMClient:
    """Pretend LLM client that returns a fixed response."""

    def __init__(self, decision: str = "skip", estimated_prob: float = 0.5,
                 confidence: float = 0.3, reasoning: str = "mock"):
        self.decision = decision
        self.estimated_prob = estimated_prob
        self.confidence = confidence
        self.reasoning = reasoning
        self.call_count = 0

    def call(self, prompt: str):
        self.call_count += 1
        return LLMResponse(
            decision=self.decision,
            estimated_prob=self.estimated_prob,
            confidence=self.confidence,
            reasoning=self.reasoning,
            raw_response="{}",
        )


def _make_context(ticker: str = "KXNYHI", timestep: int = 0) -> TreatmentContext:
    return TreatmentContext(
        market=MarketData(
            ticker=ticker, city="New York", strike_type="between",
            threshold=32.0, resolution_date="2025-01-15",
        ),
        forecast=ForecastData(
            forecast_temp_f=35.0, source="NWS", days_before=4, timestep=timestep,
        ),
        accuracy=AccuracyData(
            city="New York", lead_time=4, mae=2.5, bias=0.3, sample_count=100,
        ),
        prices=PriceData(
            yes_price=0.65, no_price=0.35, trade_count=50, open_interest=200,
            implied_prob=0.65,
        ),
        technicals=TechnicalData(
            rsi=55.0, bollinger_position=0.5, ema5=0.63, ema20=0.60,
            signal_direction="bullish", signal_confidence=0.7,
        ),
        prior=PriorDecisions(decisions=[]),
        timestep=timestep,
        remaining=NUM_TIMESTEPS - timestep,
    )


def _seed_db(conn: sqlite3.Connection, tickers: list[str] | None = None):
    if tickers is None:
        tickers = ["KXNYHI", "KXCHII"]

    for ticker in tickers:
        conn.execute(
            "INSERT OR REPLACE INTO markets (ticker, city, strike_type, threshold, resolution_date, settlement_result) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ticker, "New York", "between", 32.0, "2025-01-15", "yes"),
        )
        for ts in range(NUM_TIMESTEPS):
            conn.execute(
                "INSERT INTO market_prices (ticker, timestep, yes_price, no_price, trade_count, open_interest) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (ticker, ts, 0.65, 0.35, 50, 200),
            )
            conn.execute(
                "INSERT INTO forecast_snapshots (ticker, timestep, days_before, forecast_temp_f, source) "
                "VALUES (?, ?, ?, ?, ?)",
                (ticker, ts, 5 - ts, 35.0, "NWS"),
            )

    conn.execute(
        "INSERT INTO forecast_accuracy (city, lead_time, mae, bias, sample_count, low_confidence) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("New York", 4, 2.5, 0.3, 100, 0),
    )
    conn.commit()


def _make_harness(conn: sqlite3.Connection, llm: MockLLMClient | None = None,
                  seed: int = 42) -> Harness:
    if llm is None:
        llm = MockLLMClient()
    return Harness(conn=conn, llm_client=llm, seed=seed)


# ---------------------------------------------------------------------------
# Test 1: Decision count = treatments x markets x timesteps x replicates
# ---------------------------------------------------------------------------


class TestDecisionCount:

    def test_total_decision_count(self):
        conn = sqlite3.connect(":memory:")
        create_tables(conn)
        _seed_db(conn, tickers=["KXNYHI"])

        treatments = [MockTreatment("control"), MockTreatment("treatment_a")]
        harness = _make_harness(conn, MockLLMClient(decision="skip"))

        harness.run(treatments, run_id="run_count", replicates=2, markets_per_cell=2)

        cur = conn.execute("SELECT COUNT(*) FROM treatment_decisions WHERE run_id = ?", ("run_count",))
        count = cur.fetchone()[0]
        # 2 treatments x 1 market x 5 timesteps x 2 replicates = 20
        assert count == 20


# ---------------------------------------------------------------------------
# Test 2: Within-subjects -- each market sees ALL treatments
# ---------------------------------------------------------------------------


class TestWithinSubjects:

    def test_each_market_sees_all_treatments(self):
        conn = sqlite3.connect(":memory:")
        create_tables(conn)
        _seed_db(conn, tickers=["KXNYHI"])

        treatments = [MockTreatment("control"), MockTreatment("treatment_a")]
        harness = _make_harness(conn, MockLLMClient(decision="skip"))

        harness.run(treatments, run_id="run_ws", replicates=1, markets_per_cell=2)

        cur = conn.execute(
            "SELECT DISTINCT treatment_name FROM treatment_decisions WHERE run_id = ? AND ticker = ?",
            ("run_ws", "KXNYHI"),
        )
        treatment_names = {row[0] for row in cur.fetchall()}
        assert treatment_names == {"control", "treatment_a"}


# ---------------------------------------------------------------------------
# Test 3: Treatment order randomized per market
# ---------------------------------------------------------------------------


class TestTreatmentOrderRandomization:

    def test_order_differs_across_markets(self):
        conn = sqlite3.connect(":memory:")
        create_tables(conn)

        harness = _make_harness(conn, MockLLMClient(), seed=99)

        treatments = [MockTreatment("A"), MockTreatment("B"), MockTreatment("C")]
        order_a = harness._randomize_treatment_order(treatments, "KXNYHI", 0)
        order_b = harness._randomize_treatment_order(treatments, "KXCHII", 0)

        order_a2 = harness._randomize_treatment_order(treatments, "KXNYHI", 0)
        assert order_a == order_a2
        assert set(t.name for t in order_a) == set(t.name for t in order_b)
        assert set(t.name for t in order_a) == {"A", "B", "C"}

    def test_order_is_permutation_of_treatments(self):
        harness = _make_harness(
            sqlite3.connect(":memory:"), MockLLMClient(), seed=42,
        )
        treatments = [MockTreatment("X"), MockTreatment("Y")]
        order = harness._randomize_treatment_order(treatments, "TICK1", 0)
        names = [t.name for t in order]
        assert sorted(names) == ["X", "Y"]


# ---------------------------------------------------------------------------
# Test 4: Checkpoint / resume
# ---------------------------------------------------------------------------


class TestCheckpointResume:

    def test_resume_skips_completed_markets(self):
        conn = sqlite3.connect(":memory:")
        create_tables(conn)
        _seed_db(conn, tickers=["TICK1", "TICK2", "TICK3"])

        treatments = [MockTreatment("control"), MockTreatment("treatment_a")]
        llm = MockLLMClient(decision="skip")

        harness = _make_harness(conn, llm, seed=42)
        harness.run(treatments, run_id="run_resume", replicates=1, markets_per_cell=3)

        harness2 = _make_harness(conn, MockLLMClient(decision="skip"), seed=42)
        harness2.resume("run_resume")

        completed = harness2._get_completed_market_replicates("run_resume")
        assert ("TICK1", 0) in completed
        assert ("TICK2", 0) in completed
        assert ("TICK3", 0) in completed


# ---------------------------------------------------------------------------
# Test 5: store_decision writes correct columns
# ---------------------------------------------------------------------------


class TestStoreDecision:

    def test_stores_all_columns(self):
        conn = sqlite3.connect(":memory:")
        create_tables(conn)

        harness = _make_harness(conn)

        resp = LLMResponse(
            decision="buy_yes", estimated_prob=0.72,
            confidence=0.65, reasoning="looks good",
            raw_response='{"decision":"buy_yes"}',
        )
        harness._store_decision(
            run_id="run_store", ticker="KXNYHI", timestep=2,
            treatment_name="control", replicate=1, response=resp,
        )

        cur = conn.execute(
            "SELECT run_id, ticker, timestep, treatment_name, replicate, "
            "decision, estimated_prob, confidence, reasoning, position_size_cents "
            "FROM treatment_decisions WHERE run_id = ?",
            ("run_store",),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "run_store"
        assert row[1] == "KXNYHI"
        assert row[2] == 2
        assert row[3] == "control"
        assert row[4] == 1
        assert row[5] == "buy_yes"
        assert abs(row[6] - 0.72) < 1e-6
        assert abs(row[7] - 0.65) < 1e-6
        assert row[8] == "looks good"
        assert row[9] == 100


# ---------------------------------------------------------------------------
# Test 6: LLM returning buy_yes with estimated_prob=0.72
# ---------------------------------------------------------------------------


class TestBuyYesDecision:

    def test_buy_yes_stored_correctly(self):
        conn = sqlite3.connect(":memory:")
        create_tables(conn)
        _seed_db(conn, tickers=["KXNYHI"])

        treatments = [MockTreatment("control")]
        llm = MockLLMClient(decision="buy_yes", estimated_prob=0.72,
                             confidence=0.85, reasoning="upside")

        harness = _make_harness(conn, llm, seed=42)
        harness.run(treatments, run_id="run_buyyes", replicates=1, markets_per_cell=2)

        cur = conn.execute(
            "SELECT decision, estimated_prob, confidence, reasoning "
            "FROM treatment_decisions WHERE run_id = ? AND treatment_name = ? LIMIT 1",
            ("run_buyyes", "control"),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "buy_yes"
        assert abs(row[1] - 0.72) < 1e-6
        assert abs(row[2] - 0.85) < 1e-6
        assert row[3] == "upside"
