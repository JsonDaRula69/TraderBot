import argparse
import importlib
import json
import logging
import os
import sqlite3
import sys
from collections.abc import Sequence

from experiments.v3.db_schema import create_tables
from experiments.v3.market_selector import select_markets

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="experiments.v3",
        description="Run v3 experiment harness over prediction-market treatments.",
    )
    parser.add_argument(
        "--db",
        required=True,
        help="Path to the SQLite database file.",
    )
    parser.add_argument(
        "--control",
        required=False,
        default=None,
        help="Module path for the control treatment (e.g. experiments.treatments.control). Required for full runs.",
    )
    parser.add_argument(
        "--treatments",
        type=str,
        default=None,
        help="Comma-separated module paths for additional treatments (max 3).",
    )
    parser.add_argument(
        "--markets",
        type=int,
        default=2,
        help="Number of markets to select per stratum cell (default: 2).",
    )
    parser.add_argument(
        "--replicates",
        type=int,
        default=3,
        help="Number of replicates per market (default: 3).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for market selection and treatment ordering (default: 42).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="glm-5.1:cloud",
        help="LLM model identifier (default: glm-5.1:cloud).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional JSON path to write experiment summary.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate treatments and print market preview without calling the LLM.",
    )
    parser.add_argument(
        "--verify-data",
        action="store_true",
        help="Connect to DB, count markets, check coverage, and print summary.",
    )
    parser.add_argument(
        "--populate-db",
        action="store_true",
        help="Fetch real data from Kalshi + Open-Meteo and populate the database.",
    )
    parser.add_argument(
        "--event-prefix",
        type=str,
        default="KXHIGH",
        help="Kalshi event prefix to fetch (default: KXHIGH).",
    )
    parser.add_argument(
        "--max-markets",
        type=int,
        default=50,
        help="Max markets to fetch when populating (default: 50).",
    )
    parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help="Path to OpenClaw workspace directory (default: ~/.openclaw/workspace).",
    )
    return parser


def _load_treatment(module_path: str):
    module = importlib.import_module(module_path)
    class_name = _to_class_name(module_path.split(".")[-1])
    if not hasattr(module, class_name):
        raise ValueError(
            f"Module {module_path} does not export a class named {class_name}"
        )
    cls = getattr(module, class_name)
    instance = cls()
    if not hasattr(instance, "name") or not callable(getattr(instance, "format_prompt", None)):
        raise ValueError(f"{class_name} from {module_path} does not satisfy TreatmentInterface")
    return instance


def _to_class_name(module_name: str) -> str:
    parts = module_name.replace("-", "_").split("_")
    return "".join(p.capitalize() for p in parts) + "Treatment"


def _verify_data(conn: sqlite3.Connection) -> dict:
    cur = conn.execute("SELECT COUNT(*) FROM markets")
    market_count = cur.fetchone()[0]

    cur = conn.execute(
        """
        SELECT COUNT(DISTINCT ticker) FROM forecast_snapshots
        """
    )
    forecast_tickers = cur.fetchone()[0]

    cur = conn.execute(
        """
        SELECT COUNT(DISTINCT ticker) FROM market_prices WHERE timestep = 0
        """
    )
    price_tickers = cur.fetchone()[0]

    summary = {
        "markets": market_count,
        "forecast_coverage": forecast_tickers,
        "price_coverage": price_tickers,
    }
    return summary


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(), format="%(message)s")

    if args.populate_db:
        from experiments.v3.data_sources.populate_db import populate_db
        populate_db(args.db, args.event_prefix, args.max_markets)
        return

    if args.verify_data:
        conn = sqlite3.connect(args.db)
        create_tables(conn)
        summary = _verify_data(conn)
        conn.close()
        print(
            f"Data verification: {summary['markets']} markets, "
            f"{summary['forecast_coverage']} with forecasts, "
            f"{summary['price_coverage']} with prices."
        )
        sys.exit(0)

    if not args.control:
        parser.error("--control is required for experiment runs")

    treatments = [_load_treatment(args.control)]
    if args.treatments:
        extra = [t.strip() for t in args.treatments.split(",") if t.strip()]
        if len(extra) > 3:
            parser.error("--treatments accepts at most 3 additional treatments")
        for path in extra:
            treatments.append(_load_treatment(path))

    if args.dry_run:
        conn = sqlite3.connect(args.db)
        create_tables(conn)
        preview = select_markets(conn, markets_per_cell=args.markets, seed=args.seed)
        conn.close()
        print(f"Dry-run: Loaded {len(treatments)} treatment(s).")
        print(f"Dry-run: Market selection preview — {len(preview)} stratum cell(s), "
              f"{sum(len(v) for v in preview.values())} total market(s).")
        for cell, tickers in preview.items():
            print(f"  {cell}: {', '.join(tickers) if tickers else '(none)'}")
        sys.exit(0)

    if not os.path.exists(args.db):
        parser.error(f"Database not found: {args.db}")

    conn = sqlite3.connect(args.db)
    create_tables(conn)

    from experiments.v3.harness import Harness
    from experiments.v3.llm_client import LLMClient

    llm_client = LLMClient(model=args.model)
    harness = Harness(conn, llm_client, seed=args.seed, workspace_dir=args.workspace)

    treatment_names = [t.name for t in treatments]
    run_id = f"v3_{'_'.join(treatment_names)}_seed{args.seed}"
    harness.run(treatments, run_id=run_id, replicates=args.replicates, markets_per_cell=args.markets)

    conn.close()

    if args.output:
        summary = {
            "run_id": run_id,
            "treatments": treatment_names,
            "markets_per_cell": args.markets,
            "replicates": args.replicates,
            "seed": args.seed,
            "model": args.model,
        }
        with open(args.output, "w") as fh:
            json.dump(summary, fh, indent=2)


if __name__ == "__main__":
    main()
