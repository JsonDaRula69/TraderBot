# Scope Boundaries: Lab vs Treatment Design

This document defines the architectural boundary between the experiment infrastructure and the treatment modules. It exists because V2 violated this separation, and V3 enforces it.

---

## 1. Two Concerns

### Testing Lab (`experiments/v3/`)

The lab is the treatment-agnostic machinery that runs experiments. It owns the data pipeline, the execution loop, the scoring engine, and the statistical analysis. It never knows which treatments are loaded, and it never formats a prompt.

**Responsibilities**

- Fetch and cache market data from the Kalshi API.
- Fetch and cache weather forecasts from Open-Meteo Previous Runs.
- Build the stratified market pool (2×3×2 grid, 24+ markets).
- Assemble `TreatmentContext` objects with all available data.
- Execute the experiment loop: load data, call treatment, record decision, repeat.
- Compute P&L and delta profit per market.
- Run paired t-tests, effect sizes, and confidence intervals.
- Write results to the experiment database and generate reports.

**What the lab NEVER does**

- Import from `experiments/treatments/` or know treatment names.
- Format prompt strings. That belongs to the treatment.
- Decide what information a treatment should see. The context is always complete.
- Modify the scoring algorithm based on which treatment is running.
- Query an LLM directly without going through the treatment interface.

### Treatment Design (`experiments/treatments/`)

Treatments are plug-in modules. Each one implements `TreatmentInterface` and decides how to present data to the LLM. They are self-contained and interchangeable.

**Responsibilities**

- Implement `name`, `format_prompt()`, and `validate_response()`.
- Choose which `TreatmentContext` fields to include in the prompt.
- Define the LLM response schema (within the bounds of section 3 in `treatment_spec.md`).
- Parse and validate LLM output.

**What treatments NEVER do**

- Modify the experiment database schema.
- Change scoring logic or delta profit computation.
- Alter the experiment execution loop or timestep order.
- Import from `experiments/v3/` beyond the shared `TreatmentInterface` and `TreatmentContext`.
- Call external APIs directly. All data is provided by the harness.

---

## 2. The Boundary Rule

> **`v3/` code MUST NEVER import from `treatments/` or know treatment names. `treatments/` code MUST NEVER modify infrastructure. The only connection between the two is the `TreatmentInterface` contract.**

This rule is what makes the lab stable. You can add, remove, or rewrite treatments without touching a single line in `v3/`.

### How the boundary is enforced

- The experiment runner loads treatments from a registry file (`experiments/treatments/__init__.py`) at startup.
- The runner passes each treatment instance to the harness by reference.
- The harness only calls methods defined on `TreatmentInterface`. It has no access to treatment internals.
- The harness never branches on `treatment.name` to change behavior. The name is used only for logging and report filenames.

---

## 3. Why This Matters: The V2 Violation

In V2, all four treatment prompts were hardcoded inside `experiments/v2/simulation/treatment_harness.py` (lines 100-230 of the V2 harness). The file contained:

- Prompt templates for `control`, `raw_data`, `structured_prob`, and `calibration_bundle`.
- Formatting logic that mixed data loading with prompt construction.
- A large `if/elif` block that selected the prompt based on the treatment name string.

**Consequences**

- Adding a new treatment required editing the harness. This violated the open-closed principle.
- The harness had to be redeployed for every experiment change.
- Prompt logic was tightly coupled to data loading, making it impossible to test treatments in isolation.
- The harness knew treatment names, so it could accidentally introduce name-dependent behavior.

V3 fixes this by moving all treatment-specific logic into `experiments/treatments/`. The harness only knows the `TreatmentInterface` contract. A new treatment is a new file in the treatments folder, plus a one-line registry entry. The lab code never changes.

---

## 4. Module Classification Table

The table below lists every module in the V3 experiment system and shows which side of the boundary it belongs on.

| Module | Scope | Boundary Rule |
|--------|-------|---------------|
| `experiments/v3/harness.py` | **Lab** | Never imports from `treatments/`. Only calls `TreatmentInterface` methods. |
| `experiments/v3/runner.py` | **Lab** | Discovers treatments from registry at startup. Never branches on treatment names. |
| `experiments/v3/data_sources/kalshi.py` | **Lab** | Fetches and caches market data. No treatment awareness. |
| `experiments/v3/data_sources/open_meteo.py` | **Lab** | Fetches and caches forecast data. No treatment awareness. |
| `experiments/v3/scoring.py` | **Lab** | Computes P&L, delta profit, t-tests, effect sizes. Treatment-agnostic. |
| `experiments/v3/market_pool.py` | **Lab** | Builds stratified market pool. No treatment logic. |
| `experiments/v3/db/schema.py` | **Lab** | DB schema and migrations. Never modified by treatments. |
| `experiments/v3/db/queries.py` | **Lab** | Read/write experiment results. No treatment-specific queries. |
| `experiments/treatments/__init__.py` | **Treatment** | Registry file. Lists available treatments. No lab logic. |
| `experiments/treatments/control.py` | **Treatment** | Calls production `generate_signal()`. Does not modify infrastructure. |
| `experiments/treatments/raw_data.py` | **Treatment** | Example treatment. Formats prompts using raw forecast + market data. |
| `experiments/treatments/structured_prob.py` | **Treatment** | Example treatment. Includes structured probability estimates in prompt. |
| `experiments/shared/interface.py` | **Shared** | Defines `TreatmentInterface` and `TreatmentContext`. The contract both sides depend on. |

**Key principle**: If a module contains prompt formatting, treatment-specific logic, or LLM interaction, it belongs in `treatments/`. If it contains data loading, experiment execution, scoring, or statistical analysis, it belongs in `v3/`.

---

## 5. Violation Detection

If you are unsure whether a change respects the boundary, ask these questions:

1. Does the `v3/` file import from `treatments/`? **If yes, violation.**
2. Does the treatment file modify DB schema, scoring, or the experiment loop? **If yes, violation.**
3. Does the harness branch on `treatment.name` to change behavior? **If yes, violation.**
4. Does the treatment call an external API directly? **If yes, violation.**

When in doubt, move the code to the treatment side. The lab should be as dumb as possible about what a treatment does.
