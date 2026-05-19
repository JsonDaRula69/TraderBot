# V3 Experiment Comparative Results

## Runs Completed

| Run | Seed | Parameters | Run ID | Markets | Decisions | Treatments | All Skip |
|-----|------|------------|--------|---------|-----------|------------|----------|
| V2 short | 42 | 1m/1r | v3_control_v2_llm_synthesis_seed42 | ~3 | 19 | control: 9, v2_llm: 10 | Yes |
| V2 long | 2026 | 2m/3r | v3_control_v2_llm_synthesis_seed2026 | ~4 | 13 | control: 6, v2_llm: 7 | Yes |
| Prod short | 100 | 1m/1r | v3_control_seed100 | ~2 | 15 | control only | Yes |
| Prod long | 200 | 2m/3r | v3_control_seed200 | ~2 | 13 | control only | Yes |

## Key Findings

1. **100% skip rate across ALL runs**: Both control and V2_llm_synthesis treatments returned only "skip" decisions.

2. **Estimated probability clamped at 0.500**: Both treatments consistently returned `estimated_prob=0.50` and `confidence=0.10`, which the harness maps to "skip" (edge threshold not met).

3. **Control treatment**: Receives real market prices but `generate_signal()` returns neutral signals (confidence=0.0, edge=0¢) because:
   - Prices are derived from settlement outcomes, not actual historical orderbook data
   - No forecast data in DB (forecasts are empty)
   - Technical indicators are computed from these synthetic prices, producing no momentum

4. **V2 treatment**: Uses the original V2 prompt template but with no forecast data — all weather fields default to "N/A". The LLM can't estimate probability without concrete inputs.

## Root Cause

The experiment infrastructure works (DB, harness, LLM client, scoring all functional). The **data quality** is the blocker:

- **Prices**: Synthesized from settlement — not actual historical Kalshi prices
- **Forecasts**: None in DB — Open-Meteo fetcher not integrated
- **Accuracy**: None in DB — depends on forecasts
- **Technical indicators**: Computed from synthetic prices → no real signal

## Decision Rule

The harness converts `estimated_prob` → decision using:
1. Compute `edge = abs(estimated_prob - implied_prob)`
2. Skip if `edge < EDGE_THRESHOLD` (default 0.05) or confidence < CONFIDENCE_THRESHOLD
3. buy_yes if `estimated_prob > implied_prob`, else buy_no

Since both control and V2_llm_synthesis return `prob=0.50` and `confidence=0.10`, edge ≈ 0.02-0.03 < 0.05 threshold → **always skip**.

## Recommendations

1. **Fix price data**: Fetch real historical Kalshi trade prices via `/markets/{ticker}/trades` endpoint
2. **Fetch forecasts**: Run Open-Meteo previous-runs API for actual forecast error distributions
3. **Test with non-neutral data**: Mock a market where `estimated_prob=0.7` and `implied_prob=0.4` to verify buy_yes/buy_no paths work

## Files

- `experiments/results/comparison_report.json` — Full decision-level data
- `experiments/results/v2_short.log` — V2 short run logs
- `experiments/results/v2_long.log` — V2 long run logs
- `experiments/results/prod_short.log` — Production short logs
- `experiments/results/prod_long.log` — Production long logs
