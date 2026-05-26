"""Tests for traderbot.experiment.results."""

from traderbot.experiment.results import ExperimentResults, score_run


def test_improvement_true() -> None:
    """improvement is True when p < 0.05 and effect_size > 0."""
    r = ExperimentResults(
        treatment="calibration_bundle",
        control="control",
        delta_profit=5.0,
        t_stat=3.0,
        p_value=0.01,
        effect_size=0.8,
        ci_low=1.0,
        ci_high=9.0,
        n_markets=30,
    )
    assert r.improvement is True


def test_improvement_false_high_p() -> None:
    """improvement is False when p >= 0.05."""
    r = ExperimentResults(
        treatment="calibration_bundle",
        control="control",
        delta_profit=1.0,
        t_stat=0.5,
        p_value=0.60,
        effect_size=0.1,
        ci_low=-2.0,
        ci_high=4.0,
        n_markets=30,
    )
    assert r.improvement is False


def test_to_json_keys() -> None:
    """to_json should contain all expected keys."""
    r = ExperimentResults(
        treatment="calibration_bundle",
        control="control",
        delta_profit=3.0,
        t_stat=2.0,
        p_value=0.04,
        effect_size=0.5,
        ci_low=0.5,
        ci_high=5.5,
        n_markets=20,
    )
    j = r.to_json()
    expected_keys = {
        "treatment", "control", "delta_profit", "t_stat", "p_value",
        "effect_size", "ci_low", "ci_high", "n_markets", "improvement",
    }
    assert set(j.keys()) == expected_keys


def test_score_run_empty_db() -> None:
    """score_run on a DB with no decisions should return []."""
    import sqlite3
    from traderbot.db.experiment_schema import create_tables

    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    db_path = ":memory:"  # In-memory DB — score_run opens its own connection
    # score_run connects to a file path, so use a temp file for this test
    conn.close()

    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_file = f.name
    try:
        conn2 = sqlite3.connect(db_file)
        create_tables(conn2)
        conn2.close()
        result = score_run(db_file, "nonexistent_run")
        assert result == []
    finally:
        os.unlink(db_file)