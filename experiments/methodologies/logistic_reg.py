"""Logistic Regression methodology for weather market probability estimation."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .base import MethodologyInterface, MethodologyResult
from .db_utils import get_market
from .ticker_parser import parse_weather_ticker

try:
    from sklearn.linear_model import LogisticRegression as SklearnLogisticRegression

    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False

# Feature column names — must be identical for training and prediction
_FEATURE_COLUMNS = [
    "forecast_delta",
    "forecast_delta_squared",
    "timestep",
    "month",
    "forecast_spread",
    "humidity",
    "wind_speed",
    "precip",
]


def _sigmoid(z: np.ndarray) -> np.ndarray:
    """Numerically stable sigmoid function."""
    return np.where(
        z >= 0,
        1.0 / (1.0 + np.exp(-z)),
        np.exp(z) / (1.0 + np.exp(z)),
    )


class _SimpleLogisticRegression:
    """Minimal logistic regression via gradient descent (fallback when sklearn unavailable)."""

    def __init__(self, lr: float = 0.1, n_iter: int = 200):
        self.lr = lr
        self.n_iter = n_iter
        self.coef_: np.ndarray | None = None
        self.intercept_: float | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> _SimpleLogisticRegression:
        n_samples, n_features = X.shape
        self.coef_ = np.zeros(n_features)
        self.intercept_ = 0.0
        for _ in range(self.n_iter):
            z = X @ self.coef_ + self.intercept_
            pred = _sigmoid(z)
            error = pred - y
            self.coef_ -= self.lr * (X.T @ error) / n_samples
            self.intercept_ -= self.lr * error.mean()
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        z = X @ self.coef_ + self.intercept_
        p1 = _sigmoid(z)
        p0 = 1.0 - p1
        return np.column_stack([p0, p1])


class LogisticRegMethodology(MethodologyInterface):
    """Estimate event probability using logistic regression on forecast features."""

    def __init__(self, db_path: Path):
        super().__init__(db_path)
        self._model = None

    def estimate(
        self,
        ticker: str,
        forecast: dict,
        timestep: int,
        prior_decisions: list,
    ) -> MethodologyResult:
        try:
            parsed = parse_weather_ticker(ticker)
        except ValueError as exc:
            return MethodologyResult(
                estimated_prob=0.5,
                confidence=0.1,
                reasoning={"error": f"Invalid ticker: {exc}"},
            )

        market = get_market(self.conn, ticker)

        if market is None:
            return MethodologyResult(
                estimated_prob=0.5,
                confidence=0.1,
                reasoning={"error": f"Market not found for ticker {ticker}"},
            )

        direction = parsed["direction"]
        strike_value = market["strike_value"]

        # --- Feature engineering for prediction ---
        temp_max = forecast.get("temp_max_f", 0.0) or 0.0
        if direction == "above":
            forecast_delta = temp_max - strike_value
        else:
            forecast_delta = strike_value - temp_max

        forecast_spread = temp_max - (forecast.get("temp_min_f", 0.0) or 0.0)
        humidity = forecast.get("humidity_max_pct", 0.0) or 0.0
        wind_speed = forecast.get("wind_speed_max_kmh", 0.0) or 0.0
        precip = forecast.get("precip_mm", 0.0) or 0.0

        # Month from forecast_date or resolution_date
        date_str = forecast.get("forecast_date") or market.get("resolution_date") or ""
        month = int(date_str[5:7]) if len(date_str) >= 7 and date_str[5:7].isdigit() else 1

        prediction_features = np.array(
            [[
                forecast_delta,
                forecast_delta ** 2,
                float(timestep),
                float(month),
                forecast_spread,
                humidity,
                wind_speed,
                precip,
            ]]
        )

        # --- Training data ---
        training_rows = self._fetch_training_data()
        if len(training_rows) < 20:
            return MethodologyResult(
                estimated_prob=0.5,
                confidence=0.1,
                reasoning={"reason": "insufficient_data", "training_samples": len(training_rows)},
            )

        X_train, y_train = self._build_training_matrix(training_rows)

        # --- Fit model ---
        if _HAS_SKLEARN:
            model = SklearnLogisticRegression(max_iter=500, solver="lbfgs")
            model.fit(X_train, y_train)
            proba = model.predict_proba(prediction_features)[0]
            coef_arr = model.coef_[0].tolist()
            intercept = float(model.intercept_[0])
        else:
            model = _SimpleLogisticRegression(lr=0.1, n_iter=200)
            model.fit(X_train, y_train)
            proba = model.predict_proba(prediction_features)[0]
            coef_arr = model.coef_.tolist()
            intercept = float(model.intercept_)

        # proba[1] = P(class=1) = P(market resolves YES)
        # For "above": YES = temp > threshold, so proba[1] is P(above)
        # For "below": YES = temp < threshold, so proba[1] is P(below)
        # In both cases, proba[1] gives the probability the market resolves YES
        prob = float(proba[1])
        confidence = float(abs(proba[1] - proba[0]))
        confidence = max(confidence, 0.1)

        feature_values = dict(zip(_FEATURE_COLUMNS, prediction_features[0].tolist(), strict=True))

        return MethodologyResult(
            estimated_prob=prob,
            confidence=confidence,
            reasoning={
                "methodology": "logistic_regression",
                "direction": direction,
                "strike_value": strike_value,
                "coefficients": dict(zip(_FEATURE_COLUMNS, coef_arr, strict=True)),
                "intercept": intercept,
                "feature_values": feature_values,
                "training_samples": len(training_rows),
                "sklearn_available": _HAS_SKLEARN,
            },
        )

    def _fetch_training_data(self) -> list[dict]:
        """Fetch settled markets with forecast features for training."""
        query = """
            SELECT
                m.ticker,
                m.strike_value,
                m.strike_type,
                m.settlement_result,
                m.resolution_date,
                fs.temp_max_f,
                fs.temp_min_f,
                fs.humidity_max_pct,
                fs.wind_speed_max_kmh,
                fs.precip_mm,
                fs.timestep,
                fs.forecast_date,
                sa.actual_temp_max_f
            FROM markets m
            JOIN forecast_snapshots fs ON m.ticker = fs.ticker
            JOIN settlement_actuals sa ON m.ticker = sa.ticker
            WHERE m.settlement_result IS NOT NULL
              AND fs.timestep = 10
        """
        cursor = self.conn.execute(query)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    def _build_training_matrix(
        self, rows: list[dict]
    ) -> tuple[np.ndarray, np.ndarray]:
        """Convert training rows into (X, y) arrays matching prediction features."""
        X_list: list[list[float]] = []
        y_list: list[int] = []

        for row in rows:
            strike_value = row["strike_value"]
            direction = "above" if row["ticker"].startswith("KXHIGH") else "below"

            temp_max = row["temp_max_f"] or 0.0
            delta = temp_max - strike_value if direction == "above" else strike_value - temp_max

            spread = temp_max - (row["temp_min_f"] or 0.0)
            humidity = row["humidity_max_pct"] or 0.0
            wind_speed = row["wind_speed_max_kmh"] or 0.0
            precip = row["precip_mm"] or 0.0
            timestep = row["timestep"] or 10

            date_str = row.get("forecast_date") or row.get("resolution_date") or ""
            month = int(date_str[5:7]) if len(date_str) >= 7 and date_str[5:7].isdigit() else 1

            X_list.append([
                delta,
                delta ** 2,
                float(timestep),
                float(month),
                spread,
                humidity,
                wind_speed,
                precip,
            ])
            y_list.append(1 if row["settlement_result"] == "yes" else 0)

        return np.array(X_list, dtype=float), np.array(y_list, dtype=float)
