"""Statistical scoring for experiment runs."""

from __future__ import annotations

import logging
import math
import sqlite3
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExperimentResults:
    """Results of a single treatment-vs-control comparison."""

    treatment: str
    control: str
    delta_profit: float
    t_stat: float
    p_value: float
    effect_size: float
    ci_low: float
    ci_high: float
    n_markets: int

    @property
    def improvement(self) -> bool:
        return self.p_value < 0.05 and self.effect_size > 0

    def to_json(self) -> dict[str, Any]:
        return {
            "treatment": self.treatment,
            "control": self.control,
            "delta_profit": round(self.delta_profit, 4),
            "t_stat": round(self.t_stat, 4),
            "p_value": round(self.p_value, 6),
            "effect_size": round(self.effect_size, 4),
            "ci_low": round(self.ci_low, 4),
            "ci_high": round(self.ci_high, 4),
            "n_markets": self.n_markets,
            "improvement": self.improvement,
        }

    def summary(self) -> str:
        sig = "YES" if self.improvement else "NO"
        return (
            f"[{self.treatment} vs {self.control}] "
            f"delta={self.delta_profit:+.2f} "
            f"p={self.p_value:.4f} "
            f"d={self.effect_size:.3f} "
            f"CI=[{self.ci_low:.2f}, {self.ci_high:.2f}] "
            f"n={self.n_markets} "
            f"significant={sig}"
        )


def _pnl_for_decision(
    decision: str,
    yes_price_cents: int,
    no_price_cents: int,
    settlement_result: str | None,
) -> float:
    """Compute P&L in cents for a single decision.

    - buy_yes + settled YES  -> profit = 100 - yes_price
    - buy_yes + settled NO   -> loss   = -yes_price
    - buy_no  + settled NO   -> profit = 100 - no_price
    - buy_no  + settled YES  -> loss   = -no_price
    - skip    -> 0
    """
    if decision == "skip" or settlement_result is None:
        return 0.0

    settled_yes = settlement_result.upper() in ("1", "TRUE", "YES")

    if decision == "buy_yes":
        if settled_yes:
            return float(100 - yes_price_cents)
        return float(-yes_price_cents)

    if decision == "buy_no":
        if not settled_yes:
            return float(100 - no_price_cents)
        return float(-no_price_cents)

    return 0.0


def _paired_ttest(a: list[float], b: list[float]) -> tuple[float, float]:
    """Manual paired t-test returning (t_stat, two_tailed_p_value).

    Used as fallback when scipy is unavailable.
    """
    n = len(a)
    if n < 2:
        return 0.0, 1.0

    diffs = [ai - bi for ai, bi in zip(a, b, strict=True)]
    mean_d = sum(diffs) / n
    var_d = sum((d - mean_d) ** 2 for d in diffs) / (n - 1)
    std_d = math.sqrt(var_d) if var_d > 0 else 0.0

    if std_d == 0:
        return 0.0, 1.0

    t_stat = mean_d / (std_d / math.sqrt(n))

    # Approximate two-tailed p-value from normal distribution for large n,
    # or use the t-distribution approximation for small n.
    # For simplicity, use the regularised incomplete beta function approximation.
    df = n - 1
    x = df / (df + t_stat * t_stat)
    p_value = _incomplete_beta(df / 2.0, 0.5, x)
    return t_stat, p_value


def _incomplete_beta(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta function I_x(a, b) for p-value computation.

    Uses the continued-fraction expansion (Lentz's method).
    """
    if x < 0.0 or x > 1.0:
        return 0.0
    if x == 0.0 or x == 1.0:
        return x

    # Use the symmetry relation I_x(a,b) = 1 - I_{1-x}(b,a) for efficiency
    if x > (a + 1.0) / (a + b + 2.0):
        return 1.0 - _incomplete_beta(b, a, 1.0 - x)

    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(math.log(x) * a + math.log(1.0 - x) * b - lbeta)

    # Continued fraction (Lentz's method)
    f = 1.0
    c = 1.0
    d = 1.0 - (a + 1.0) * x / (a + 1.0)
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    f = d

    for m in range(1, 201):
        # Even step
        numerator = m * (b - m) * x / ((a + 2.0 * m - 1.0) * (a + 2.0 * m))
        d = 1.0 + numerator * d
        if abs(d) < 1e-30:
            d = 1e-30
        d = 1.0 / d
        c = 1.0 + numerator / c
        if abs(c) < 1e-30:
            c = 1e-30
        f *= c * d

        # Odd step
        numerator = -(a + m) * (a + b + m) * x / ((a + 2.0 * m) * (a + 2.0 * m + 1.0))
        d = 1.0 + numerator * d
        if abs(d) < 1e-30:
            d = 1e-30
        d = 1.0 / d
        c = 1.0 + numerator / c
        if abs(c) < 1e-30:
            c = 1e-30
        delta = c * d
        f *= delta

        if abs(delta - 1.0) < 3e-7:
            break

    return front * f


def _normal_quantile(p: float) -> float:
    """Standard normal quantile (inverse CDF) via rational approximation.

    Abramowitz & Stegun 26.2.22. Accurate to ~1e-4, acceptable for
    the Cornish-Fisher t-critical fallback.
    """
    if p <= 0.0:
        return -float("inf")
    if p >= 1.0:
        return float("inf")
    t = math.sqrt(-2.0 * math.log(1.0 - p))
    c = [2.515517, 0.802853, 0.010328]
    d = [1.432788, 0.189269, 0.001308]
    return t - (c[0] + c[1] * t + c[2] * t * t) / (1.0 + d[0] * t + d[1] * t * t + d[2] * t * t * t)


def _t_critical(alpha: float, df: int) -> float:
    """Two-tailed t-distribution critical value for confidence intervals.

    Uses scipy when available, falls back to exact formulas for small df
    (Cauchy at df=1, algebraic for df=2-4) and Cornish-Fisher expansion
    (Gleason 1999) for df >= 5.

    For 95% CI with n=3 (df=2), returns ~4.303 instead of 1.96.
    """
    try:
        from scipy import stats

        return float(stats.t.ppf(1.0 - alpha / 2.0, df))
    except ImportError:
        if df < 1:
            return float("inf")

        p = 1.0 - alpha / 2.0  # upper tail probability

        if df <= 15:
            # Exact 95% two-tailed t critical values for small df
            # (the only alpha this function is called with in practice)
            _small_df_crits = {
                1: 12.7062047362,
                2: 4.3026527299,
                3: 3.1824463053,
                4: 2.7764451052,
                5: 2.5705818356,
                6: 2.4469118488,
                7: 2.3646242516,
                8: 2.3060041350,
                9: 2.2621571628,
                10: 2.2281388514,
                11: 2.2009851601,
                12: 2.1788128297,
                13: 2.1603686565,
                14: 2.1447866879,
                15: 2.1314495456,
            }
            return _small_df_crits.get(df, float("inf"))

        # df >= 16: Cornish-Fisher expansion (Gleason 1999)
        z = _normal_quantile(p)
        z2 = z * z
        z3 = z2 * z
        z5 = z3 * z2
        term1 = (z3 + z) / (4.0 * df)
        term2 = (5.0 * z5 + 16.0 * z3 + 3.0 * z) / (96.0 * df * df)
        return z + term1 + term2


def _cohen_d(diffs: list[float]) -> float:
    """Compute Cohen's d with small-sample correction (Hedges' g)."""
    n = len(diffs)
    if n < 2:
        return 0.0

    mean_d = sum(diffs) / n
    var_d = sum((d - mean_d) ** 2 for d in diffs) / (n - 1)
    std_d = math.sqrt(var_d) if var_d > 0 else 0.0

    if std_d == 0:
        return 0.0

    d = mean_d / std_d

    # Hedges' g small-sample correction
    correction = 1.0 - 3.0 / (4.0 * (n - 1) + 9.0) if n < 50 else 1.0
    return d * correction


def score_run(db_path: str, run_id: str) -> list[ExperimentResults]:
    """Score an experiment run by comparing treatments against control.

    1. Connect to SQLite DB at db_path
    2. Query agent_decisions for the given run_id
    3. Group decisions by (treatment, ticker) and compute P&L per group
    4. Identify control treatment (name="control" or first alphabetically)
    5. For each non-control treatment vs control:
       - Compute delta_profit per market
       - Run paired t-test
       - Compute Cohen's d and 95% CI
    6. Return list of ExperimentResults
    """
    conn = sqlite3.connect(db_path)
    try:
        decisions = conn.execute(
            "SELECT treatment, ticker, timestep, decision FROM agent_decisions WHERE run_id = ?",
            (run_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        logger.warning("Failed to query decisions for run_id=%s", run_id)
        return []
    finally:
        conn.close()

    # Group final decisions by (treatment, ticker)
    # Use the last timestep's decision for each treatment-ticker pair
    final_decisions: dict[tuple[str, str], tuple[str, int]] = {}
    for treatment, ticker, timestep, decision in decisions:
        key = (treatment, ticker)
        if key not in final_decisions or timestep > final_decisions[key][1]:
            final_decisions[key] = (decision, timestep)

    # Collect all treatments
    treatments = sorted({t for t, _ in final_decisions})
    if not treatments:
        return []

    # Identify control
    control_name: str | None = None
    for t in treatments:
        if t == "control":
            control_name = t
            break
    if control_name is None:
        control_name = treatments[0]

    # Get tickers present in control
    control_tickers = {ticker for (t, ticker) in final_decisions if t == control_name}
    if not control_tickers:
        return []

    # Fetch market settlement data and prices
    conn = sqlite3.connect(db_path)
    try:
        settlement_rows = conn.execute(
            "SELECT ticker, settlement_result FROM markets WHERE ticker IN ({})".format(
                ",".join("?" for _ in control_tickers)
            ),
            list(control_tickers),
        ).fetchall()
        settlement_map: dict[str, str | None] = {r[0]: r[1] for r in settlement_rows}

        all_tickers = {ticker for (_, ticker) in final_decisions}
        price_rows = conn.execute(
            "SELECT ticker, yes_price_cents, no_price_cents FROM market_prices "
            "WHERE timestep = 0 AND ticker IN ({})".format(",".join("?" for _ in all_tickers)),
            list(all_tickers),
        ).fetchall()
        price_map: dict[str, tuple[int, int]] = {r[0]: (r[1], r[2]) for r in price_rows}
    except sqlite3.OperationalError:
        logger.warning("Failed to query prices from %s", db_path)
        return []
    finally:
        conn.close()

    # Compute P&L per (treatment, ticker)
    pnl_map: dict[tuple[str, str], float] = {}
    for (treatment, ticker), (decision, _timestep) in final_decisions.items():
        settlement = settlement_map.get(ticker)
        prices = price_map.get(ticker)
        if prices is None:
            # No price data → skip this market
            continue
        yes_cents, no_cents = prices
        pnl = _pnl_for_decision(decision, yes_cents, no_cents, settlement)
        pnl_map[(treatment, ticker)] = pnl

    # Get control P&L vector
    control_pnls: dict[str, float] = {}
    for (t, ticker), pnl in pnl_map.items():
        if t == control_name:
            control_pnls[ticker] = pnl

    # Try scipy, fall back to manual
    try:
        from scipy import stats

        use_scipy = True
    except ImportError:
        use_scipy = False

    results: list[ExperimentResults] = []
    for treatment in treatments:
        if treatment == control_name:
            continue

        # Pair P&Ls by shared tickers
        treatment_pnls: list[float] = []
        ctrl_pnls: list[float] = []
        shared_tickers = set()
        for (t, ticker), pnl in pnl_map.items():
            if t == treatment and ticker in control_pnls:
                treatment_pnls.append(pnl)
                ctrl_pnls.append(control_pnls[ticker])
                shared_tickers.add(ticker)

        n = len(treatment_pnls)
        if n < 2:
            continue

        diffs = [t - c for t, c in zip(treatment_pnls, ctrl_pnls, strict=True)]
        mean_delta = sum(diffs) / n
        std_delta = math.sqrt(sum((d - mean_delta) ** 2 for d in diffs) / (n - 1)) if n > 1 else 0.0

        # Paired t-test
        if use_scipy:
            t_stat, p_value = stats.ttest_rel(treatment_pnls, ctrl_pnls)
        else:
            t_stat, p_value = _paired_ttest(treatment_pnls, ctrl_pnls)

        effect = _cohen_d(diffs)
        # 95% CI uses t-distribution critical value — wider than z=1.96 for small n
        # (e.g. n=3 → t_crit ≈ 4.303). Paired samples with unknown variance.
        t_crit = _t_critical(alpha=0.05, df=n - 1)
        ci = (
            mean_delta - t_crit * std_delta / math.sqrt(n),
            mean_delta + t_crit * std_delta / math.sqrt(n),
        )

        result = ExperimentResults(
            treatment=treatment,
            control=control_name,
            delta_profit=mean_delta,
            t_stat=t_stat,
            p_value=p_value,
            effect_size=effect,
            ci_low=ci[0],
            ci_high=ci[1],
            n_markets=n,
        )
        results.append(result)

        logger.info(
            "Scored %s vs %s: p=%.4f d=%.3f delta=%.2f n=%d improvement=%s",
            treatment,
            control_name,
            p_value,
            effect,
            mean_delta,
            n,
            result.improvement,
        )
        if result.improvement:
            logger.info("Deployment criterion met for %s vs %s", treatment, control_name)
        else:
            logger.info("Deployment criterion rejected for %s vs %s", treatment, control_name)

    return results
