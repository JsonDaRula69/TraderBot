# Comprehensive E2E Testing Protocol Update

## TL;DR

> **Quick Summary**: Rewrite and expand `tests/TESTING_PROMPT.md` from a phases-0-through-5 static analysis document into a comprehensive end-to-end testing protocol covering installation flow, all 8 phases, Kalshi API spec compliance, OpenClaw gateway integration, Telegram E2E, security deep audit, and real-world context testing. The protocol must be designed to be run repeatedly as development continues.
>
> **Deliverables**:
> - Updated `tests/TESTING_PROMPT.md` with comprehensive E2E testing protocol
> - New sections for installation/config flow, Kalshi API spec compliance, OpenClaw integration, security audit, Telegram E2E, agent decision-making analysis
> - Updated phase references (Phases 5-8 now built, not "pending")
> - Bug class taxonomy additions for security findings (SecretStr, file permissions, demo/prod isolation)
>
> **Estimated Effort**: Large
> **Parallel Execution**: YES - 4 waves
> **Critical Path**: Task 1 → Task 3 → Task 8 → Task 12 → Task 15

---

## Context

### Original Request
User wants to update `tests/TESTING_PROMPT.md` to implement a full end-to-end test of the entire TraderBot package. Must test every module and function, starting from installation flow through safe storage of secrets and agent tool calls. Must verify integrations are used to specification (Kalshi API, OpenClaw, security). Must reference `docs/` as source of truth and settle divergences. Must test real-world context. This is documentation update only.

### Interview Summary
**Key Discussions**:
- Real Kalshi demo API calls vs mocks: User chose **real demo API**
- OpenClaw integration depth: User chose **full gateway integration**
- Telegram testing: User chose **full Telegram E2E test**
- SecretStr findings: User chose **P1 bug — must fix**
- Docs divergence: User chose **update TESTING_PROMPT to match code**

**Research Findings**:
- Kalshi API: Full spec at docs.kalshi.com/openapi.yaml, RSA-PSS JWT auth, distinct demo/prod endpoints, ~10 req/sec rate limits
- Security: Plain `str` for credential fields (P1), SQLite without permission constraints, os.getenv without keyring fallback in some paths, no audit log tamper-evidence, hardcoded TEST_API_KEY
- OpenClaw: Workspace files (AGENTS.md, SOUL.md, TOOLS.md, IDENTITY.md, USER.md, HEARTBEAT.md/HEARTBEAT_DATA.md distinction), `isolated agentTurn` vs `systemEvent` cron architectures, skill system YAML frontmatter, Telegram channel via gateway
- Metis gap analysis: Identified 5 critical clarification points about scope boundaries, test environments, Phase 8 status, fix-vs-document decisions, and version discipline

### Metis Review
**Identified Gaps** (addressed):
- Scope creep risk: Clearly delimited as documentation-only update (no test code, no bug fixes)
- Test environment: Real credentials required for Kalshi demo; OpenClaw gateway required for E2E
- Phase 8 status: `simulation/adaptation.py`, `heartbeat.py`, `cron_loops.py` exist — update references
- Fix vs. document: P1 bugs (SecretStr) documented as findings in the protocol, not fixed in this plan
- Version discipline: Commit update with standard version bump per AGENTS.md conventions

---

## Work Objectives

### Core Objective
Rewrite `tests/TESTING_PROMPT.md` as a comprehensive, repeatable E2E testing protocol that covers every module, every function, every integration point, and every security concern — from installation through production readiness.

### Concrete Deliverables
- Updated `tests/TESTING_PROMPT.md` with all new and revised sections

### Definition of Done
- [ ] Every module in `src/traderbot/` has testing coverage specified in TESTING_PROMPT.md
- [ ] All integration points (Kalshi API, OpenClaw, Telegram) have verification checklists
- [ ] Security audit section covers SecretStr, file permissions, keyring, demo/prod isolation, audit tamper-evidence
- [ ] Phase references updated: Phases 5-7 marked as built, Phase 8 partial
- [ ] Bug class taxonomy updated with new security findings
- [ ] Installation/config flow section added with concrete validation steps
- [ ] All acceptance criteria are agent-executable (no "manually verify" or "visually check")

### Must Have
- Installation flow testing (dependencies, API key config, OpenClaw setup)
- Kalshi API spec compliance verification (every endpoint, auth, websocket, rate limits)
- OpenClaw workspace file validation (AGENTS.md, SOUL.md, IDENTITY.md, HEARTBEAT.md, HEARTBEAT_DATA.md)
- OpenClaw gateway integration testing (cron, heartbeat, skill execution, session management)
- Telegram E2E testing (gateway → Telegram → agent → skill call → response)
- Security deep audit (SecretStr, keyring, file permissions, demo/prod isolation, audit trail integrity)
- Agent decision-making analysis (toolkit outputs never contain buy/sell/hold signals)
- Docs vs. code validation updated for all phases
- All phase references updated to match current codebase reality

### Must NOT Have (Guardrails)
- DO NOT modify files in `docs/` without explicit human approval per AGENTS.md
- DO NOT write actual test code — this is documentation update only
- DO NOT attempt penetration testing or exploit vulnerabilities
- DO NOT send real Telegram messages without explicit human gate
- DO NOT make real trades on production Kalshi API
- DO NOT scope-creep into fixing P1 bugs (SecretStr, etc.) — document them as findings
- DO NOT leave "not yet built" markers for modules that actually exist
- DO NOT write vague acceptance criteria ("verify it works" → specify exact command, expected output, pass condition)

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest, ruff, mypy per pyproject.toml)
- **Automated tests**: Tests-after (this plan updates the testing PROTOCOL document, not test files)
- **Framework**: pytest (existing)

### QA Policy
Every task includes agent-executed QA scenarios that verify the TESTING_PROMPT.md update is correct, complete, and internally consistent.

- **File consistency**: Use `grep` and `read` to verify every module referenced actually exists
- **Phase accuracy**: Use `ls` and `glob` to confirm built modules match phase claims
- **Doc-code alignment**: Cross-reference TESTING_PROMPT.md against `docs/` and source code

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — research and verify current state):
├── Task 1: Audit current TESTING_PROMPT.md against codebase [deep]
├── Task 2: Audit all docs/ files against source code [deep]
└── Task 3: Audit security posture and identify all bug classes [deep]

Wave 2 (New sections — write in parallel):
├── Task 4: Write Phase 0.8 — Installation & Configuration Flow Tests [unspecified-high]
├── Task 5: Write Phase 0.9 — Kalshi API Spec Compliance Tests [unspecified-high]
├── Task 6: Write Phase 3.5 — OpenClaw Gateway Integration Tests [unspecified-high]
├── Task 7: Write Phase 5.5 — Security & Encryption Deep Audit [deep]
└── Task 8: Write Phase 4.5 — Agent Decision-Making Analysis [unspecified-high]

Wave 3 (Update existing sections):
├── Task 9: Update Phase 0 — Architecture Model for current modules [quick]
├── Task 10: Update Phases 2.11-2.14 — Simulation, Self-Learning, News, Adaptation [unspecified-high]
├── Task 11: Update Bug Class Taxonomy with security findings [quick]
└── Task 12: Write Phase 6.5 — Telegram E2E Integration Tests [unspecified-high]

Wave FINAL (After ALL tasks — 4 parallel reviews):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review — verify no test code was written [unspecified-high]
├── Task F3: Real QA — run grep/read commands to verify all references exist [unspecified-high]
└── Task F4: Scope fidelity check — verify Only TESTING_PROMPT.md was modified [deep]
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| 1 | - | 4, 5, 6, 7, 8, 9, 10, 11 |
| 2 | - | 4, 5, 6, 7, 8, 9, 10, 11 |
| 3 | - | 7, 11 |
| 4 | 1, 2 | 12 |
| 5 | 1, 2 | - |
| 6 | 1, 2 | 12 |
| 7 | 3 | - |
| 8 | 1, 2 | 12 |
| 9 | 1 | - |
| 10 | 1 | - |
| 11 | 3 | - |
| 12 | 4, 6, 8 | F1-F4 |

### Agent Dispatch Summary

- **Wave 1**: 3 — T1→`deep`, T2→`deep`, T3→`deep`
- **Wave 2**: 5 — T4→`unspecified-high`, T5→`unspecified-high`, T6→`unspecified-high`, T7→`deep`, T8→`unspecified-high`
- **Wave 3**: 4 — T9→`quick`, T10→`unspecified-high`, T11→`quick`, T12→`unspecified-high`
- **FINAL**: 4 — F1→`oracle`, F2→`unspecified-high`, F3→`unspecified-high`, F4→`deep`

---

## TODOs

---

## Final Verification Wave

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the updated TESTING_PROMPT.md end-to-end. Verify every "Must Have" is addressed. Verify no "Must NOT Have" violations. Verify all phase references match actual modules. Verify bug class taxonomy has security entries. Output: `Must Have [N/N] | Must NOT Have [N/N] | Phase references [N/N correct] | VERDICT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Verify ONLY TESTING_PROMPT.md was modified. Run `git diff --stat` to confirm. Verify no actual test code was written. Verify no files in `docs/` were modified. Verify no source files were modified. Output: `Files Modified [1] | Test Code [NONE] | Docs Modified [NONE] | VERDICT`

- [ ] F3. **Real QA** — `unspecified-high`
  Run grep commands to verify every module referenced in TESTING_PROMPT.md actually exists in the codebase. Run glob to confirm file existence. Cross-reference version claims against VERSION file. Verify acceptance criteria are all agent-executable (no "manually verify"). Output: `Module refs [N/N valid] | Version [MATCH] | Executable criteria [N/N] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  Compare testing-protocol plan against actual TESTING_PROMPT.md changes. Verify everything in the plan was implemented. Verify nothing beyond scope was added. Flag any unaccounted additions. Output: `Plan items [N/N implemented] | Scope creep [NONE/N items] | VERDICT`

---

## Commit Strategy

- **1**: `docs(tests): rewrite TESTING_PROMPT.md as comprehensive E2E protocol` — tests/TESTING_PROMPT.md

## Success Criteria

### Verification Commands
```bash
# Verify TESTING_PROMPT.md exists and is substantial
wc -l tests/TESTING_PROMPT.md  # Expected: >2000 lines

# Verify no source code was modified
git diff --stat src/  # Expected: no changes

# Verify no docs/ were modified
git diff --stat docs/  # Expected: no changes

# Verify only TESTING_PROMPT.md was modified
git diff --name-only  # Expected: tests/TESTING_PROMPT.md only
```

### Final Checklist
- [ ] All "Must Have" sections present in TESTING_PROMPT.md
- [ ] All "Must NOT Have" violations absent
- [ ] No files in docs/ were modified
- [ ] No actual test code was written
- [ ] All phase references updated (5-8 built status)
- [ ] Bug class taxonomy includes security findings
- [ ] All acceptance criteria are agent-executable
- [ ] TESTING_PROMPT.md references match actual codebase modules