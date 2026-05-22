"""Tests for experiments.v3.cli — argparse entry point and dry-run/verify modes."""

import io
import sqlite3
from unittest.mock import patch

import pytest

from experiments.v3.cli import build_parser, main


class TestArgparseParsing:
    def test_required_db(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_control_optional_for_dry_run(self):
        parser = build_parser()
        args = parser.parse_args(["--db", "/tmp/db.sqlite", "--dry-run"])
        assert args.control is None
        assert args.dry_run is True

    def test_defaults(self):
        parser = build_parser()
        args = parser.parse_args(
            ["--db", "/tmp/db.sqlite", "--control", "experiments.treatments.control"]
        )
        assert args.db == "/tmp/db.sqlite"
        assert args.control == "experiments.treatments.control"
        assert args.treatments is None
        assert args.markets == 2
        assert args.replicates == 3
        assert args.seed == 42
        assert args.model == "glm-5.1:cloud"
        assert args.output is None
        assert args.dry_run is False
        assert args.verify_data is False

    def test_all_args(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "--db", "/tmp/db.sqlite",
                "--control", "experiments.treatments.control",
                "--treatments", "foo,bar",
                "--markets", "5",
                "--replicates", "10",
                "--seed", "7",
                "--model", "custom-model",
                "--output", "/tmp/out.json",
                "--dry-run",
                "--verify-data",
            ]
        )
        assert args.db == "/tmp/db.sqlite"
        assert args.control == "experiments.treatments.control"
        assert args.treatments == "foo,bar"
        assert args.markets == 5
        assert args.replicates == 10
        assert args.seed == 7
        assert args.model == "custom-model"
        assert args.output == "/tmp/out.json"
        assert args.dry_run is True
        assert args.verify_data is True

    def test_help_shows_all_flags(self, capsys):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--help"])
        captured = capsys.readouterr()
        for flag in (
            "--db", "--control", "--treatments", "--markets",
            "--replicates", "--seed", "--model", "--output",
            "--dry-run", "--verify-data",
        ):
            assert flag in captured.out, f"{flag} missing from help"


# ---------------------------------------------------------------------------
# --dry-run tests
# ---------------------------------------------------------------------------


class TestDryRun:
    def _make_fake_treatment_class(self, name: str):
        """Return a minimal fake TreatmentInterface subclass."""
        from experiments.v3.treatment_interface import TreatmentInterface

        class FakeTreatment(TreatmentInterface):
            @property
            def name(self) -> str:
                return name

            def format_prompt(self, ctx):  # type: ignore[override]
                return "prompt"

            def validate_response(self, response):
                return True

        return FakeTreatment

    def test_dry_run_validates_treatments_and_exits(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        from experiments.v3.db_schema import create_tables
        create_tables(conn)
        conn.close()

        fake_control = self._make_fake_treatment_class("control")
        fake_treatment = self._make_fake_treatment_class("fake")

        with patch("experiments.v3.cli._load_treatment") as mock_load:
            mock_load.side_effect = [fake_control(), fake_treatment()]
            with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                with pytest.raises(SystemExit) as exc_info:
                    main(
                        [
                            "--db", db_path,
                            "--control", "experiments.treatments.control",
                            "--treatments", "experiments.treatments.fake",
                            "--dry-run",
                        ]
                    )
                assert exc_info.value.code == 0
                out = stdout.getvalue()
                assert "Dry-run" in out or "dry" in out.lower()


# ---------------------------------------------------------------------------
# --verify-data tests
# ---------------------------------------------------------------------------


class TestVerifyData:
    def test_verify_data_counts_markets(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        from experiments.v3.db_schema import create_tables
        create_tables(conn)
        # Seed a market and a price row at timestep 0
        conn.execute(
            "INSERT INTO markets (ticker, city, strike_type, settlement_result) VALUES (?, ?, ?, ?)",
            ("KXNYHI", "NewYork", "between", "YES"),
        )
        conn.execute(
            "INSERT INTO market_prices (ticker, timestep, yes_price, no_price, trade_count, open_interest) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("KXNYHI", 0, 0.5, 0.5, 10, 100),
        )
        conn.commit()
        conn.close()

        with patch("sys.stdout", new_callable=io.StringIO) as stdout:
            with pytest.raises(SystemExit) as exc_info:
                main(
                    [
                        "--db", db_path,
                        "--control", "experiments.treatments.control",
                        "--verify-data",
                    ]
                )
            assert exc_info.value.code == 0
            out = stdout.getvalue()
            assert "markets" in out.lower()
            assert "KXNYHI" in out or "1" in out

    def test_verify_data_empty_db(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        from experiments.v3.db_schema import create_tables
        create_tables(conn)
        conn.close()

        with patch("sys.stdout", new_callable=io.StringIO) as stdout:
            with pytest.raises(SystemExit) as exc_info:
                main(
                    [
                        "--db", db_path,
                        "--control", "experiments.treatments.control",
                        "--verify-data",
                    ]
                )
            assert exc_info.value.code == 0
            out = stdout.getvalue()
            assert "0" in out or "empty" in out.lower() or "no markets" in out.lower()
