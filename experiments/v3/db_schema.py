import sqlite3


TABLES: dict[str, str] = {
    "markets": """
        CREATE TABLE IF NOT EXISTS markets (
            ticker TEXT PRIMARY KEY,
            city TEXT,
            strike_type TEXT,
            floor_strike REAL,
            ceiling_strike REAL,
            threshold REAL,
            resolution_date TEXT,
            settlement_result TEXT,
            actual_value REAL,
            event_ticker TEXT,
            series_ticker TEXT
        )
    """,
    "forecast_snapshots": """
        CREATE TABLE IF NOT EXISTS forecast_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            timestep INTEGER,
            days_before INTEGER,
            forecast_temp_f REAL,
            source TEXT,
            forecast_date_raw TEXT
        )
    """,
    "market_prices": """
        CREATE TABLE IF NOT EXISTS market_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            timestep INTEGER,
            yes_price REAL,
            no_price REAL,
            trade_count INTEGER,
            open_interest INTEGER,
            extracted_at TEXT
        )
    """,
    "settlement_results": """
        CREATE TABLE IF NOT EXISTS settlement_results (
            ticker TEXT PRIMARY KEY,
            actual_temp_f REAL,
            settlement_result TEXT,
            settlement_source TEXT
        )
    """,
    "forecast_accuracy": """
        CREATE TABLE IF NOT EXISTS forecast_accuracy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT,
            lead_time INTEGER,
            mae REAL,
            bias REAL,
            sample_count INTEGER,
            low_confidence INTEGER DEFAULT 0
        )
    """,
    "orderbook_snapshots": """
        CREATE TABLE IF NOT EXISTS orderbook_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            timestep INTEGER,
            yes_bids_json TEXT,
            no_bids_json TEXT,
            best_yes_bid REAL,
            best_no_bid REAL,
            implied_prob REAL
        )
    """,
    "treatment_decisions": """
        CREATE TABLE IF NOT EXISTS treatment_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            ticker TEXT,
            timestep INTEGER,
            treatment_name TEXT,
            replicate INTEGER,
            decision TEXT,
            estimated_prob REAL,
            confidence REAL,
            reasoning TEXT,
            position_size_cents INTEGER DEFAULT 0
        )
    """,
    "experiment_runs": """
        CREATE TABLE IF NOT EXISTS experiment_runs (
            run_id TEXT PRIMARY KEY,
            treatment_names_json TEXT,
            num_markets INTEGER,
            num_replicates INTEGER,
            seed INTEGER,
            timestamp TEXT,
            status TEXT
        )
    """,
}


def create_tables(conn: sqlite3.Connection) -> None:
    for ddl in TABLES.values():
        conn.execute(ddl)
    conn.commit()


def verify_schema(conn: sqlite3.Connection) -> bool:
    """Return True if all expected tables and columns exist."""
    cursor = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table'"
    )
    actual = {}
    for row in cursor.fetchall():
        name = row[0]
        ddl = row[1]
        if ddl and name in TABLES:
            lines = [ln.strip() for ln in ddl.splitlines() if ln.strip()]
            col_lines = [ln for ln in lines if not ln.startswith("CREATE TABLE") and not ln.startswith(")")]
            cols = set()
            for cl in col_lines:
                cl = cl.rstrip(",")
                cl = cl.split("DEFAULT")[0].strip()
                if " " in cl or "\t" in cl:
                    first_token = cl.split()[0]
                    cols.add(first_token.lower())
            actual[name] = cols

    for name, ddl in TABLES.items():
        if name not in actual:
            return False
        lines = [ln.strip() for ln in ddl.splitlines() if ln.strip()]
        col_lines = [ln for ln in lines if not ln.startswith("CREATE TABLE") and not ln.startswith(")")]
        expected = set()
        for cl in col_lines:
            cl = cl.rstrip(",")
            cl = cl.split("DEFAULT")[0].strip()
            if " " in cl or "\t" in cl:
                first_token = cl.split()[0]
                expected.add(first_token.lower())
        if not expected.issubset(actual[name]):
            return False
    return True
