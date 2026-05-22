import sqlite3


def compute_city_accuracy(conn: sqlite3.Connection, city: str) -> list[dict]:
    """Join forecasts with settlements, group by lead_time, compute bias/MAE."""
    sql = """
        SELECT f.days_before AS lead_time,
               f.forecast_temp_f,
               s.actual_temp_f
        FROM forecast_snapshots f
        JOIN settlement_results s ON f.ticker = s.ticker
        JOIN markets m ON f.ticker = m.ticker
        WHERE m.city = ?
        ORDER BY f.ticker, f.days_before
    """
    cursor = conn.execute(sql, (city,))
    rows = cursor.fetchall()
    if not rows:
        return []

    groups: dict[int, list[tuple[float, float]]] = {}
    for lead_time, fc, act in rows:
        groups.setdefault(lead_time, []).append((fc, act))

    results = []
    for lead_time, pairs in groups.items():
        errors = [fc - act for fc, act in pairs]
        n = len(errors)
        bias = sum(errors) / n
        mae = sum(abs(e) for e in errors) / n
        results.append({
            "city": city,
            "lead_time": lead_time,
            "bias": bias,
            "mae": mae,
            "sample_count": n,
            "low_confidence": 1 if n < 3 else 0,
        })

    return results


def compute_accuracy(conn: sqlite3.Connection) -> list[dict]:
    """Compute accuracy for all cities in the DB."""
    cursor = conn.execute("SELECT DISTINCT city FROM markets")
    cities = [row[0] for row in cursor.fetchall()]

    all_results = []
    for city in cities:
        all_results.extend(compute_city_accuracy(conn, city))
    return all_results


def save_accuracy(conn: sqlite3.Connection, accuracy_rows: list[dict]) -> None:
    """Insert accuracy rows with upsert semantics (DELETE + INSERT per row)."""
    for row in accuracy_rows:
        conn.execute(
            "DELETE FROM forecast_accuracy WHERE city = ? AND lead_time = ?",
            (row["city"], row["lead_time"]),
        )
        conn.execute(
            "INSERT INTO forecast_accuracy (city, lead_time, mae, bias, sample_count, low_confidence) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (row["city"], row["lead_time"], row["mae"], row["bias"], row["sample_count"], row["low_confidence"]),
        )
