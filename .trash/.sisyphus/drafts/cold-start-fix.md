# Draft: Cold-Start Fix Implementation

## Requirements (confirmed)
- Implement solutions to the cold-start problem described in cold_start_fix.md
- No unit tests (agent-executed QA only)
- The OpenClaw agent is DEV-ONLY and will be deleted once investigation is complete
- Each Kalshi category needs its own analysis model, data sources, and operating procedure

## Architecture: Division of Responsibility

### TraderBot = Toolkit (Enforcement Layer)
- Data fetching, risk pipeline, trade execution, audit logging
- `traderbot trade --estimated-prob X --confidence Y` — agent provides probability
- `traderbot signals` — FALLBACK reference tool, uses market-implied prob
- `generate_signal()` is NOT the primary decision path
- `AnalysisRegistry` already supports category-specific analyzers (register pattern)
- Risk pipeline: `evaluate_trade_full()` enforces guardrails regardless of prob source

### OpenClaw Agent = Decision-Maker (Strategy Layer)
- Currently provides `--estimated-prob` and `--confidence` as heuristic guesses
- Each category (weather, elections, economics) needs different analysis
- Agent will be deleted — the pattern must survive in TraderBot CLI tools

### Key Insight: The Cold-Start Problem is Really About Data Infrastructure
The agent CAN provide estimated_prob already (5 trades executed with edge 0.08-0.66).
The problem is:
1. The agent has no calibrated data to inform its probability estimates
2. Trade decisions aren't being stored for learning (ChromaDB decisions = 0 entries)
3. There's no feedback loop from settlement outcomes back to probability calibration

## Architecture Decisions (CRITICAL — Based on Category-Specific Design)

### cold_start_fix.md's Approach is WRONG for Phase 1
The doc proposes a hardcoded `weather_prob.py` inside `analysis/`. This is wrong because:
- Weather analysis ≠ election analysis ≠ crypto analysis
- `generate_signal()` is a fallback, not the primary path
- The pattern should be: TraderBot provides calibration DATA, not domain-specific MODELS

### Correct Architecture
| What | Where | Why |
|------|-------|-----|
| Calibration CLI | `traderbot calibrate --category weather` | Fetches settled markets, computes accuracy bins, stores in ChromaDB |
| Probability estimation CLI | `traderbot prob-estimate --ticker X` | Uses calibration data + current data to return estimated_prob |
| Category-specific analysis | `AnalysisRegistry` with registered `CategoryAnalyzer` | Already exists! `register()` method ready |
| Decision storage (Phase 4) | `src/traderbot/db/decisions.py` | Audit → ChromaDB write is toolkit-level |
| Bayesian update (Phase 3) | `AdapterStateStore` + `BayesianAdapter` | Already complete — needs wiring only |
| Backtest framework (Phase 2) | `BacktestEngine` + strategy classes | Already complete — needs `WeatherStrategy` only |
| Category analyzers | `analysis/registry.py` pattern | `CategoryAnalyzer` subclasses per category |

### The AnalysisRegistry Pattern
The codebase ALREADY HAS the category-specific pattern:
```python
class AnalysisRegistry:
    def register(self, category: MarketCategory, analyzer: CategoryAnalyzer) -> None:
        self._analyzers[category] = analyzer

    def get(self, category: MarketCategory) -> CategoryAnalyzer:
        if category in self._analyzers:
            return self._analyzers[category]
        return self._default  # GenericAnalyzer (fallback)
```

Each category can have its own `CategoryAnalyzer.analyze()` method that:
- Knows which data sources to consult
- Has category-specific calibration data
- Returns `CategorySignals` with confidence

## Revised Phase Architecture

### Phase 1: Category-Aware Probability Estimation (NOT just "weather_prob")
- `AnalysisRegistry` registration for weather category with `WeatherAnalyzer`
- `WeatherAnalyzer.analyze()` queries ChromaDB for historical accuracy bins
- New CLI: `traderbot calibrate --category weather` to populate bins
- New CLI: `traderbot prob-estimate --ticker X` as agent reference tool
- `traderbot signals --category weather` uses `WeatherAnalyzer` instead of `GenericAnalyzer`

### Phase 2: Backtest Framework (unchanged from doc)
- `WeatherStrategy` extends existing `Strategy` base class
- `traderbot backtest --strategy weather --category weather` command wiring
- `BacktestEngine` already complete — just needs category strategy implementations

### Phase 3: Bayesian Learning Loop (unchanged from doc)
- Wire `BayesianAdapter.update()` into settlement reconciliation
- Decisions → ChromaDB → Bayesian update → calibration data refresh
- Trigger: `traderbot calibrate --update` or heartbeat integration

### Phase 4: Decision Storage Pipeline (unchanged from doc)
- `src/traderbot/db/decisions.py` (new file)
- Write all `evaluate_trade_full()` results to ChromaDB `decisions` collection
- `get_pending_decisions()` and `update_decision()` for settlement reconciliation

## Remote Environment State (macpro-linux as of 2026-05-18)
- TraderBot v0.12.03 (dev branch)
- ChromaDB: news(1566), news_signals(54), data_points(7484), decisions(0), market_conditions(0), market_patterns(0)
- 82 trade evaluations in audit/2026-05-18.jsonl: 5 executed, 77 rejected (all edge=0)
- `estimated_prob` field is NULL in audit entries — agent provides edge_estimate directly
- 2 profiles: weather2 (paper, rm 1.00), weatherman (paper, rm 1.00)
- OpenClaw agents: weather, weatherman2 (both dev-only, will be deleted)

## Scope Boundaries
- INCLUDE: All 4 phases, but redesigned for category-specific architecture
- INCLUDE: `AnalysisRegistry`-based category analyzers (not hardcoded weather model)
- INCLUDE: CLI tools for calibration and prob-estimate
- INCLUDE: Decision storage to ChromaDB
- EXCLUDE: Modifying `generate_signal()` to hardcode a weather model
- EXCLUDE: Agent workspace changes (agent is temporary)
- EXCLUDE: Unit tests
