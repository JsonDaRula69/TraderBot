"""Paired t-tests, Cohen's d, confidence intervals, and treatment comparison."""

from __future__ import annotations

import numpy as np
from scipy import stats


def paired_t_test(treatment_pnl: list[float], control_pnl: list[float]) -> dict:
    """Paired t-test on per-market delta profit."""
    result = stats.ttest_rel(treatment_pnl, control_pnl)
    return {
        "t_statistic": float(result.statistic),
        "p_value": float(result.pvalue),
        "mean_delta": float(np.mean(np.array(treatment_pnl) - np.array(control_pnl))),
        "n": len(treatment_pnl),
    }


def cohens_d(treatment_pnl: list[float], control_pnl: list[float]) -> float:
    """Cohen's d effect size for paired samples."""
    diffs = np.array(treatment_pnl) - np.array(control_pnl)
    mean_diff = np.mean(diffs)
    sd_diff = np.std(diffs, ddof=1) if len(diffs) > 1 else 1.0
    return float(mean_diff / sd_diff) if sd_diff > 0 else 0.0


def confidence_interval(deltas: list[float], confidence: float = 0.95) -> dict:
    """Confidence interval for mean delta profit."""
    if len(deltas) < 2:
        return {"lower": 0.0, "upper": 0.0, "mean": 0.0, "n": 0}
    mean = np.mean(deltas)
    sem = stats.sem(deltas)
    ci = stats.t.interval(confidence, df=len(deltas) - 1, loc=mean, scale=sem)
    return {
        "lower": float(ci[0]),
        "upper": float(ci[1]),
        "mean": float(mean),
        "n": len(deltas),
    }


def compare_treatments(
    treatment_pnl: dict[str, list[float]],
    metrics: dict[str, dict[str, list[float]]],
) -> dict:
    """Full comparison: each treatment vs control."""
    control = treatment_pnl.get("control", [])
    if not control:
        return {"error": "No control data"}

    results: dict = {"control_mean_pnl": float(np.mean(control))}

    for name, pnl in treatment_pnl.items():
        if name == "control":
            continue
        results[name] = {
            "mean_pnl": float(np.mean(pnl)),
            **paired_t_test(pnl, control),
            "cohens_d": cohens_d(pnl, control),
            "ci_95": confidence_interval(list(np.array(pnl) - np.array(control))),
        }
        if name in metrics and "control" in metrics:
            for metric_name in metrics[name]:
                if metric_name in metrics.get("control", {}):
                    results[name][f"{metric_name}_ttest"] = paired_t_test(
                        metrics[name][metric_name],
                        metrics["control"][metric_name],
                    )

    return results
