"""Tests for traderbot.experiment.harness."""

import ast
import sqlite3
from unittest.mock import MagicMock

from traderbot.db.experiment_schema import create_tables
from traderbot.experiment.harness import Harness, _control_decision
from traderbot.experiment.shared import ValidatedDecision
from traderbot.llm.client import LLMClient


def _make_llm_client() -> LLMClient:
    """Build a mock LLMClient that returns canned JSON."""
    provider = MagicMock()
    provider.generate.return_value = (
        '{"decision": "skip", "estimated_prob": 0.5, "confidence": 0.5, "reasoning": "mocked"}'
    )
    return LLMClient(provider=provider)


def _make_conn() -> sqlite3.Connection:
    """Create an in-memory DB with the experiment schema."""
    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    return conn


def test_harness_init() -> None:
    """Harness constructor accepts (conn, llm_client, seed)."""
    conn = _make_conn()
    llm = _make_llm_client()
    h = Harness(conn=conn, llm_client=llm, seed=99)
    assert h.seed == 99
    assert h.conn is conn
    assert h.llm_client is llm
    conn.close()


def test_harness_run_empty_db() -> None:
    """Harness.run with empty DB should not crash and record no decisions."""
    conn = _make_conn()
    llm = _make_llm_client()
    h = Harness(conn=conn, llm_client=llm, seed=42)
    from traderbot.experiment.treatments.control import ControlTreatment

    h.run(treatment_instances=[ControlTreatment()], run_id="test_empty")
    rows = conn.execute("SELECT COUNT(*) FROM agent_decisions").fetchone()
    assert rows[0] == 0
    conn.close()


def test_boundary_no_treatment_imports() -> None:
    """harness.py should not directly import treatment implementations (only shared)."""
    with open(__file__.rsplit("tests/", 1)[0] + "harness.py") as f:
        source = f.read()
    tree = ast.parse(source)
    treatment_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "treatments." in node.module and "shared" not in node.module:
                treatment_imports.append(node.module)
    assert treatment_imports == [], f"harness.py imports treatment impl: {treatment_imports}"


def test_control_decision() -> None:
    """_control_decision should produce a ValidatedDecision."""
    vd = _control_decision(current_yes_cents=70)
    assert isinstance(vd, ValidatedDecision)
    assert vd.decision in ("buy_yes", "buy_no", "skip")
    assert 0.0 <= vd.estimated_prob <= 1.0
    assert 0.0 <= vd.confidence <= 1.0
