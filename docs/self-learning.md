# Self-Learning & Experiment Pipeline

How TraderBot improves over time — Bayesian parameter updating, learning logs, structured experiments, and the WAL protocol for crash-safe execution.

## Design Philosophy

The agent improves through **math, not emotions**. When outcomes differ from predictions, we update the mathematical model. We don't "feel more confident" or "learn a lesson" — we adjust a probability distribution based on evidence.

This is the critical distinction from human traders who tilt, chase losses, or develop superstitions. The adaptation engine only changes parameters based on statistical evidence.

## Experiment Pipeline

New trading strategies and decision improvements go through a structured experiment pipeline before deployment. This prevents unvalidated changes from reaching production.

```
DISCOVER → PROMOTE → DESIGN → VALIDATE → EVALUATE → DEPLOY/REJECT
```

### Stage 1: DISCOVER

Pattern identified in `.learnings/LEARNINGS.md` during heartbeat review or manual observation. Patterns are logged with a unique key and recurrence count.

```markdown
## Entry: EDGE-001
**Pattern-Key**: illiquid-market-slippage
**Recurrence-Count**: 4
**Priority**: high
**Status**: active
```

### Stage 2: PROMOTE

When `Recurrence-Count >= 3` across 2+ tasks within 30 days, the pattern becomes eligible for promotion:

```bash
traderbot learnings --promote KEY
```

This transitions the learning to `PENDING_REVIEW` status. Promotion is notification-only — the agent NEVER auto-edits `AGENTS.md`. Human approval is required before any operating rule change.

**Staleness constraint**: Patterns with `max_age_days > 30` are automatically excluded from promotion, enforced in `db/learnings.py`.

### Stage 3: DESIGN

When a PENDING_REVIEW learning is approved for testing, an agent spawns a sub-agent via `sessions_spawn → sessions_yield` to implement the improvement as a `TreatmentInterface` subclass. The design is recorded in `SESSION-STATE.md`.

### Stage 4: VALIDATE

Populate the experiment database with market data:

```bash
traderbot experiment populate --category KXHIGH --max-markets N
```

This fetches market data from Kalshi and forecast data from Open-Meteo, storing them in the experiment SQLite database. Verify coverage:

```bash
traderbot experiment verify
```

Returns JSON with market count, forecast coverage, price coverage, and settled market count.

### Stage 5: EVALUATE

Run the within-subjects experiment:

```bash
traderbot experiment run --treatments control,variant --replicates N --model <model>
```

The Harness executes each treatment on the same set of markets (within-subjects design), records agent decisions per `(treatment, market, timestep)` cell, then automatically scores results via `score_run()`.

CLI exit codes: `0` = no significant improvement, `2` = significant improvement detected, `1` = failure.

### Stage 6: DEPLOY / REJECT

```bash
traderbot experiment results <run-id>
```

Scores each treatment vs. control using paired t-test and Cohen's d. Deployment criteria: **p < 0.05 AND positive effect size** → deploy. Otherwise, reject.

## TreatmentInterface

All treatments implement `TreatmentInterface` (from `experiment/shared.py`):

```python
class TreatmentInterface(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique treatment identifier."""
        ...

    @property
    def bypass_llm(self) -> bool:
        """If True, the harness skips LLM calls for this treatment."""
        return False

    @abstractmethod
    def format_prompt(self, ctx: TreatmentContext) -> str:
        """Format the prompt sent to the LLM for this treatment."""
        ...

    @abstractmethod
    def validate_response(self, response: dict) -> ValidatedDecision:
        """Parse and validate the LLM's response into a decision."""
        ...
```

### Treatment Context

Each treatment receives a `TreatmentContext` dataclass with:

| Field | Type | Description |
|---|---|---|
| `market` | `MarketData` | Ticker, strike type, threshold, expiration, category |
| `forecast` | `ForecastData` | Forecast temperature, source, days before expiry |
| `accuracy` | `AccuracyData` | Brier score, calibration error, sample size |
| `prices` | `PriceData` | Current YES/NO prices, price history, spread |
| `technical` | `TechnicalData` | RSI, Bollinger Bands, EMA (short & long) |
| `prior` | `PriorDecisions` | Previous decisions for this market |
| `system_context` | `str` | Optional system-level context |

### ValidatedDecision

Treatments must return a `ValidatedDecision`:

```python
@dataclass(frozen=True)
class ValidatedDecision:
    decision: Literal["buy_yes", "buy_no", "skip"]
    estimated_prob: float   # 0.0–1.0
    confidence: float       # 0.0–1.0
    reasoning: str
```

### Built-in Treatments

| Treatment | `bypass_llm` | Description |
|---|---|---|
| `ControlTreatment` | True | Uses market-implied probability — no LLM call. Baseline for comparison. |
| `CalibrationBundleTreatment` | False | Full-context prompt with forecast data, accuracy metrics, technical indicators, and prior decisions. |

New treatments are registered in `experiment/treatments/__init__.py` via `TREATMENT_REGISTRY`.

## Harness

The `Harness` class (`experiment/harness.py`) executes **within-subjects experiments**: every treatment runs on the same set of markets, so differences are attributable to the treatment, not market selection bias.

### Market Stratification

Markets are stratified by city prefix × time-to-expiry bucket using `select_markets()` from `experiment/methodologies/db_utils.py`:

| Bucket | Condition |
|---|---|
| `lt7d` | Resolution date < 7 days away |
| `7-14d` | Resolution 7–14 days away |
| `gt14d` | Resolution > 14 days away |

Each cell gets `markets_per_cell` (default 2) randomly selected markets, controlled by `--seed`.

### Execution Flow

```
Harness.run(treatments, run_id, replicates=3, markets_per_cell=2)
│
├── select_markets(conn, markets_per_cell, seed) → stratified cells
│
├── For each replicate (1..replicates):
│   └── For each ticker in selected markets:
│       └── _run_ticker(treatments, run_id, ticker)
│           ├── Load market data from DB
│           ├── Load forecasts, price history, prior decisions
│           ├── Build TreatmentContext
│           └── For each treatment:
│               ├── if bypass_llm: _control_decision()
│               │   └── Uses market-implied probability (yes_price/100)
│               └── else: LLM call with treatment.format_prompt(ctx)
│                   └── treatment.validate_response(llm_response)
│                   └── _record_decision() → agent_decisions table
```

### Control Decision Logic

The bypass-LLM control derives decisions from market-implied probability:

```python
estimated_prob = current_yes_cents / 100.0
if estimated_prob > 0.55:  decision = "buy_yes"
elif estimated_prob < 0.45: decision = "buy_no"
else:                       decision = "skip"
confidence = min(1.0, abs(estimated_prob - 0.5) * 2)
```

## Results & Statistical Scoring

The `ExperimentResults` dataclass and `score_run()` function (`experiment/results.py`) evaluate whether a treatment outperforms control.

### ExperimentResults

```python
@dataclass
class ExperimentResults:
    treatment: str        # Treatment name
    control: str          # Control name
    delta_profit: float   # Mean P&L difference (cents)
    t_stat: float         # Paired t-statistic
    p_value: float        # Two-tailed p-value
    effect_size: float    # Cohen's d (Hedges' g for small samples)
    ci_low: float         # 95% CI lower bound
    ci_high: float        # 95% CI upper bound
    n_markets: int        # Number of paired markets

    @property
    def improvement(self) -> bool:
        return self.p_value < 0.05 and self.effect_size > 0
```

### Scoring Methodology

1. For each run, collect final decisions per `(treatment, ticker)` pair (last timestep)
2. Compute P&L per decision based on settlement results and market prices
3. Pair treatment P&L against control P&L by shared tickers
4. Run **paired t-test** (scipy if available, manual incomplete-beta fallback)
5. Compute **Cohen's d** with Hedges' g small-sample correction
6. Compute **95% CI** as `mean_delta ± 1.96 × SE`
7. **Deployment criterion**: `p < 0.05 AND effect_size > 0`

### P&L Computation

| Decision | Settled YES | Settled NO |
|---|---|---|
| `buy_yes` | Profit = 100 − yes_price | Loss = −yes_price |
| `buy_no` | Loss = −no_price | Profit = 100 − no_price |
| `skip` | 0 | 0 |

## Experiment CLI

```bash
# Populate experiment database with market data
traderbot experiment populate --category KXHIGH --max-markets 200

# Verify data coverage
traderbot experiment verify

# Run experiment (dry-run to validate without LLM calls)
traderbot experiment run --treatments control,calibration_bundle --replicates 3 --model glm-5.1:cloud --dry-run

# Run experiment (live)
traderbot experiment run --treatments control,calibration_bundle --replicates 3 --model glm-5.1:cloud

# Score results from a completed run
traderbot experiment results <run-id>

# List available treatments
traderbot experiment list-treatments
```

CLI exit codes: `0` = success/no improvement, `1` = failure, `2` = statistically significant improvement detected.

## WAL Protocol (Write-Ahead Log)

The `wal.py` module implements a crash-safe write-ahead log for trade execution. Every trade intent is written to `SESSION-STATE.md` **before** execution, enabling recovery from crashes.

### WalStatus Transitions

```
write_intent() → PENDING
                    │
        ┌───────────┼───────────┐
        │           │           │
   EXECUTED     REJECTED    CANCELLED
   (order       (risk check  (cancelled
    placed)      failed)      pre-exec)
        │
    COMPLETED
   (position
    confirmed)
        │
     EXPIRED
   (timed out)
```

| Status | Meaning |
|---|---|
| `PENDING` | Intent written, awaiting execution |
| `EXECUTED` | Order placed on exchange (awaiting fill confirmation) |
| `COMPLETED` | Position confirmed on exchange |
| `REJECTED` | Risk check or exchange rejected the intent |
| `CANCELLED` | Intent cancelled before execution |
| `EXPIRED` | Intent timed out before execution |

### WalEntry Structure

Entries are stored as markdown in `SESSION-STATE.md` under the `## Pending Actions` section:

```markdown
### WAL-A1B2C3D4
- Timestamp: 2026-05-27T14:30:00+00:00
- Action: BUY YES 10 KXHIGHTMIN-25M26 @ 65¢
- Reason: High confidence weather signal
- Signal: forecast_accuracy
- Risk: passed
- Confidence: 0.85
- Status: PENDING
```

### Core WAL Operations

| Operation | Function | Description |
|---|---|---|
| Write intent | `write_intent(path, ...)` | Creates PENDING entry with exclusive file lock. Raises `ConcurrentWriteError` if another writer holds the lock. |
| Update status | `update_status(path, intent_id, status)` | Transitions entry status by rewriting the `Status:` line. Uses exclusive lock. |
| Scan pending | `scan_pending(path)` | Returns all PENDING entries from SESSION-STATE.md for crash recovery. |
| Reconcile | `reconcile(path, positions)` | Matches PENDING intents against actual positions → marks COMPLETED or CANCELLED. |

### File Locking

The WAL uses `portalocker` for POSIX file locking:
- **Exclusive lock** (`LOCK_EXCLUSIVE | LOCK_NON_BLOCKING`): Acquired during `write_intent()` and `update_status()`. Prevents concurrent writes.
- **Shared lock** (`LOCK_SHARED`): Acquired during `scan_pending()` reads.
- If an exclusive lock cannot be obtained, `ConcurrentWriteError` is raised immediately (non-blocking).
- New files are created with `set_file_owner_only()` for security.

### Crash Recovery

On startup after a crash:

1. Call `scan_pending(SESSION_STATE_PATH)` to find all PENDING entries
2. Fetch actual positions from Kalshi API
3. Call `reconcile(SESSION_STATE_PATH, positions)`:
   - For each PENDING entry, if the position exists and matches → mark `COMPLETED`
   - If the position doesn't match → mark `CANCELLED`
4. Resume normal operations

## Bayesian Parameter Adaptation

`simulation/adaptation.py` — the math layer that adjusts strategy parameters.

### How It Works

Strategy parameters are modeled as probability distributions (priors), not fixed values. As the agent observes outcomes, it updates these distributions using Bayes' theorem:

```
posterior ∝ prior × likelihood

where:
  prior      = current belief about the parameter
  likelihood = how likely the observed outcome is under different parameter values
  posterior   = updated belief
```

### Adapted Parameters

| Parameter | Prior Distribution | What It Controls |
|---|---|---|
| **Edge threshold** | Beta(2, 8) → starts at ~0.20 | Minimum edge required to enter a trade |
| **Signal weight: statistical** | Dirichlet(1,1,1) | How much weight to give statistical indicators |
| **Signal weight: sentiment** | Dirichlet(1,1,1) | How much weight to give sentiment signals |
| **Mean reversion strength** | Normal(0.5, 0.2) | How aggressively to fade price moves |
| **Momentum decay rate** | Exponential(1.0) | How quickly momentum signals decay |

### Update Cycle

The adaptation engine runs during the Heartbeat Loop (every 30 minutes):

1. Collect all decisions made since last heartbeat
2. For closed markets: compare predicted outcome vs. actual
3. Compute likelihood of observed outcomes under current priors
4. Update posterior distributions via conjugate prior updates (fast, no MCMC needed)
5. Write updated parameters to `SESSION-STATE.md`
6. Log what changed and why

### Guardrails on Adaptation

| Guard | Rule | Why |
|---|---|---|
| **Parameter bounds** | No parameter can move more than 20% in a single update | Prevents wild swings from small sample sizes |
| **Minimum sample** | At least 10 observations before any update | Statistical validity |
| **Cooldown** | No more than 4 updates per 24 hours | Prevents over-fitting to recent data |
| **Reset trigger** | If posterior variance < 0.01, reset to weak prior | Prevents convergence to false certainty |
| **Human review** | If any parameter moves >10% for 3 consecutive updates, flag for human review | Detects systematic drift |

## Learning Logs

Inspired by `peterskoett/self-improving-agent`. Structured markdown files that capture what the agent learns from experience.

### File Structure

```
.learnings/
├── LEARNINGS.md            # Corrections, insights, better approaches
├── ERRORS.md               # API errors, failed orders, unexpected states
└── FEATURE_REQUESTS.md     # Capabilities the agent discovers it needs
```

### Learning Entry Format

```markdown
## Entry: EDGE-001
**Logged**: 2026-05-27T14:30:00Z
**Pattern-Key**: illiquid-market-slippage
**Recurrence-Count**: 4
**Priority**: high
**Status**: active
**Category**: risk
### Learning
Markets with open_interest < 500 experience significant slippage on orders > 5 contracts.
### Action
Added liquidity threshold to risk/limits.py. Pending verification in next heartbeat.
```

### Pattern Promotion

When a learning recurs enough, it gets promoted to permanent project memory:

**Promotion criteria**:
- `Recurrence-Count >= 3`
- Seen across at least 2 distinct tasks
- Occurred within a 30-day window (`max_age_days=30`)
- Pattern is not stale (patterns older than 30 days from last recurrence are NOT eligible)

**Promotion targets**:
- `AGENTS.md` — flagged for human review via PENDING_REVIEW status (never auto-committed)
- `SESSION-STATE.md` — active context for the current session
- Code changes — if the learning identifies a bug or improvement

**Promotion is notification-only**: The agent NEVER auto-edits `AGENTS.md`. Pattern promotion creates a `PENDING_REVIEW` entry in `FEATURE_REQUESTS.md` that surfaces during heartbeat review. Human approval is required before any operating rule change.

## Semantic Decision Search

Store decision embeddings in ChromaDB for natural language retrieval. Instead of filtering decisions by date or ticker with SQL, agents query with questions like "what happened last time the Fed raised rates?"

### Design

- **Embedding model**: `voyage-4-large` (general-purpose, 1024 dimensions default)
- **Scope**: Last 90 days, max 1000 results per query
- **Embed on write**: Decisions are embedded when logged, not on read
- **Storage hierarchy**: ChromaDB stores embedding + `decision_id` (foreign key to SQLite); SQLite is authoritative; ChromaDB is the search index only

### Query Flow

1. Agent asks: "what happened to energy markets when the Fed raised rates?"
2. Query embedding generated with `voyage-4-large`
3. ChromaDB returns semantically similar decision IDs ranked by cosine similarity
4. Agent retrieves full decision records from SQLite via `decision_id`
5. Agent reviews historical decisions, forms hypothesis, decides action

## Fleet Improvement Pipeline

The self-learning pipeline doesn't stop at the agent level — it feeds into a fleet-wide improvement cycle that involves sysadmin cron jobs, GitHub issues, CI validation, and deployment.

### Architecture Overview

```
Agent (category)                Sysadmin                        GitHub / CI
─────────────────              ─────────                       ────────────

1. DISCOVER pattern
   → .learnings/LEARNINGS.md
   ─────────────────────────► 2. PROMOTE (Recurrence >= 3)
                                  → PENDING_REVIEW status
                             3. DESIGN experiment
                                  → test-lab/backlog.md
                                  → QUEUED status
                             4. EXECUTE (every 6h cron)
                                  → traderbot backtest + compare
                                  → RUNNING → VALIDATED or REJECTED
                             5. EVALUATE against deployment bar:
                                  Sharpe >= 1.0, win rate >= +5pp,
                                  sample size >= 30
                                      │
                        ┌─────────────┴─────────────┐
                        ▼                           ▼
              Code change needed?          Profile param change?
                        │                           │
                        ▼                           ▼
                  6. FILE GITHUB ISSUE       6. DEPLOY via
                     via 🐙 github skill       traderbot profile update
                     with reproduction         → archive in results/
                     steps + labels            → notify agent
                        │
                        ▼
                  7. CI validates (PR)
                     → lint → unit → matrix → build
                     → merge on pass
```

### Cron Job Triggers

Three sysadmin cron jobs instruct agents to file GitHub issues:

| Cron Job | Schedule | Source | Label | Trigger |
|---|---|---|---|---|
| `experiment-execution` | Every 6h | `test-lab/backlog.md` | `enhancement,experiment` | Validated experiment requires code change |
| `learning-review` | Every 6h | `.learnings/ERRORS.md` | `bug` | Confirmed bug in code |
| | | `.learnings/FEATURE_REQUESTS.md` | `enhancement` | Confirmed missing capability |
| `pipeline-health` | Every 6h | systemd/ChromaDB/WS daemon health | (auto) | Pipeline failure requiring code fix |

When a code change is NOT needed (profile param changes only), the sysadmin deploys directly via `traderbot profile update` without a GitHub issue.

### GitHub Issues

Issues are filed by the sysadmin agent via the 🐙 github skill (OpenClaw tool) into the `JsonDaRula69/TraderBot` repository. Templates enforce structured reporting:

| Template | Fields | Linked Source |
|---|---|---|
| [Bug Report](.github/ISSUE_TEMPLATE/bug_report.md) | Version, command, observed/expected, env, reproduction steps, related ERRORS.md entries | `.learnings/ERRORS.md` |
| [Feature Request](.github/ISSUE_TEMPLATE/feature_request.md) | Category (from `LearningCategory`), current state, proposed change, expected benefit, implementation sketch, related backlog entries | `.learnings/FEATURE_REQUESTS.md`, `test-lab/backlog.md` |

### CI Validation Pipeline

Every commit must go through a Pull Request. The CI pipeline runs in this order:

1. **frozen-check**: validates `uv.lock` is fresh (`uv sync --frozen`)
2. **lint**: ruff lint + format check (`ruff check`, `ruff format --check`)
3. **unit**: fast unit tests (`-m "unit"`) with coverage upload — gates subsequent jobs
4. **test**: full matrix (ubuntu-latest / macos-latest / windows-latest) — `-m "not live"`
5. **live**: API smoke tests — runs only on push to main (secrets unavailable on fork PRs)
6. **build**: builds wheel + verifies `pip install` works

Branch protection on `main` requires:
- All 6 status checks pass
- Branch is up-to-date with main
- For `jsondarula`: auto-merge bypasses review requirement
- For external contributors: 1 approving review required
- Force pushes blocked

### PR Template Checklist

Every PR includes a checklist:
- [ ] Tests pass (`uv run pytest -m "not live"`)
- [ ] Ruff lint + format clean
- [ ] VERSION bumped
- [ ] CHANGELOG.md updated
- [ ] Regression test written for bug fixes
- [ ] Cron/heartbeat changes verified with `--dry-run`
- [ ] Config changes use stable CLI (`openclaw config set`)
- [ ] Deployed to macpro-linux and verified

### Deployment Bar (Experiment Validation Gate)

Before any experiment result is deployed (as either a profile param update or a GitHub issue):

| Criterion | Threshold | Fails → |
|---|---|---|
| Sharpe ratio | >= 1.0 | REJECT in backlog.md |
| Win rate improvement | >= +5 percentage points vs control | REJECT |
| Sample size | >= 30 trades per treatment | REJECT (add replicates) |
| Code change required? | Must be confirmed design vs param-only | FILE ISSUE vs DEPLOY |

### Which Improvements Go Through This Pipeline

| Source | Destination | Mechanism |
|---|---|---|
| Agent LEARNINGS.md patterns (Recurrence >= 3) | Experiment backlog (DISCOVERED) | Heartbeat cron promotes to PENDING_REVIEW → sysadmin designs experiment |
| ERRORS.md entries (confirmed bugs) | GitHub issue (label: bug) | learning-review cron files issue with reproduction steps |
| FEATURE_REQUESTS.md entries (confirmed gaps) | GitHub issue (label: enhancement) | learning-review cron files issue with investigation results |
| Pipeline health failures (stale data, missing timers) | GitHub issue or direct fix | pipeline-health cron diagnoses and either files issue or runs fix |
| Profile param experiments (validated) | Direct deploy via `traderbot profile update` | experiment-execution cron runs backtest → on pass → DEPLOY with agent notification |