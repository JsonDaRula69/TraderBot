# LLM as a Judge: Analysis for AutoDev Code Review

> Research analysis examining the feasibility, design patterns, and risks of using LLMs as evaluative judges in autonomous code review — specifically framed for AutoDev's review pipeline. Incorporates findings from 10+ academic papers published 2024–2026 and the oh-my-openagent production implementation.

---

## 1. What "LLM as a Judge" Means

The term originates from Zheng et al. (2023), "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena," which formalized a pattern already emerging in practice: using a language model to evaluate the outputs of other language models against a rubric. The core insight is that evaluation itself is a language task — comparing code against quality criteria, identifying defects, assessing architectural conformance — and therefore within the competency surface of LLMs.

Three judge variants are recognized:

| Variant | How it works | AutoDev application |
|---------|-------------|---------------------|
| **Single-judge** | One LLM evaluates one output against criteria | Routine PR review (current `autodev-review`) |
| **Multi-judge (panel)** | Multiple LLMs (or same LLM, different prompts) evaluate independently; verdict by majority vote or consensus | Critical-path changes (security, auth, money) |
| **Pairwise judge** | LLM compares old vs. new implementation, selects better one or identifies behavioral differences | Regression detection during refactoring |

---

## 2. What the Research Says (2024–2026)

### 2.1 Judge Reliability Is Lower Than Assumed

**"The Coin Flip Judge?" (arXiv:2606.13685)** ran 29 tasks with 50 pairwise and 50 pointwise trials per question using GPT-4o-mini and GPT-4.1-mini. Key findings:

- Pairwise preferences flip on average **13.6% of the time** across repeated identical evaluations
- **28% of questions** exceed a 20% flip rate — one question reached 56%
- GPT-4o-mini exhibits significant **first-position bias** (72% A-majority, p=0.024)
- Cross-judge agreement is only **76% (κ=0.51)** — barely moderate
- Deterministic decoding reduces but does not eliminate inconsistency
- **11 repeated trials** are needed for majority-vote to recover the 50-trial reference verdict with 95% probability on average; **15 trials** for high-variance questions

**Implication for AutoDev:** A single-pass review by one model is too noisy for high-stakes decisions. Multi-trial aggregation and position randomization should be standard for any review that touches the critical path (money, auth, security).

### 2.2 Production Judges Miss Most Real Defects

**"Catching One in Five" (arXiv:2606.10315)** studied a deployed LLM judge on a production multi-turn agent. Key findings:

- The judge surfaced **fewer than 25%** of human-confirmed systematic problems — 2 of 9 patterns in one batch
- In a 100-round batch where humans found 23 distinct defects, the operational gate **flagged zero rounds**
- The judge catches **turn-local issues** (wrong language, fabricated stats) but misses **cross-turn state issues** (cart hallucination, confirm-gate lockout, stale referents)
- The failure is **routing, not perception**: the scoring rubric has no category for behavioral dimensions (state-tracking, guardrails, recovery) where most defects cluster. 113 of 114 rounds whose raw judge note described a real defect were scored under the wrong rubric axis
- When the apparent defect rate is zero, **no statistical correction can recover the true rate**

**Implication for AutoDev:** The review rubric must cover behavioral dimensions (state tracking, financial correctness, error recovery), not just surface-level code quality. If the rubric doesn't have a category for a defect class, the judge literally cannot route findings to the right severity. The `autodev-review` skill's current dimensions (architecture, security, pattern, evidence) need expansion to include behavioral verification.

### 2.3 Self-Review Is Fundamentally Unreliable

**"Articulate but Wrong" (arXiv:2605.21537)** tested whether an LLM can recognize when its own output silently changes behavior. Across 1,980 modernization calls and 11 production LLMs:

- **31.7% of semantic drift cases** were silently endorsed by the same model that produced them
- Per-model self-miss rate is **strongly bimodal**: 0% on five models to 100% on one widely deployed model
- Several models **explicitly articulated the very semantic distinction** that broke their output, then declared behavior preserved
- Drift rate is **non-monotone in model capability and price**: ranges 5.6%–46.7%, does not track model scale

**Implication for AutoDev:** The implementer model MUST NOT be the sole reviewer. This is already partially addressed (Atlas = GLM 5.1, Oracle/Momus = Deepseek V4 Pro), but the finding that models can *articulate the correct distinction and still get it wrong* means confidence tags must be treated skeptically, not trusted because the reasoning sounds plausible.

### 2.4 Adversarial Manipulation of Judges Is Effective

**"Turning Bias into Bugs / BITE" (arXiv:2605.26156)** introduced a black-box adversarial framework that learns semantics-preserving edits to inflate LLM judge scores:

- **>65% attack success rate** across diverse judges and tasks
- Raises scores by **1–2 points on a 9-point scale** while preserving semantic equivalence
- Evades standard style-control methods and detection baselines
- Operates as a contextual bandit — no access to model parameters or gradients

**Implication for AutoDev:** In an adversarial context (someone intentionally submitting code to bypass review), the judge can be gamed. For Traderbot specifically, this means the judge should not be the sole security gate for external contributions. For internal AutoDev code, the risk is lower since the implementer is not adversarial, but pattern-aware "good enough" code can still exploit verbosity and structure biases.

### 2.5 Context Dilution Is Real and Counter-Intuitive

**SWE-PRBench (arXiv:2603.26130)** evaluated 8 frontier models on PR review with 350 human-annotated PRs:

- Models detect only **15–31% of human-flagged issues** on diff-only configuration
- Performance **degrades monotonically** from diff-only to full context — more context is worse, not better
- The dominant failure mechanism: **attention dilution** in long contexts. A 2,000-token diff-with-summary prompt **outperforms** a 2,500-token full-context prompt
- Top 4 models are statistically indistinguishable (mean score 0.147–0.153), with a clear tier gap to the remaining 4

**AACR-Bench (arXiv:2601.19494)** confirmed and extended this:

- AI-assisted expert-verified annotation uncovered **285% more defects** than raw PR comments
- Context granularity and retrieval method significantly impact performance, varying by model and language
- Agent architectures perform differently from non-agent LLMs on the same benchmarks

**Implication for AutoDev:** The review prompt should be concise and focused. More context is not better — it dilutes attention. The current `autodev-review` skill's Step 1 (gather context) should produce a **structured summary**, not a full context dump. The plan + evidence + diff-with-summary pattern (not full files) is the right approach.

### 2.6 Social Engineering Defeats LLM Reviewers

**SEVRA-BENCH (arXiv:2606.13757)** tested whether LLM reviewers can reject malicious PRs where the attacker controls both the code and the PR description:

- 1,062 malicious PRs built from real CVE-linked fixes, inverted, and wrapped in 15 social-engineering framings
- **Sharp gap** between closed-source and open-source model security capabilities
- Social engineering framings (urgency, authority, false evidence of prior approval) significantly increase approval rates

**Implication for AutoDev:** The liaison bridge introduces external PRs from Traderbot agents. While these are internal, the principle holds: the review should be **content-driven, not framing-driven**. The judge should evaluate the diff, not the PR description's framing. The current skill's Step 1 (identify which issue and plan the PR follows) is good — it anchors the review to the plan's acceptance criteria rather than the PR author's narrative.

### 2.7 Trust Calibration Is the Core Problem

**"Trust-Calibrated Code Review" (arXiv:2606.01969)** conducted a participatory design study with JetBrains and 17 industry practitioners:

- Reviewing LLM-generated multi-file changes is a **trust-calibration problem, not a diffing problem**
- Developers need risk signals at **three granularities**: overview, file-analysis, code snippet
- Seven design constructs emerged: chunk, risk-per-line, risk-per-file, judge, walk-through, zooming in/out, security cage
- 63% of respondents expected reduced overall review effort, 52% reduced trust-assessment effort

**Implication for AutoDev:** The review output should provide layered risk signals, not a flat list of findings. The current skill's table format (severity, category, finding, file:line) is a start but doesn't provide the overview-to-detail drill-down that developers need. The "security cage" concept — a containment boundary for high-risk changes — maps directly to Traderbot's need to quarantine money-handling code.

### 2.8 Multi-Agent Debate Has Role Asymmetry

**"The Confident Liar" (arXiv:2606.10296)** studied multi-agent debate with LLM-as-judge scoring:

- Confidence aligns with judged reasoning quality **twice as strongly for the Constructor as for the Auditor**
- Confidence-based detection of critical reasoning failures: AUROC **0.804 for Constructor vs. 0.634 for Auditor**
- Role asymmetry means the same confidence signal means different things from different agents

**Implication for AutoDev:** The implementer's self-assessed confidence should be weighted differently than the reviewer's. If Atlas (implementer) says "I'm confident this is correct," that's less reliable than Oracle (reviewer) saying "I'm confident this is correct." The reviewer role has inherently better calibration for defect detection.

---

## 3. The OmO Production Implementation: A Reference Architecture

Oh-my-openagent (OmO) implements a sophisticated multi-agent review system that directly addresses many of the research findings above. Key components:

### 3.1 Three-Layer Review Architecture (Pre-Publish Review)

| Layer | Agents | What They Check | Model |
|-------|--------|----------------|-------|
| Per-Change Deep Dive | Up to 10 ultrabrain | Each logical change group individually | Deepseek V4 Pro |
| Holistic Review | 5 (goal, QA, code quality, security, context) | Full changeset, cross-cutting | Mixed |
| Release Synthesis | 1 oracle | Overall readiness, version bump, breaking changes | Oracle |

This maps to research finding 2.2: the multi-layer structure ensures no single rubric axis is responsible for all defect types. The holistic review catches cross-cutting issues that per-change analysis misses.

### 3.2 Artifact-Backed, Skeptical Gate Review

The `lazycodex-gate-reviewer` role explicitly assumes **"the work has already failed before"**:

> "Assume the work has already failed before. Executors can be wrong, tests can be too narrow, and success prose can be misleading. Verify everything yourself from the artifacts."

This directly addresses finding 2.3 (self-review failure): the gate reviewer treats all prior evidence as **untrusted until verified against referenced artifact paths**. It checks:
- Every intended change landed
- Every success criterion has evidence
- Every adversarial class has a real verdict
- No skipped, partial, inferred, or not_applicable result is used as success

### 3.3 Anti-Slop Review

The code reviewer runs an explicit **overfit/slop detection pass** that flags:
- Deletion-only tests
- Tautological tests (tests that only verify what was removed)
- Implementation-mirroring tests (tests that just check constants from the implementation)
- Unnecessary production extraction/parsing/normalization
- Scope drift disguised as "thoroughness"

This addresses the "completeness illusion" bias from finding 2.5: a review that covers all rubric categories can feel thorough while each category is superficially checked.

### 3.4 Blocker Classification System

OmO's quality-gate system classifies blockers with specific patterns (e.g., `GHCR_PULL_ACCESS`, `EXTERNAL_AUTHORIZATION_REQUIRED`) and normalizes evidence for deduplication. This prevents the same issue from being reported multiple times and allows systematic tracking.

### 3.5 Review-Work: 5-Agent Parallel Orchestrator

The `review-work` skill spawns 5 specialized sub-agents in parallel:
1. **Goal Verifier** (Oracle): Did we build what was asked?
2. **QA Executor** (unspecified-high): Does it actually work?
3. **Code Reviewer** (Oracle): Is the code well-written?
4. **Security Auditor** (Oracle): Is it secure?
5. **Context Miner** (unspecified-high): Did we miss any context?

All 5 must pass. If even one fails, the review fails. This is a strict multi-judge panel with unanimous requirement — more conservative than majority vote but appropriate for a release gate.

---

## 4. Design Recommendations for AutoDev

Based on the research findings and OmO's production patterns, here are specific recommendations for upgrading AutoDev's review pipeline:

### 4.1 Replace Single-Judge with Panel Review

**Current:** Oracle reviews alone.
**Recommended:** Three-judge panel for all reviews, five-judge panel for critical paths.

| Change type | Panel size | Composition | Verdict mechanism |
|------------|-----------|-------------|-------------------|
| Routine (docs, config, non-critical) | 3 | 2× Deepseek V4 Pro (different prompts) + 1× GLM 5.1 | Majority vote per finding |
| Standard (new features, refactors) | 3 | Same as above | Majority vote per finding, escalate any 2+ severity findings |
| Critical (money, auth, security) | 5 | 2× Deepseek V4 Pro (different prompts) + 2× Deepseek V4 Pro (different prompts) + 1× GLM 5.1 | Unanimous on severity, majority on findings, human confirmation required |

**Why different prompts matter more than different models** (finding 2.1): two judges with different rubrics on the same model outperform two models with the same prompt. Prompt diversity targets different failure modes.

Three prompt archetypes for the panel:
1. **Structural reviewer**: "Does this code follow the project's architecture patterns? Check each module boundary."
2. **Adversarial reviewer**: "Assume there is a bug. Find it. What's the worst thing this code could do?"
3. **Behavioral reviewer**: "Trace the execution path for the happy path and the three most likely error paths. Does each handle correctly?"

### 4.2 Restructure the Review Rubric

The current `autodev-review` skill has 5 steps: architecture, security, pattern, evidence. Research (finding 2.2) shows this misses behavioral dimensions. Expand to:

| Dimension | What it checks | Traderbot-specific |
|-----------|---------------|-------------------|
| **Architecture** | Module boundaries, coupling, new dependencies | Kalshi module isolation, gateway config integrity |
| **Security** | Hardcoded secrets, auth bypass, injection | Kalshi API key handling, trade execution auth |
| **Behavioral correctness** | Happy path + error paths, state transitions | P&L settlement rounding, order state machine, race conditions |
| **Pattern conformance** | Naming, error handling, logging, typing | Traderbot coding conventions |
| **Evidence completeness** | Every acceptance criterion has proof, BEFORE/AFTER | Traderbot-specific gates T1-T3 |
| **Slop/overfit detection** | Tautological tests, unnecessary abstraction, scope drift | No AI-generated cruft |

### 4.3 Implement Evidence-Bound, Artifact-Backed Judgment

Following OmO's gate-reviewer pattern, every finding must reference a specific artifact:

```
Finding format:
| # | Severity | Category | Finding | Evidence | Confidence |
|---|----------|----------|---------|----------|------------|
| 1 | HIGH | Behavioral | P&L settlement uses float arithmetic | `settlement.py:147` computes `price * qty` as float, can produce rounding drift | HIGH |
| 2 | LOW | Pattern | Inconsistent logger name | `risk.py:23` uses `logger = logging.getLogger('risk')` instead of `__name__` | MEDIUM |
```

Findings without specific file:line:evidence are flagged as **LOW confidence** and **do not block merge**, regardless of stated severity.

### 4.4 Add Pairwise Regression Detection

For any PR that modifies existing code (not pure additions), add a step between the current Steps 2 and 3:

> **Step 2.5: Behavioral regression check**
> Compare the old and new implementations. Identify any behavioral differences not explicitly called for in the plan. For Traderbot-specific modules (trade execution, settlement, P&L), trace the execution path for known edge cases and verify behavioral parity.

This addresses finding 2.3 (self-review failure) and finding 2.7 (trust calibration). The pairwise comparison focuses the judge's attention on *what changed* rather than *what the code looks like*.

### 4.5 Implement Context Budget Management

Following finding 2.5 (SWE-PRBench: concise context beats verbose context):

| Context element | Budget | Format |
|----------------|-------|--------|
| Plan summary | 500 tokens | Structured: acceptance criteria + affected modules |
| Diff-with-summary | 2,000 tokens | Diff + file-level summary of what each file does |
| Evidence directory listing | 200 tokens | File names and sizes |
| Ratified lore (relevant) | 500 tokens | Loreguard search results for tags matching the PR |
| Traderbot-specific gates | 300 tokens | Checklist of applicable T1-T3 gates |
| **Total review context** | **~3,500 tokens** | |

Do NOT include: full file contents, entire git history, all lore records, all reference docs. These are available on demand but should not be in the initial review context.

### 4.6 Add Anti-Rubber-Stamp and Calibration Mechanisms

From findings 2.1, 2.2, and 2.4:

1. **Require at least one finding per review**, even for approved PRs. "No issues found" is a red flag, not a green light.
2. **Track approval rate** over time. Alert if >90% (rubber-stamping) or <50% (over-blocking).
3. **Inject synthetic defect PRs monthly** (red-team testing). Create PRs with known defects and verify the judge catches them.
4. **Randomize position** in pairwise comparisons to mitigate position bias.
5. **Run 3 trials** for critical-path reviews and take majority verdict.

### 4.7 Integrate with Loreguard for Trust-Calibrated Review

When the judge makes a finding that references a ratified decision:

1. **Corroborated**: Finding aligns with Loreguard lore → increase confidence
2. **Contradicted**: Finding contradicts Loreguard lore → `report_conflict`, draft counter-record, human decides
3. **Unsupported**: No lore exists for this finding type → reduced confidence, note as "unsupported finding"

This creates the feedback loop between judge and knowledge base that addresses the cascading failure mode (finding 2.3, where judge-approved defects get incorporated as "correct patterns").

### 4.8 Add the Security Cage Concept

From finding 2.7 (trust-calibrated review), implement a **security cage** for critical-path code:

Files matching these patterns are automatically flagged as critical-path:
- `**/trade_execution/**`
- `**/settlement/**`
- `**/kalshi/**`
- `**/auth/**`
- `**/security/**`
- Any file with `@critical` in a comment

Critical-path changes:
- Require 5-judge panel instead of 3
- Require human approval regardless of grace period
- Require behavioral regression check (Step 2.5)
- Require evidence that specifically addresses financial correctness (not just "tests pass")

### 4.9 Implement Judge Calibration Pipeline

Add to `.autodev/`:

```
.autodev/
├── evidence/
│   └── judge-calibration/
│       ├── <YYYY-MM-DD>-calibration.md      # Periodic calibration results
│       ├── <YYYY-MM-DD>-override.md          # Human override records
│       └── red-team/
│           ├── <YYYY-MM-DD>-red-team.md      # Synthetic defect test results
│           └── templates/                     # Known-defect PR templates
│               ├── hardcoded-secret.md
│               ├── float-arithmetic-pnl.md
│               ├── race-condition-order.md
│               └── missing-error-handling.md
```

Track these metrics:

| Metric | Target | Alert threshold |
|--------|--------|-----------------|
| True positive rate (bugs caught / total bugs) | >70% | <50% |
| False positive rate (false blocks / total blocks) | <20% | >35% |
| Approval rate | 70–85% | >95% or <50% |
| Finding specificity (% with exact file:line) | >80% | <50% |
| Human override rate | <10% | >25% |

### 4.10 Human Override Protocol

When a human overrides a judge decision:

1. Comment on the PR with `@autodev-override <reason>`
2. Override is logged to `.autodev/evidence/judge-calibration/`
3. If the override contradicts a judge finding, the judge prompt is reviewed in the next calibration cycle
4. If the override reveals a lore gap, file a `suggest_lore` draft
5. If the same type of override occurs 3+ times, the review prompt is updated to account for the pattern

This is the **human-optional but human-valuable** feedback loop. Humans don't need to review every PR, but when they do, their feedback makes the judge better for future reviews.

---

## 5. Updated Review Skill Design

Based on all findings, the upgraded `autodev-review` skill should follow this flow:

```
Step 0: Classify change criticality
  ├── Critical path → 5-judge panel + human confirmation required
  ├── Standard → 3-judge panel
  └── Routine → single judge + at least one finding required

Step 1: Assemble focused review context (≤3,500 tokens)
  ├── Plan summary (acceptance criteria, affected modules)
  ├── Diff-with-summary (not full files)
  ├── Evidence directory listing
  ├── Relevant Loreguard lore (search by tags matching PR)
  └── Applicable Traderbot-specific gates (T1-T3)

Step 2: Dispatch panel
  ├── Judge A: Structural reviewer ("Does this follow architecture?")
  ├── Judge B: Adversarial reviewer ("What's the worst it could do?")
  └── Judge C: Behavioral reviewer ("Does it preserve behavior?")
  (For critical: add Judge D: Financial correctness, Judge E: Security specialist)

Step 3: Aggregate findings
  ├── Majority vote per finding (≥2 judges agree → finding accepted)
  ├── Unanimous severity for HIGH/CRITICAL → blocking
  ├── Single-judge HIGH → noted, not blocking
  └── Any judge LOW → advisory only

Step 4: Behavioral regression check (if modifying existing code)
  └── Pairwise comparison: old vs new, identify behavioral differences not in the plan

Step 5: Loreguard cross-reference
  ├── Corroborated findings → increase confidence
  ├── Contradicted findings → report_conflict, draft counter-record
  └── Unsupported findings → reduce confidence

Step 6: Post structured review
  ├── Findings table with severity, category, evidence, confidence
  ├── Overall verdict: APPROVE / REQUEST CHANGES / BLOCK
  ├── Critical-path flagging if applicable
  └── Calibration data logged for tracking

Step 7: Label and escalate
  ├── All clean → autodev-ready
  ├── Non-blocking findings → autodev-ready (findings noted)
  ├── Blocking findings → autodev-blocked
  └── Critical path → autodev-blocked + human approval required
```

---

## 6. Limitations and Honest Assessment

### What LLM judges cannot do:

1. **Verify runtime behavior.** A judge reads code but cannot run it. Tests and CI remain essential — the judge supplements them, not replaces them.
2. **Predict emergent system behavior.** Ten individually-approved PRs can interact in ways no single review catches. Integration testing and monitoring are irreplaceable.
3. **Make architectural judgment calls.** The judge can verify conformance to existing patterns, but deciding whether a new pattern is needed requires engineering judgment the judge can inform but not make.
4. **Stay calibrated without feedback.** Without human overrides and red-team testing, judge quality degrades as the codebase evolves away from the judge's training data.
5. **Detect all security vulnerabilities.** SEVRA-BENCH shows LLM reviewers can be socially engineered. Novel vulnerability patterns outside training data will be missed.

### What LLM judges do well:

1. **Pattern enforcement.** "Does this follow conventions?" is a pattern-matching task LLMs handle well.
2. **Known vulnerability detection.** Hardcoded secrets, SQL injection, XSS — LLMs catch these reliably.
3. **Completeness checking.** "Did the PR address all acceptance criteria?" is verification, which LLMs handle well when criteria are explicit.
4. **Consistency.** The same rubric, every time, without fatigue or disinterest.
5. **Scalability.** Every PR gets reviewed, including the ones humans skip.

### The bottom line:

LLM-as-judge for code review is a **high-value, medium-risk tool** that catches the defect classes humans miss on their worst days but misses the defect classes humans catch on their best days. Deploy it as:

- **First gate** (before human review, after CI)
- **Consistent enforcer** of pattern rules and known vulnerability classes
- **Completeness verifier** against explicit acceptance criteria
- **Escalation signal** for critical-path changes that need human eyes

Do NOT deploy it as:
- A replacement for human review of critical changes
- A replacement for runtime testing (CI, integration tests, production monitoring)
- A substitute for architectural decision-making

---

## 7. References

### Academic Papers

1. Zheng et al. (2023). "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena." arXiv:2306.05685. — Foundational paper; 80–85% human agreement, position/verbosity/self-enhancement biases documented.
2. "The Coin Flip Judge?" (arXiv:2606.13685). — 13.6% preference flip rate; 28% of questions exceed 20% flip; 11 trials needed for 95% confidence; cross-judge agreement only 76%.
3. "Turning Bias into Bugs / BITE" (arXiv:2605.26156). — Black-box adversarial framework; >65% attack success rate; 1–2 point inflation on 9-point scale.
4. "Catching One in Five" (arXiv:2606.10315). — Production LLM judge catches <25% of real defects; failure is routing (rubric gaps), not perception; zero operational flags in 100-round batch with 23 human-confirmed defects.
5. "Articulate but Wrong" (arXiv:2605.21537). — Self-review endorses 31.7% of semantic drift cases; bimodal per-model failure (0% to 100%); models articulate correct distinction then declare behavior preserved.
6. "Trust-Calibrated Code Review" (arXiv:2606.01969). — Participatory design study; review is trust-calibration, not diffing; three-level workflow; seven design constructs including security cage.
7. "SWE-PRBench" (arXiv:2603.26130). — 8 frontier models detect 15–31% of human-flagged issues; context dilution; 2K-token diff-with-summary outperforms 2.5K-token full context.
8. "AACR-Bench" (arXiv:2601.19494). — AI-assisted expert annotation increases defect coverage 285%; context granularity and retrieval method significantly impact performance.
9. "SEVRA-BENCH" (arXiv:2606.13757). — LLM code reviewers socially engineered via malicious PRs; 1,062 CVE-based adversarial PRs; sharp gap between open/closed-source model security capabilities.
10. "The Confident Liar" (arXiv:2606.10296). — Multi-agent debate; confidence aligns with quality 2x more for Constructor than Auditor; role asymmetry in confidence signals.

### Production Implementations

11. **oh-my-openagent** (code-yeongyu/oh-my-openagent). — 16-agent pre-publish review; 5-agent review-work orchestrator; quality gate with blocker classification; artifact-backed skeptical gate reviewer; anti-slop detection; role-specific models and reasoning efforts.
12. **Claude Code Action** (anthropics/claude-code-action). — GitHub-native agent for PR review and code implementation; supports @claude mentions, automatic mode detection, path-specific reviews, security-focused reviews.

### AutoDev Framework Documents

13. `ARCHITECTURE.md` — System architecture, liaison bridge, label taxonomy, workflow.
14. `KNOWLEDGE-ARCHITECTURE.md` — 5-tier knowledge system, behavioral guardrails, Loreguard/Magic Context integration.
15. `skills/autodev-review/SKILL.md` — Current review skill design.
16. `skills/autodev-implement/SKILL.md` — Implementation skill with Traderbot-specific gates T1-T3.
17. `config/standing-orders.md` — 18 non-negotiable rules for AutoDev agents.
18. `config/team-spec.json` — Team composition and role assignments.
