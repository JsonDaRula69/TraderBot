"""Comparison report generator for methodology scoring results.

Reads scoring JSON files from a results directory and produces a ranked
markdown report comparing all methodologies across Brier score, calibration,
edge realization, P&L, timing analysis, and confidence correlation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Ensure experiments/ is on the path so `python -m results.compare` works
_experiments_root = Path(__file__).resolve().parent.parent
if str(_experiments_root) not in sys.path:
    sys.path.insert(0, str(_experiments_root))


def load_scoring_files(input_dir: Path) -> dict[str, dict[str, Any]]:
    """Discover and load all scoring JSON files from the input directory.

    Returns {methodology_name: scoring_dict}. Files that fail to parse are skipped
    with a warning to stderr.
    """
    results: dict[str, dict[str, Any]] = {}
    for json_path in sorted(input_dir.glob("*.json")):
        try:
            data = json.loads(json_path.read_text())
            methodology = data.get("methodology", json_path.stem)
            results[methodology] = data
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Warning: skipping {json_path.name}: {exc}", file=sys.stderr)
    return results


def fmt_val(value: Any, precision: int = 4) -> str:
    """Format a numeric or None value for markdown table cells."""
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{precision}f}"
    return str(value)


def render_summary_table(results: dict[str, dict[str, Any]]) -> str:
    """Summary table sorted by brier_score (lower is better)."""
    rows: list[tuple[str, float | None, float | None, int, float | None]] = []
    for name, data in results.items():
        brier = data.get("brier_score")
        edge = data.get("edge_realization_rate")
        pnl = data.get("total_pnl_cents", 0)
        conf_corr = data.get("confidence_correlation")
        # Treat missing brier as infinity for sorting
        brier_sort = brier if brier is not None else float("inf")
        rows.append((brier_sort, name, brier, edge, pnl, conf_corr))

    rows.sort(key=lambda r: r[0])

    lines = [
        "## Summary Table",
        "",
        "Methodologies ranked by Brier score (lower = better calibration):",
        "",
        "| Methodology | Brier Score | Edge Realization | Total P&L (cents) | Confidence Correlation |",
        "|-------------|------------:|-----------------:|------------------:|-----------------------:|",
    ]
    for _, name, brier, edge, pnl, conf_corr in rows:
        lines.append(
            f"| {name} | {fmt_val(brier)} | {fmt_val(edge)} "
            f"| {fmt_val(pnl, precision=0)} | {fmt_val(conf_corr)} |"
        )
    return "\n".join(lines)


def calibration_interpretation(slope: float | None) -> str:
    """Human-readable interpretation of calibration slope."""
    if slope is None:
        return "No calibration data"
    if 0.90 <= slope <= 1.10:
        return "Well calibrated"
    if slope < 1.0:
        return "Overconfident (slope < 1)"
    return "Underconfident (slope > 1)"


def render_calibration_section(results: dict[str, dict[str, Any]]) -> str:
    """Calibration comparison table with slope interpretation."""
    lines = [
        "## Calibration Comparison",
        "",
        "Calibration slope near 1.0 indicates well-calibrated probabilities. "
        "Slope < 1 means the methodology is overconfident (predicted probabilities "
        "are too extreme); slope > 1 means underconfident (too conservative).",
        "",
        "| Methodology | Calibration Slope | Interpretation |",
        "|-------------|------------------:|----------------|",
    ]
    for name, data in results.items():
        cal = data.get("calibration", {})
        slope = cal.get("slope") if isinstance(cal, dict) else None
        interp = calibration_interpretation(slope)
        lines.append(
            f"| {name} | {fmt_val(slope)} | {interp} |"
        )
    return "\n".join(lines)


def render_timing_section(results: dict[str, dict[str, Any]]) -> str:
    """Timing analysis: avg P&L per timestep, identifying best entry timestep."""
    # Collect all timesteps across all methodologies
    all_timesteps: set[str] = set()
    for data in results.values():
        timing = data.get("timing_analysis", {})
        all_timesteps.update(timing.keys())

    if not all_timesteps:
        return "## Timing Analysis\n\n*No timing data available.*\n"

    sorted_ts = sorted(all_timesteps, key=int)

    lines = [
        "## Timing Analysis",
        "",
        "Average P&L (cents) per entry timestep. "
        "The **best entry timestep** for each methodology is marked in bold.",
        "",
    ]

    # Header
    header_cells = " | ".join(["Methodology"] + [f"t{ts}" for ts in sorted_ts] + ["Best Entry"])
    sep_cells = " | ".join(["-------------"] + ["---:" for _ in sorted_ts] + ["-----------"])
    lines.append(f"| {header_cells} |")
    lines.append(f"| {sep_cells} |")

    for name, data in results.items():
        timing = data.get("timing_analysis", {})
        if not timing:
            cells = [name] + ["—"] * len(sorted_ts) + ["—"]
        else:
            # Find best timestep (highest avg P&L)
            best_ts = max(timing.items(), key=lambda kv: kv[1]) if timing else (None, float("-inf"))
            best_key = best_ts[0]

            values: list[str] = []
            for ts in sorted_ts:
                val = timing.get(ts)
                if val is None:
                    values.append("—")
                elif ts == best_key:
                    values.append(f"**{fmt_val(val, precision=0)}**")
                else:
                    values.append(fmt_val(val, precision=0))

            cells = [name, *values, f"t{best_key}" if best_key else "—"]

        lines.append(f"| {' | '.join(cells)} |")

    return "\n".join(lines)


def render_edge_realization_section(results: dict[str, dict[str, Any]]) -> str:
    """Bar-style comparison of edge realization rates."""
    lines = [
        "## Edge Realization",
        "",
        "Edge realization rate measures how often a methodology correctly predicts "
        "the outcome when it identifies a positive edge (estimated_prob > market price). "
        "A rate > 0.50 suggests genuine predictive skill.",
        "",
        "| Methodology | Edge Realization Rate | Visual |",
        "|-------------|----------------------:|--------|",
    ]

    # Determine max rate for scaling
    max_rate = 1.0
    for data in results.values():
        rate = data.get("edge_realization_rate")
        if rate is not None and rate > max_rate:
            max_rate = rate

    for name, data in results.items():
        rate = data.get("edge_realization_rate")
        if rate is None:
            bar = "N/A"
        else:
            bar_len = max(1, round((rate / max_rate) * 30)) if max_rate > 0 else 1
            bar = "█" * bar_len + f" ({fmt_val(rate)})"
        lines.append(f"| {name} | {fmt_val(rate)} | {bar} |")

    return "\n".join(lines)


def compute_recommendation(results: dict[str, dict[str, Any]]) -> str:
    """Determine which methodology to recommend for production.

    Scoring: Brier (lower), edge realization (higher), calibration
    (closer to 1.0), P&L (higher), confidence correlation (more negative).
    Each metric contributes equally to a composite rank.
    """
    if not results:
        return "No methodologies have been scored yet. Run the simulation and scoring pipeline first."

    names = list(results.keys())
    n = len(names)

    # Compute ranks for each metric (lower rank = better)
    ranks: dict[str, dict[str, float]] = {name: {} for name in names}

    # Brier score: lower is better
    brier_vals = [(name, results[name].get("brier_score", float("inf"))) for name in names]
    brier_vals.sort(key=lambda x: x[1])
    for rank, (name, _) in enumerate(brier_vals, 1):
        ranks[name]["brier_rank"] = rank

    # Edge realization rate: higher is better (None treated as -inf)
    edge_vals = [(name, results[name].get("edge_realization_rate") or float("-inf")) for name in names]
    edge_vals.sort(key=lambda x: x[1], reverse=True)
    for rank, (name, _) in enumerate(edge_vals, 1):
        ranks[name]["edge_rank"] = rank

    # Calibration slope: closer to 1.0 is better
    cal_vals = [
        (name, abs((results[name].get("calibration", {}).get("slope") or 0) - 1.0))
        if isinstance(results[name].get("calibration"), dict)
        else (name, float("inf"))
        for name in names
    ]
    cal_vals.sort(key=lambda x: x[1])
    for rank, (name, _) in enumerate(cal_vals, 1):
        ranks[name]["cal_rank"] = rank

    # Total P&L: higher is better
    pnl_vals = [(name, results[name].get("total_pnl_cents", -10**9)) for name in names]
    pnl_vals.sort(key=lambda x: x[1], reverse=True)
    for rank, (name, _) in enumerate(pnl_vals, 1):
        ranks[name]["pnl_rank"] = rank

    # Confidence correlation: more negative is better (None treated as worst)
    conf_vals = [(name, results[name].get("confidence_correlation") or 1.0) for name in names]
    conf_vals.sort(key=lambda x: x[1])
    for rank, (name, _) in enumerate(conf_vals, 1):
        ranks[name]["conf_rank"] = rank

    # Composite score: average of all ranks
    composite: list[tuple[float, str]] = []
    for name in names:
        r = ranks[name]
        avg = (r["brier_rank"] + r["edge_rank"] + r["cal_rank"] + r["pnl_rank"] + r["conf_rank"]) / 5
        composite.append((avg, name))
    composite.sort()

    best_name = composite[0][1]

    lines = [
        "## Recommendation",
        "",
    ]

    if n == 1:
        lines.append(
            f"Only one methodology (**{best_name}**) has been scored. "
            "Deploy it and add more methodologies for comparison."
        )
        return "\n".join(lines)

    # Show composite ranking
    lines.append("Composite ranking (average rank across all 5 metrics):")
    lines.append("")
    lines.append("| Rank | Methodology | Composite Score | Brier Rank | Edge Rank | Cal Rank | P&L Rank | Conf Rank |")
    lines.append("|------|-------------|----------------:|-----------:|----------:|---------:|---------:|----------:|")

    for i, (score, name) in enumerate(composite, 1):
        r = ranks[name]
        lines.append(
            f"| {i} | {name} | {score:.1f} "
            f"| {r['brier_rank']:.0f} | {r['edge_rank']:.0f} "
            f"| {r['cal_rank']:.0f} | {r['pnl_rank']:.0f} | {r['conf_rank']:.0f} |"
        )

    lines.append("")
    lines.append(
        f"**Recommended for production deployment: `{best_name}`** — "
        f"it achieved the best composite ranking across all evaluation dimensions."
    )

    return "\n".join(lines)


def render_missing_section(expected: list[str], found: list[str]) -> str:
    """Report on methodologies that have not been scored yet."""
    missing = set(expected) - set(found)
    if not missing:
        return ""

    lines = [
        "## Not Yet Scored",
        "",
        "The following methodologies do not have scoring results yet:",
        "",
    ]
    for m in sorted(missing):
        lines.append(f"- `{m}`")
    lines.append("")
    lines.append("Run the simulation harness and scoring pipeline to populate these results.")
    return "\n".join(lines)


def generate_report(
    results: dict[str, dict[str, Any]],
    expect_methodologies: list[str] | None = None,
) -> str:
    """Generate the full comparison markdown report."""
    sections: list[str] = [
        "# Methodology Comparison Report\n\n",
    ]

    if not results:
        sections.append(
            "*No scoring results found. Run the simulation and scoring pipeline first.*\n"
        )
        return "\n".join(sections)

    sections.append(
        f"*{len(results)} methodology(s) scored*\n"
    )

    sections.append(render_summary_table(results))
    sections.append("")
    sections.append(render_calibration_section(results))
    sections.append("")
    sections.append(render_timing_section(results))
    sections.append("")
    sections.append(render_edge_realization_section(results))
    sections.append("")
    sections.append(compute_recommendation(results))

    if expect_methodologies:
        missing = render_missing_section(expect_methodologies, list(results.keys()))
        if missing:
            sections.append("")
            sections.append(missing)

    # Append raw JSON summaries for reference
    sections.append("")
    sections.append("## Raw Scoring Data")
    sections.append("")
    for name, data in results.items():
        sections.append(f"### {name}")
        sections.append("")
        sections.append("```json")
        sections.append(json.dumps(data, indent=2, default=str))
        sections.append("```")
        sections.append("")

    return "\n".join(sections)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare methodology scoring results and produce a ranked markdown report."
    )
    parser.add_argument(
        "--input-dir", "-i",
        default="experiments/results",
        help="Directory containing scoring JSON files (default: experiments/results)",
    )
    parser.add_argument(
        "--output", "-o",
        default="experiments/results/comparison_report.md",
        help="Output path for the markdown report (default: experiments/results/comparison_report.md)",
    )

    args = parser.parse_args()

    # Resolve paths relative to repo root
    repo_root = Path(__file__).resolve().parent.parent.parent
    input_dir = Path(args.input_dir)
    if not input_dir.is_absolute():
        input_dir = repo_root / input_dir

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = repo_root / output_path

    if not input_dir.exists():
        print(f"Error: input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    # Known methodology names for "not yet scored" section
    expect_these = ["bin_cal", "logistic_reg", "llm_synthesis", "ensemble"]

    results = load_scoring_files(input_dir)

    if not results:
        print(f"Warning: no scoring JSON files found in {input_dir}", file=sys.stderr)

    report = generate_report(results, expect_methodologies=expect_these)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)
    print(f"Comparison report written to {output_path}")


if __name__ == "__main__":
    main()
