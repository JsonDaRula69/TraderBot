# Draft: End-to-End Testing Framework Evolution

## Requirements (confirmed)
- Evolve the existing TESTING_PROMPT.md from a per-phase build review protocol into a comprehensive end-to-end test framework
- Line-by-line verification of every module and every function
- Start from installation flow (dependency check, API key configuration, OpenClaw implementation)
- Cover all the way through safe storage of secrets, agent tool calls, and decision-making analysis
- Reference docs/ as source of truth for expected behavior
- Build work is still in progress — some tests/modules may not exist yet (framework must accommodate unbuilt phases gracefully)

## Research Findings

### Current TESTING_PROMPT.md (1156 lines)
- Phase 0: Codebase Architecture Model (module dependency map, type audit, import validation, doc validation)
- Phase 1: Static Code Analysis (linter, type checker, risk module imports, monetary precision, Pydantic strict mode, audit trail, circuit breaker persistence, async/sync boundaries)
- Phase 2: Unit Tests (models, KalshiClient, WebSocket, risk limits, Kelly criterion, circuit breaker, audit trail, CLI, DB, analysis engine)
- Phase 2.11: Phase 5 Simulation Test Patterns (backtest, paper trading, strategy profiles, bootstrap)
- Phase 2.12: Phase 6 Self-Learning Test Patterns (learnings DB, WAL protocol, feature requests, degradation logging)
- Phase 2.13: Phase 7 News/Sentiment Test Patterns (source aggregation, classifier, sentiment scoring, impact assessment)
- Phase 2.14: Phase 8 Adaptation Test Patterns (Bayesian updates, guardrails, heartbeat, cron architecture)
- Phase 3: Integration Tests (trade evaluation flow, client→market data→risk pipeline, risk bypass tests, audit trail completeness)
- Phase 4: Property-Based and Invariant Tests (model fuzzing, Kelly invariants, circuit breaker invariants, risk limit invariants, decimal precision)
- Phase 5: Execution and Validation (full test suite, linter, type checker, coverage, fix and re-run cycle)
- Bug Class Taxonomy (8 documented bug classes with custom checks)
- Reporting Requirements (findings, severity, impact, evidence, root cause, fix applied, verification)

### Source Code Modules (all exist)
- `kalshi/`: client.py, config.py, demo.py, history.py, markets.py, models.py, trading.py, websocket.py, _normalize.py
- `analysis/`: indicators.py, odds.py, portfolio.py, signals.py
- `risk/`: audit.py, circuit_breaker.py, limits.py, sizing.py
- `simulation/`: adaptation.py, data_loader.py, engine.py, models.py, paper_trader.py, performance.py, profiles.py
- `news/`: classifier.py, embeddings.py, impact_assessor.py, models.py, sentiment_scorer.py, sources.py
- `db/`: decisions.py, learnings.py, positions.py, vectors.py
- `cli.py`, `auth.py`, `wal.py`, `learning.py`

### Test Files (44 test files exist)
- Phase 1-4 related: test_models.py, test_client.py, test_websocket.py, test_limits.py, test_sizing.py, test_circuit_breaker.py, test_audit.py, test_cli.py, test_db_init.py, test_decisions_db.py, test_positions_db.py, test_indicators.py, test_odds.py, test_portfolio.py, test_signals.py, test_risk_gate.py, test_demo.py, test_auth.py, test_history.py, test_markets.py, test_trading.py
- Phase 5: test_backtest_engine.py, test_data_loader.py, test_paper_trader.py, test_simulation_integration.py, test_simulation_models.py, test_strategy_profiles.py, test_performance.py
- Phase 6: test_learnings_db.py, test_learning_promotion.py, test_learning_integration.py, test_feature_requests.py, test_wal.py, test_vectors.py
- Phase 7: test_news_classifier.py, test_news_embeddings.py, test_news_models.py, test_news_sources.py, test_sentiment_scorer.py, test_impact_assessor.py
- Phase 8: test_adaptation.py

### Key Gaps in Current Testing_PROMPT.md (What's Missing for E2E)
1. **Installation/Setup Flow** — No test for: dependency installation, configuration of API keys, OpenClaw skill setup, keyring credential storage, env var resolution
2. **Authentication E2E** — No test for `traderbot auth login`, `auth set-key`, `auth list-keys`, `auth rotate`, keyring integration
3. **Secrets Management** — No test for keyring credential resolution order, .env fallback, env var fallback, SecretStr in Pydantic models, no secrets in logs
4. **OpenClaw Integration** — No test for SKILL.md command definitions matching CLI, workspace setup, cron architectures, isolated agentTurn systemEvent patterns
5. **End-to-End Trade Flow** — Phase 3 integration tests cover individual component flows but NOT the full install→auth→scan→analyze→trade→audit path
6. **Cross-Phase Integration** — No test that verifies all 8 phases work together as a system (e.g., news→sentiment→signal→risk→trade→audit→learn→adapt)
7. **Decision-Making Analysis** — No test verifying the full decision pipeline from signal generation through risk gate through audit logging through heartbeat review through learning promotion
8. **WAL Protocol E2E** — Tests exist for WAL write but not for crash recovery, reconciliation, or WAL read on restart
9. **Degradation/Fallback E2E** — Individual degradation tests exist but not a full system test where multiple services are unavailable
10. **Bootstrap Calibration E2E** — Not covered as an end-to-end flow
11. **Heartbeat Full Cycle** — Not tested as a full cycle (performance review → adapt → promote → feature request → circuit check → update HEARTBEAT.md)

### Architecture Constraints (from docs/)
- Toolkit is "dumb pipe with smart guards" — toolkit never decides strategy
- Risk module is immutable — no config-based limits
- All monetary values in cents as int
- Pydantic strict mode on all models
- Keyring for secrets, .env and env vars as fallback
- Three-loop architecture: Decision (5min agentTurn), Heartbeat (6hr agentTurn), News (event-driven systemEvent)
- WAL protocol for crash recovery
- Learning promotion requires 3+ recurrences across 2+ tasks within 30 days
- Feature requests are NEVER auto-implemented

## Scope Boundaries
- INCLUDE: Full end-to-end testing framework evolution, installation through decision analysis
- INCLUDE: Cross-phase integration tests
- INCLUDE: OpenClaw integration testing
- INCLUDE: Auth/secrets management testing
- INCLUDE: Degradation and fallback testing
- INCLUDE: Crash recovery and WAL E2E testing
- EXCLUDE: Writing actual test code (only the testing framework/prompt document)
- EXCLUDE: Running tests or fixing bugs in existing modules
- EXCLUDE: Modifying source code
- EXCLUDE: Changes to docs/ (source of truth, cannot modify without human approval)