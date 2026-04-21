---
active: true
iteration: 5
max_iterations: 500
completion_promise: "DONE"
initial_completion_promise: "DONE"
started_at: "2026-04-21T05:16:50.175Z"
session_id: "ses_251b5df72ffesFdCicyoNnFt0F"
ultrawork: true
strategy: "continue"
message_count_at_start: 91
---
Alright, begin building Phase 1 and 2. Develop the required scaffolding As you build, and develop testing methology for yourself to comprehensively test every feature. save these into a new subdirectory /tests and a prompt including instructions on how to create a self looping testing protocol into /tests/TESTING_PROMPT.md. You may refer to @EXAMPLE_TESTING_PROMPT.md as for inspiration, but do not copy exactly. This is a prompt script used from an unrelated project and may contain a lot of information irrelevant to this project. It’s for reference and guidance only. Remember to reference documentation as your source of truth, and update your memories using CTX tools as you go.  Called the Read tool with the following input: {"filePath":"/Users/djtchill/Desktop/TraderBot/EXAMPLE_TESTING_PROMPT.md"} <path>/Users/djtchill/Desktop/TraderBot/EXAMPLE_TESTING_PROMPT.md</path>
<type>file</type>
<content>
1: # COMPREHENSIVE AUTOMATED CODE REVIEW AND TESTING PROTOCOL
2: 
3: > **Purpose:** This document is a prompt for LLM agents performing systematic code review and testing of the Mac Pro 2013 Ubuntu Autoinstall project. It provides exhaustive checklists for every phase, with project-specific checks grounded in how Subiquity, Ubuntu, and macOS actually work. Every script and flow path must be checked line by line.
4: >
5: > **Critical principle:** The checklists in this document define the MINIMUM scope of review — they are a starting point, not an exhaustive list of everything that could be wrong. The reviewer MUST go beyond the specific items listed here and perform thorough, original analysis on every line of code and every execution path. Do not limit your review to checking items off a list; actively seek bugs, logic errors, and structural problems that are NOT anticipated by the checklists. The goal is to discover ALL issues, not just confirm that listed checks pass.
6: 
7: ## Subagent Usage Guidelines
8: 
9: This review protocol is designed to be executed by a lead agent orchestrating subagents (explore, librarian, plan, oracle, etc.) for maximum parallelism and coverage. Follow these guidelines to use subagents effectively:
10: 
11: ### When to Use Subagents vs. Direct Tools
12: 
13: | Task Type | Best Approach | Why |
14: |-----------|--------------|-----|
15: | Searching for a **known pattern** (e.g., `grep -n 'eval '` in all shell scripts) | **Direct tools** (grep, read, ast_grep) | You already know exactly what to search for; subagent overhead is wasted |
16: | Discovering **unknown patterns** (e.g., "find all functions that call both echo and log_*") | **Explore subagent** | You know the shape of the bug but not the exact pattern; subagent can search broadly |
17: | Checking **external library behavior** (e.g., how Subiquity handles `wifis:` in netplan) | **Librarian subagent** | Requires documentation lookup, not local code search |
18: | **Architecture decisions** or debugging **hard problems** after 2+ failed attempts | **Oracle subagent** | Expensive but high-quality reasoning for complex tradeoffs |
19: | **Planning multi-step implementations** | **Plan subagent** | Produces structured work breakdowns with parallel execution opportunities |
20: 
21: ### Subagent Prompt Structure (MANDATORY)
22: 
23: Every subagent delegation MUST include these 6 sections. Vague prompts = poor results:
24: 
25: ```
26: 1. CONTEXT: What task I'm working on, which files/modules are involved, and what approach I'm taking
27: 2. GOAL: The specific outcome I need — what decision or action the results will unblock
28: 3. DOWNSTREAM: How I will use the results — what I'll build/decide based on what's found
29: 4. REQUEST: Concrete search instructions — what to find, what format to return, and what to SKIP
30: 5. CONSTRAINTS: File paths, severity levels, patterns to exclude, known false positives to ignore
31: 6. ANTI-PATTERNS: What NOT to do (e.g., "Don't just list files — show the specific line with context")
32: ```
33: 
34: ### Parallelism Rules
35: 
36: - **Fire 3-5 explore agents in parallel** for discovery tasks (Phase 0 architecture, Phase 1 static analysis)
37: - **Fire 2-3 librarian agents** when external documentation is needed (Subiquity schema, netplan behavior, DKMS)
38: - **Never block** waiting for a single subagent — continue with non-overlapping work
39: - **Cross-reference** subagent results before trusting them — always verify a sample of findings directly
40: - **Prefer direct tools for targeted checks** — if you can write the grep pattern yourself, do it. Reserve subagents for genuine discovery.
41: 
42: ### Subagent Anti-Patterns
43: 
44: 1. **Don't ask one subagent to "analyze everything."** Break broad tasks into narrow, pattern-specific searches. One subagent per bug class, per file group, per pattern.
45: 2. **NEVER repeat work assigned to a subagent.** Once you delegate a search to a subagent, you MUST NOT run the same search yourself. If an explore agent was tasked with finding all `eval` calls, running `grep -rn 'eval '` yourself is FORBIDDEN — you already delegated that work. Wait for the subagent's results, then use them. The only exception is verifying a small sample (3-5 items) to confirm accuracy. Repeating the full search wastes context budget and contradicts the reason for delegation.
46: 3. **Don't trust subagent results blindly.** Verify a sample of findings (3-5 items) directly before relying on the full result set. This is sample verification, not a full re-search — check a few results, then trust the rest.
47: 4. **Don't delegate trivial checks.** If you can run `grep -n 'trap.*EXIT' lib/tui.sh` in 2 seconds, do it yourself. Don't spawn a subagent for that.
48: 5. **Don't forget to cancel** idle background subagents after collecting results.
49: 
50: Execute a systematic, multi-phase review and testing cycle. Do not stop at static analysis. Each phase must be completed before moving to the next. Found bugs must be fixed, then ALL tests re-run from the beginning.
51: 
52: ## Table of Contents
53: 
54: - [Phase 0: Codebase Architecture Model](#phase-0-codebase-architecture-model)
55:   - [0.6 Bug Class Taxonomy and Custom Check Generation](#06-bug-class-taxonomy-and-custom-check-generation)
56: - [Phase 1: Static Code Analysis](#phase-1-static-code-analysis)
57:   - [1.1.1 TUI Module Raw Fallback Audit](#111-tui-module-raw-fallback-audit)
58:   - [1.1.2 TUI Dialog Subshell and Trap Audit](#112-tui-dialog-subshell-and-trap-audit)
59:   - [1.1.3 Logging Output Destination Audit](#113-logging-output-destination-audit)
60:   - [1.7 Systematic Execution Path Walkthrough](#17-systematic-execution-path-walkthrough)
61: - [Phase 2: Functional Behavior Testing](#phase-2-functional-behavior-testing)
62:   - [2.8 TUI Interactive Prompt Testing](#28-tui-interactive-prompt-testing)
63:   - [2.9 Option Selection Flow Pathway Tracing](#29-option-selection-flow-pathway-tracing)
64:   - [2.10 First-Run Flow Verification](#phase-210-first-run-flow-verification)
65:   - [2.11 Sudo File Ownership Audit](#phase-211-sudo-file-ownership-audit)
66:   - [2.12 Orphaned and Unused Code Detection](#phase-212-orphaned-and-unused-code-detection)
67:   - [2.13 Bash 3.2 Compatibility Verification](#phase-213-bash-32-compatibility-verification)
68:   - [2.14 Action Single-Execution Guarantee](#phase-214-action-single-execution-guarantee)
69:   - [2.15 Data Flow Tracing](#215-data-flow-tracing)
70:   - [2.16 Error Message Quality Audit](#216-error-message-quality-audit)
71: - [Phase 3: Integration and System Testing](#phase-3-integration-and-system-testing)
72: - [Phase 4: Best Practices and Patterns](#phase-4-best-practices-and-patterns)
73: - [Phase 5: Execution and Validation](#phase-5-execution-and-validation)
74:   - [5.4 VM Integration Test (Deferred to Phase 5.5)](#54-vm-integration-test-deferred-to-phase-55)
75:   - [5.5 Logging Verification](#55-logging-verification)
76: - [Phase 5.5: VM Integration Test](#phase-55-vm-integration-test)
77:   - [5.5.1 Build VM Test ISO](#551-build-vm-test-iso)
78:   - [5.5.2 Create VirtualBox VM](#552-create-virtualbox-vm)
79:   - [5.5.3 Start Webhook Monitor](#553-start-webhook-monitor)
80:   - [5.5.4 Run VM Installation](#554-run-vm-installation)
81:   - [5.5.5 Verify Installation Completion via SSH](#555-verify-installation-completion-via-ssh)
82:   - [5.5.6 Serial Log Deep Analysis](#556-serial-log-deep-analysis)
83:   - [5.5.7 Webhook Event Verification](#557-webhook-event-verification)
84:   - [5.5.8 Cleanup](#558-cleanup)
85: - [Phase 6: Refactoring and Simplification](#phase-6-refactoring-and-simplification)
86: - [Phase 7: Self-Improvement and Coverage Gap Analysis](#phase-7-self-improvement-and-coverage-gap-analysis)
87: - [Iterative Fix and Test Cycle](#iterative-fix-and-test-cycle)
88: - [Reporting Requirements](#reporting-requirements)
89: - [Final Checklist](#final-checklist)
90: 
91:
