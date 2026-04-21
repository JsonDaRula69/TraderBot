# COMPREHENSIVE AUTOMATED CODE REVIEW AND TESTING PROTOCOL

> **Purpose:** This document is a prompt for LLM agents performing systematic code review and testing of the Mac Pro 2013 Ubuntu Autoinstall project. It provides exhaustive checklists for every phase, with project-specific checks grounded in how Subiquity, Ubuntu, and macOS actually work. Every script and flow path must be checked line by line.
>
> **Critical principle:** The checklists in this document define the MINIMUM scope of review — they are a starting point, not an exhaustive list of everything that could be wrong. The reviewer MUST go beyond the specific items listed here and perform thorough, original analysis on every line of code and every execution path. Do not limit your review to checking items off a list; actively seek bugs, logic errors, and structural problems that are NOT anticipated by the checklists. The goal is to discover ALL issues, not just confirm that listed checks pass.

## Subagent Usage Guidelines

This review protocol is designed to be executed by a lead agent orchestrating subagents (explore, librarian, plan, oracle, etc.) for maximum parallelism and coverage. Follow these guidelines to use subagents effectively:

### When to Use Subagents vs. Direct Tools

| Task Type | Best Approach | Why |
|-----------|--------------|-----|
| Searching for a **known pattern** (e.g., `grep -n 'eval '` in all shell scripts) | **Direct tools** (grep, read, ast_grep) | You already know exactly what to search for; subagent overhead is wasted |
| Discovering **unknown patterns** (e.g., "find all functions that call both echo and log_*") | **Explore subagent** | You know the shape of the bug but not the exact pattern; subagent can search broadly |
| Checking **external library behavior** (e.g., how Subiquity handles `wifis:` in netplan) | **Librarian subagent** | Requires documentation lookup, not local code search |
| **Architecture decisions** or debugging **hard problems** after 2+ failed attempts | **Oracle subagent** | Expensive but high-quality reasoning for complex tradeoffs |
| **Planning multi-step implementations** | **Plan subagent** | Produces structured work breakdowns with parallel execution opportunities |

### Subagent Prompt Structure (MANDATORY)

Every subagent delegation MUST include these 6 sections. Vague prompts = poor results:

```
1. CONTEXT: What task I'm working on, which files/modules are involved, and what approach I'm taking
2. GOAL: The specific outcome I need — what decision or action the results will unblock
3. DOWNSTREAM: How I will use the results — what I'll build/decide based on what's found
4. REQUEST: Concrete search instructions — what to find, what format to return, and what to SKIP
5. CONSTRAINTS: File paths, severity levels, patterns to exclude, known false positives to ignore
6. ANTI-PATTERNS: What NOT to do (e.g., "Don't just list files — show the specific line with context")
```

### Parallelism Rules

- **Fire 3-5 explore agents in parallel** for discovery tasks (Phase 0 architecture, Phase 1 static analysis)
- **Fire 2-3 librarian agents** when external documentation is needed (Subiquity schema, netplan behavior, DKMS)
- **Never block** waiting for a single subagent — continue with non-overlapping work
- **Cross-reference** subagent results before trusting them — always verify a sample of findings directly
- **Prefer direct tools for targeted checks** — if you can write the grep pattern yourself, do it. Reserve subagents for genuine discovery.

### Subagent Anti-Patterns

1. **Don't ask one subagent to "analyze everything."** Break broad tasks into narrow, pattern-specific searches. One subagent per bug class, per file group, per pattern.
2. **NEVER repeat work assigned to a subagent.** Once you delegate a search to a subagent, you MUST NOT run the same search yourself. If an explore agent was tasked with finding all `eval` calls, running `grep -rn 'eval '` yourself is FORBIDDEN — you already delegated that work. Wait for the subagent's results, then use them. The only exception is verifying a small sample (3-5 items) to confirm accuracy. Repeating the full search wastes context budget and contradicts the reason for delegation.
3. **Don't trust subagent results blindly.** Verify a sample of findings (3-5 items) directly before relying on the full result set. This is sample verification, not a full re-search — check a few results, then trust the rest.
4. **Don't delegate trivial checks.** If you can run `grep -n 'trap.*EXIT' lib/tui.sh` in 2 seconds, do it yourself. Don't spawn a subagent for that.
5. **Don't forget to cancel** idle background subagents after collecting results.

Execute a systematic, multi-phase review and testing cycle. Do not stop at static analysis. Each phase must be completed before moving to the next. Found bugs must be fixed, then ALL tests re-run from the beginning.

## Table of Contents

- [Phase 0: Codebase Architecture Model](#phase-0-codebase-architecture-model)
  - [0.6 Bug Class Taxonomy and Custom Check Generation](#06-bug-class-taxonomy-and-custom-check-generation)
- [Phase 1: Static Code Analysis](#phase-1-static-code-analysis)
  - [1.1.1 TUI Module Raw Fallback Audit](#111-tui-module-raw-fallback-audit)
  - [1.1.2 TUI Dialog Subshell and Trap Audit](#112-tui-dialog-subshell-and-trap-audit)
  - [1.1.3 Logging Output Destination Audit](#113-logging-output-destination-audit)
  - [1.7 Systematic Execution Path Walkthrough](#17-systematic-execution-path-walkthrough)
- [Phase 2: Functional Behavior Testing](#phase-2-functional-behavior-testing)
  - [2.8 TUI Interactive Prompt Testing](#28-tui-interactive-prompt-testing)
  - [2.9 Option Selection Flow Pathway Tracing](#29-option-selection-flow-pathway-tracing)
  - [2.10 First-Run Flow Verification](#phase-210-first-run-flow-verification)
  - [2.11 Sudo File Ownership Audit](#phase-211-sudo-file-ownership-audit)
  - [2.12 Orphaned and Unused Code Detection](#phase-212-orphaned-and-unused-code-detection)
  - [2.13 Bash 3.2 Compatibility Verification](#phase-213-bash-32-compatibility-verification)
  - [2.14 Action Single-Execution Guarantee](#phase-214-action-single-execution-guarantee)
  - [2.15 Data Flow Tracing](#215-data-flow-tracing)
  - [2.16 Error Message Quality Audit](#216-error-message-quality-audit)
- [Phase 3: Integration and System Testing](#phase-3-integration-and-system-testing)
- [Phase 4: Best Practices and Patterns](#phase-4-best-practices-and-patterns)
- [Phase 5: Execution and Validation](#phase-5-execution-and-validation)
  - [5.4 VM Integration Test (Deferred to Phase 5.5)](#54-vm-integration-test-deferred-to-phase-55)
  - [5.5 Logging Verification](#55-logging-verification)
- [Phase 5.5: VM Integration Test](#phase-55-vm-integration-test)
  - [5.5.1 Build VM Test ISO](#551-build-vm-test-iso)
  - [5.5.2 Create VirtualBox VM](#552-create-virtualbox-vm)
  - [5.5.3 Start Webhook Monitor](#553-start-webhook-monitor)
  - [5.5.4 Run VM Installation](#554-run-vm-installation)
  - [5.5.5 Verify Installation Completion via SSH](#555-verify-installation-completion-via-ssh)
  - [5.5.6 Serial Log Deep Analysis](#556-serial-log-deep-analysis)
  - [5.5.7 Webhook Event Verification](#557-webhook-event-verification)
  - [5.5.8 Cleanup](#558-cleanup)
- [Phase 6: Refactoring and Simplification](#phase-6-refactoring-and-simplification)
- [Phase 7: Self-Improvement and Coverage Gap Analysis](#phase-7-self-improvement-and-coverage-gap-analysis)
- [Iterative Fix and Test Cycle](#iterative-fix-and-test-cycle)
- [Reporting Requirements](#reporting-requirements)
- [Final Checklist](#final-checklist)

---

## PHASE 0: CODEBASE ARCHITECTURE MODEL

Perform this phase FIRST. Its findings feed into and expand the scope of all subsequent phases.

**Phase 0 is not just about checking the items listed below.** It is about building a complete mental model of the codebase — understanding every module's role, every variable's lifecycle, every function's callers and callees. If you identify a dependency, variable collision, or architecture issue that is NOT listed in the sections below, document it and classify it. The sections below define MINIMUM coverage.

**Phase 0 Gate:** Before proceeding to Phase 1, all Phase 0 findings must be documented and classified. Any P0 finding from Phase 0 (e.g., readonly variable collision preventing script launch) must be fixed before continuing, because it blocks all subsequent testing.

### 0.1 Sourcing Tree and Initialization Order
Map the complete sourcing tree: which script sources which, in what order
Trace the entry point initialization sequence step by step from first line to main()
Document which modules are loaded before others and why that order matters
Identify any modules that are conditionally sourced and under what conditions
Verify: does the main script (prepare-deployment.sh) set `readonly SCRIPT_DIR` before sourcing lib/*.sh?
Verify: do any lib/*.sh files re-assign SCRIPT_DIR when it's already readonly from the parent?
Verify: does lib/detect.sh, lib/deploy.sh, and lib/autoinstall.sh all have the `SCRIPT_DIR="${SCRIPT_DIR:-$(cd "$(dirname "$0")" && pwd)}"` pattern?
Verify: what happens when this defaults to the lib/ directory instead of the project root?
Check: does build-iso.sh also set `readonly SCRIPT_DIR` and source from `$LIB_DIR`?
Map: prepare-deployment.sh → colors.sh → logging.sh → tui.sh → dryrun.sh → retry.sh → verify.sh → rollback.sh → detect.sh → disk.sh → autoinstall.sh → bless.sh → deploy.sh → remote_mac.sh → revert.sh (conditionally: remote.sh)
Identify: which modules are conditionally sourced (remote.sh is `if [ -f ]`) and what breaks if they're absent

### 0.2 Variable Namespace Collision Map
List ALL `readonly` and `declare -r` declarations across every file
List ALL `export`'d variables and trace which modules consume them
Identify ALL shared variable names across modules (SCRIPT_DIR, LIB_DIR, ESP_NAME, ESP_SIZE, STORAGE_LAYOUT, NETWORK_TYPE, INTERNAL_DISK, APFS_CONTAINER, TARGET_DEVICE, DRY_RUN, AGENT_MODE, JSON_OUTPUT, CONFIRM_YES, OUTPUT_DIR, LOG_LEVEL, etc.)
For each shared variable: document which module owns it, which modules read it, and whether any module attempts to reassign it
Flag: any library that re-assigns a variable already declared `readonly` in a parent scope (e.g., SCRIPT_DIR in detect.sh, deploy.sh, autoinstall.sh when sourced from prepare-deployment.sh)
Verify: ESP_NAME is set as readonly in prepare-deployment.sh AND as a non-readonly default in disk.sh — is there a collision?
Verify: ESP_SIZE is set as readonly in prepare-deployment.sh AND as a default in disk.sh — same pattern

### 0.3 Function Namespace Map
List ALL function definitions across every .sh file
Identify any function name collisions across modules (e.g., are there any name collisions between lib/revert.sh and lib/rollback.sh?)
Identify any function that shadows a system command (e.g., `log` in logging.sh shadows `/usr/bin/log` on macOS)
Check: does `die()` in build-iso.sh conflict with `die()` from logging.sh?
Check: do `warn()`, `error()`, `log()` aliases in build-iso.sh conflict with logging.sh versions?

### 0.4 Guard Variable Audit
Check every lib/*.sh for a guard variable (e.g., _COLORS_SH_SOURCED, _LOGGING_SH_SOURCED, etc.)
List which modules have guards and which don't
Determine if any module can be double-sourced and what would break
Verify: if colors.sh is double-sourced, readonly RED/GREEN/etc. would fail — does the guard prevent this?
Verify: lib/retry.sh has a one-line guard — does it properly prevent re-execution of the readonly declarations?
Check: lib/tui.sh declares `readonly TUI_BACKEND`, `readonly TUI_HAS_GAUGE`, `readonly TUI_HAS_TAILBOX`, `readonly TUI_BACKTITLE` — what happens on double-source?
Check: guard pattern consistency — every lib file with a guard MUST use the check-before-set pattern: `[ "${_GUARD:-0}" -eq 1 ] && return 0` BEFORE `_GUARD=1`. A guard that only sets the variable (e.g., `_GUARD=1`) without the check allows double-sourcing which can fail on `readonly` re-declarations. Verify: `grep -L '&& return 0' lib/*.sh | xargs grep '_SOURCED=1\|_GUARD=1'` — any file that sets a guard variable but lacks the early-return check has a P2 bug.

### 0.5 Architecture Diagram
Produce a dependency diagram: main script → libs → sub-libs
Mark each edge with what is consumed (variables, functions)
Highlight circular dependencies or fragile ordering assumptions
Verify: rollback.sh depends on retry.sh and dryrun.sh — is this documented?
Verify: deploy.sh sources nearly everything — is the order significant?
Check: does build-iso.sh source a subset of libs? Which ones? Does it miss any it needs?

### 0.6 Bug Class Taxonomy and Custom Check Generation

**Purpose:** Phase 0 doesn't just model what IS — it must model what GOES WRONG. Every bug found (whether during review cycles OR manually between them) represents a **bug class** that may have additional instances. Phase 0 must extract the general pattern from each past bug and generate custom checks for the current cycle.

**Critical: Catalog PATTERNS, not instances.** Bug class entries must NEVER reference specific line numbers, function names, file paths, or version numbers. These details are transient — the pattern is permanent. A good bug class description applies equally to ANY codebase with the same architectural structure, not just this one at a specific point in time.

**CRITICAL: Include bugs found outside review cycles.** Many bugs are found by manual testing, user reports, or ad-hoc investigation between formal review cycles. These bugs are EQUALLY valuable for pattern extraction — they represent blind spots the checklists missed. Before each review cycle:

1. Review `git log --oneline` since the last review cycle for commits containing `fix`, `Fix`, or `bug`
2. Review CHANGELOG.md entries since the last review cycle
3. Ask the user: "Were any bugs found manually since the last review cycle?"
4. For EACH bug found (whether during review or outside it), extract the bug class

**Bug class extraction process:**
For EACH bug found since the last review cycle:

1. **Generalize the bug**: Strip ALL instance-specific details. What is the abstract pattern?
2. **Identify the class**: What structural condition enables this pattern? Where else could it occur?
3. **Generate a check**: Write a concrete, executable check that finds ALL instances of this class in the CURRENT codebase (not the historical one)
4. **Add to the appropriate phase**: Insert the check with a `[BUG-CLASS]` tag

**Bug class catalog (accrues across review cycles — never remove entries):**

| Bug Class | Abstract Pattern | Custom Check |
|-----------|-----------------|--------------|
| Output channel contamination | A module writes to stdout for both informational output AND return values; callers capturing via `$(...)` receive both channels mixed together | Verify all logging/diagnostic output goes to stderr; verify no function uses stdout for both logging and return values |
| Confirmation-before-collection | A summary/confirmation is called from a function that executes before the data it summarizes has been collected | Trace call sequence: summary/confirm must appear AFTER all data-gathering functions, never inside a function called before data collection completes |
| Placeholder-as-set | Prompt skip conditions treat template/default values as "already configured" because the value is non-empty but not user-provided | Check all "skip if set" conditions also check for known placeholder patterns, not just emptiness |
| Widget column mismatch | UI widget item arrays have wrong column count for the backend (e.g., trailing empty column) | Verify each widget backend path constructs item arrays with exactly the column count the widget expects |
| Unsafe variable indirection | Variable indirection via eval without validating the variable name contains only safe characters | Audit all eval calls: any that interpolate a variable name must validate it against `^[a-zA-Z_][a-zA-Z0-9_]*$` |
| Duplicate definition overwrite | Two definitions of the same name in the same file where the second silently overwrites the first | Check for duplicate function/variable definitions within single files |
| Eval-with-user-input | `eval` is used with a string containing user-controllable input (filenames, config values) without proper quoting or sanitization | Audit all `eval` calls: verify the expanded string does not incorporate unsanitized external input; prefer global-variable patterns over `eval` for return values |
| Command substitution with TUI | TUI result-returning functions are called inside `$(...)` which creates a subshell that breaks dialog/whiptail on macOS (hangs) and mixes stdout channels | Grep for `$(tui_menu`, `$(tui_input`, etc. — all result-returning TUI functions must use `_TUI_RESULT` global, never stdout capture |
| Dry-run journal skip | In dry-run mode, phase-tracking journal entries are not recorded, so journal-based skip-on-resume logic cannot work after dry-run | Verify dry-run paths either record journal phases with a dry-run marker or explicitly document that dry-run state is not resumable |

**Custom check generation template:**
```
Bug Class: [abstract name — NO line numbers, NO function names, NO file paths]
Abstract Pattern: [general description that could apply to any codebase with this structure]
How to Detect: [concrete methodology to find ALL instances in current codebase]
Phase: [which phase this check belongs in]
Expected Severity: [P0/P1/P2 if found]
```

**Phase 0 Gate Addition:** Before proceeding to Phase 1, ALL bugs found since the last review cycle (both during-review AND manual/outside) must have their bug class extracted, generalized, and custom checks inserted into the appropriate phase sections. This ensures each review cycle is STRICTLY MORE COMPREHENSIVE than the last — institutional knowledge of failure patterns compounds over time.

---

## PHASE 1: STATIC CODE ANALYSIS

Before running static analysis, create a `.shellcheckrc` file:
```
source-path=lib/
# Document intentional patterns that warrant ignores
# SC1090/SC1091: Sourced files with variable paths — we use source "$LIB_DIR/foo.sh"
# SC2034: Unused variables — some are used by sourced scripts
```

All findings from this phase must be classified by severity:
- **P0 (Fatal):** Script won't start, crashes immediately, data loss risk
- **P1 (Critical):** Core feature broken, wrong behavior, silent data corruption
- **P2 (Major):** Error path mishandled, missing validation, incorrect fallback
- **P3 (Minor):** Style, formatting, documentation gaps, non-idiomatic patterns

### 1.1 Syntax and Structure Validation
Run syntax checks on ALL shell scripts: `bash -n` for each .sh file
Run ShellCheck with full severity coverage: `shellcheck -x --severity=warning` on ALL .sh files including:
- prepare-deployment.sh
- build-iso.sh (in lib/ directory)
- Every file in lib/*.sh
- Every file in tests/*.sh and tests/vm/*.sh
- macpro-monitor/start.sh, stop.sh, reset.sh

Note: ShellCheck cannot follow dynamic `source "$LIB_DIR/foo.sh"` paths. Use `source-path=lib/` in .shellcheckrc and add `# shellcheck source=lib/foo.sh` directives where needed. SC1090/SC1091 warnings for sourced libs should be verified manually, not suppressed blindly.

Run formatting validation: `shfmt -i 2 -ci -bn -d`
Run Node.js syntax validation on macpro-monitor/server.js (`node --check`)
Document EVERY warning, error, and suggestion — do not filter
Classify each finding as P0/P1/P2/P3

### 1.1.1 TUI Module Raw Fallback Audit
lib/tui.sh contains multi-backend TUI functions (dialog, whiptail, raw). The raw fallback is the most error-prone — it is the code path executed when neither dialog nor whiptail is available. Copy-paste contamination between function fallbacks has caused P1 bugs. For each function, verify:

**Contamination check** — grep for function-crossing patterns that should NOT appear outside their respective fallbacks:
- `grep -n "Proceed\?" lib/tui.sh` — "Proceed?" should ONLY appear in tui_confirm raw fallback
- `grep -n "yes/no" lib/tui.sh` — "yes/no" prompt should ONLY appear in tui_confirm raw fallback
- `grep -n "Press Enter" lib/tui.sh` — "Press Enter to continue" should ONLY appear in tui_msgbox raw fallback
- `grep -n '\$message' lib/tui.sh` — `$message` is a tui_confirm parameter; `$description` is a tui_menu parameter; verify each usage is in the correct function

**Variable scope check** — for each raw fallback branch (else branch after dialog/whiptail checks):
- tui_menu: uses `$description` (NOT `$message`)
- tui_confirm: uses `$message` (NOT `$description`)
- tui_input: uses `$label`, `$default_value`
- tui_password: uses `$label`, reads with `IFS= read -rs`
- tui_checklist: uses `$description`, reads from `/dev/tty`
- tui_msgbox: uses `$message`
- tui_progress: output-only, no input
- tui_tailbox: uses `$title`, `$filepath`

**/dev/tty consistency check** — verify ALL raw input functions read from /dev/tty:
- `grep -n 'read.*< /dev/tty' lib/tui.sh` — should find exactly 6 matches (tui_menu, tui_confirm, tui_msgbox, tui_input, tui_password, tui_checklist)
- tui_progress and tui_tailbox are output-only and should NOT read from /dev/tty
- Any function reading from stdin (`read -rp`) without `< /dev/tty` is a P1 bug — stdin is consumed by heredoc/pipe in scripted contexts

**Return type check** — verify raw fallbacks return expected types:
- tui_menu returns: tag string (e.g., "existing", "generate", "skip")
- tui_confirm returns: 0 (yes) or 1 (no)
- tui_input returns: user-entered string
- tui_password returns: user-entered password
- tui_checklist returns: space-separated tag string
- tui_msgbox returns: nothing (displays and exits)

**set -u compatibility check** — source lib/tui.sh with `set -u` active, call each function with test args. Any "unbound variable" error indicates a missing local declaration or wrong parameter name in a fallback branch.

**Non-interactive context audit (systematic):**
Search for ALL commands that may prompt for interactive input outside of TUI functions: `grep -rn 'read.*-p\|openssl.*enc\|ssh-keygen\|sudo.*-S\|passwd\|chpasswd' prepare-deployment.sh lib/*.sh`
For EACH hit:
1. Can this command be reached in agent mode (--agent) where stdin is not a TTY?
2. If yes, does it have a non-interactive fallback (e.g., `--pass` flag, `-N ""` flag, stdin pipe)?
3. Will it hang indefinitely waiting for input that never comes?
This is a COMPLETE audit — a command that hangs in agent mode is a P0 bug.

### 1.1.2 TUI Dialog Subshell and Trap Audit

**Dialog command substitution audit (P0 — hangs on macOS):**
Dialog (`dialog`, `whiptail`) CANNOT run inside `$(...)` command substitution on macOS. The `$(...)` creates a subshell where dialog's ncurses cannot properly access `/dev/tty` for terminal rendering and keyboard input, causing an invisible hang.

- `grep -n '\$(tui_menu\|\$(tui_input\|\$(tui_password\|\$(tui_checklist' prepare-deployment.sh lib/*.sh` — ALL must be zero matches
- ALL TUI result-returning functions (tui_menu, tui_input, tui_password, tui_checklist, tui_checkbox, tui_grid_checklist) MUST use a global result variable (e.g., `_TUI_RESULT`) instead of `echo`/stdout
- Callers MUST use the pattern `tui_X ... || return 1; VAR="$_TUI_RESULT"` NOT `VAR=$(tui_X ...)`
- tui_confirm and tui_msgbox are exempt — they return exit codes, not values, so `$(...)` is never used with them

**EXIT trap pollution audit (P1 — prevents cleanup):**
TUI functions that set `trap ... EXIT` inside their body overwrite the main script's EXIT trap. After the function returns, the main script's cleanup trap is gone.

- `grep -n 'trap.*EXIT' lib/tui.sh` — must be zero matches (TUI functions must NOT set EXIT traps)
- `grep -n 'trap.*EXIT' prepare-deployment.sh` — verify the main script's EXIT trap is intact and not overwritten
- TUI functions that need temp file cleanup must use manual `rm -f "$tmpfile"` at every exit point (success and failure), NOT EXIT traps
- The main script's EXIT trap (`trap 'cleanup_on_error' EXIT`) must remain active for the entire script lifecycle

**Dialog/whiptail menu column audit (P1 — duplicate/blank entries):**
- `dialog --menu` items are pairs: `tag label` (2 columns per item)
- `dialog --checklist` items are triples: `tag label state` (3 columns per item)
- `whiptail --radiolist` items are triples: `tag label ON/OFF` (3 columns per item)
- Verify each TUI function constructs its items array with the correct column count for the backend:
  - tui_menu dialog path: `items+=(tag label)` — exactly 2 elements per item
  - tui_menu whiptail path: `items+=(tag label state)` — exactly 3 elements per item
  - tui_checklist dialog path: `items+=(tag label state)` — exactly 3 elements per item
  - tui_checklist whiptail path: `items+=(tag label state)` — exactly 3 elements per item
- A trailing empty column (e.g., `items+=(tag label "")`) in menu mode causes dialog to render blank/duplicate entries — this is a P1 bug

### 1.1.3 Logging Output Destination Audit

**Log-to-stdout contamination audit (P0 — corrupts captured return values):**
Any function that returns a value via `echo` (stdout) AND calls a log function has a data corruption bug when captured via `$(...)`. The `$(...)` captures ALL stdout — both the intended return value AND any log messages written to stdout. This produces output like `[INFO] message real_return_value` instead of `real_return_value`.

- `grep -n 'printf\|echo' lib/logging.sh` — verify ALL terminal output goes to stderr (`>&2`), never stdout
- Specifically check `_log_to_terminal()`: it MUST write to stderr. If it uses bare `printf` or `echo` without `>&2`, any `$(function_that_logs)` capture will be contaminated
- `grep -rn 'log_info\|log_warn\|log_error\|log_debug\|log_fatal' lib/discover.sh lib/detect.sh lib/disk.sh` — any function in these files that also uses `echo` for return values IS a contamination bug if logging goes to stdout
- General rule: **logging module output MUST go to stderr.** Functions return values via `echo` (stdout). These two channels must never mix.

**$(...) capture audit (P0 — find all contamination-susceptible calls):**
- `grep -rn '$(' lib/discover.sh lib/detect.sh lib/disk.sh` — any `$(command)` where `command` calls both `echo` and `log_*` is a contamination candidate
- For each candidate, verify that logging goes to stderr (not stdout) so `$(...)` only captures `echo` output
- Also check: do any functions use `echo` for BOTH logging AND return values? (e.g., `echo "status: ok"; echo "$result"` — the first echo pollutes the capture)

### 1.2 Variable and Scope Analysis
**This section builds on Phase 0.2 (Variable Namespace Collision Map).** If Phase 0.2 found no collisions, this section focuses on the remaining checks: usage safety, input handling, and scope correctness. Do not re-audit collision findings from Phase 0.2.

Audit ALL variable declarations (local, readonly, declare, export)
Phase 0.2 already mapped collisions and readonly/export conflicts — skip those here
Trace variable scope throughout the codebase — especially across source boundaries
Check for variables that should be local but aren't
Specific checks:
- CHECK: All `eval "$varname=..."` patterns in disk.sh, deploy.sh — are they safe with `set -u`? (Phase 0.2 already identified which eval calls exist; this check verifies they validate their input)
- CHECK: `parse_conf()` reads deploy.conf line-by-line — what happens with empty values or values containing `=`?
- CHECK: `save_config()` writes deploy.conf — does it properly quote values containing spaces or special chars?

**eval and dynamic dispatch audit (systematic):**
Search for ALL `eval` calls across the entire codebase: `grep -rn 'eval ' prepare-deployment.sh lib/*.sh`
For EACH eval call found:
1. What values can reach the eval string?
2. Is every possible value validated or sanitized?
3. Could user input reach this eval without validation?
This is a COMPLETE audit — do not stop at known eval sites.

### 1.3 Dependency Graph Mapping
Map all function calls and their dependencies
Identify all external command dependencies including:
- macOS-specific: diskutil, bless, sgdisk, newfs_msdos, tmutil, csrutil, fdesetup, sw_vers, security
- Linux-specific (for remote.sh): ssh, dkms, apt-get, dpkg, efibootmgr, systemctl, ufw, grub-*
- Cross-platform: xorriso, python3, curl, dd, comm, stat
- Note which commands run on macOS vs. Linux (e.g., diskutil is macOS-only; dkms is Linux-only)
Check that all sourced files exist and are valid
Document the execution order and call hierarchy
Identify circular dependencies
Verify that every function referenced in a case/esac or callback actually exists
Specific checks:
- VERIFY: All functions referenced in prepare-deployment.sh's case statements (deploy_internal_partition, deploy_usb, deploy_manual, deploy_vm_test) are defined in lib/deploy.sh
- VERIFY: All functions referenced in _AGENT_OPERATIONS (remote_get_info, remote_kernel_status, etc.) are defined in lib/remote.sh
- VERIFY: All functions referenced in rollback PHASES_* constants are defined
- CHECK: build-iso.sh defines its own log/warn/error/die — are these compatible with logging.sh versions?

### 1.4 Control Flow Analysis
Trace all execution paths including error paths
Identify unreachable code
Check all exit paths have proper cleanup
Verify all conditionals cover their intended cases
Check loop termination conditions
Trace what happens when `set -e` encounters a failing command in a pipeline, subshell, or conditional
Identify any `|| true` or `|| :` that might be swallowing real errors

**Pattern-based checks (specific):**
These checks identify error-handling patterns that are common sources of bugs. For exhaustive path tracing, see Phase 1.7 which covers ALL execution paths from entry to exit. This section focuses on control flow PATTERNS; Phase 1.7 focuses on path COVERAGE.

- TRACE: What happens when deploy_internal_partition fails at phase _phase_generate_config? Does cleanup_on_error get called? Does the journal get destroyed?
- TRACE: What happens when build-iso.sh fails at step [4/5]? Does the staging directory get cleaned up? Does the trap fire?
- CHECK: The `run_phased` function in rollback.sh — when `is_dry_run` is true, it skips the phase function entirely. Does this mean journal phases are never recorded in dry-run mode? Is this correct?
- CHECK: In detect.sh, `select_usb_device` uses `eval` to set a variable by name — is this safe with user-controlled input?
- CHECK: In autoinstall.sh, `generate_autoinstall()` uses `sed -i` with both GNU and BSD syntax (`sed -i ... 2>/dev/null || sed -i '' ...`) — is this pattern correct for both platforms?
- CHECK: The `journal_set` function uses `eval` to read variable values — is the key validation regex sufficient to prevent injection (`^[a-zA-Z_][a-zA-Z0-9_]*$`)?
- CHECK: `retry_diskutil` checks stderr for "Resource busy" — are there other transient diskutil errors that should trigger retries?
- CHECK: `retry_xorriso` retries on I/O errors — does it properly clean up partial extraction directories on failure?

### 1.5 Line-by-Line Code Review
Review EVERY line of EVERY shell script for correctness. Do not skip sections assuming they work.

**This is the most critical phase for discovering UNKNOWN bugs.** The checklists in other sections identify common patterns and known failure modes, but ONLY line-by-line reading catches subtle logic errors, missing error handling, off-by-one errors, and incorrect assumptions. The reviewer MUST read every line with fresh eyes, asking "what if this fails?" and "what if the input is unexpected?" for EVERY line — not just the lines that seem suspicious.

**Structured methodology — for each file, process ALL lines:**

1. **Read the file completely** before marking any finding. Context matters — a line that looks wrong in isolation may be correct in context.
2. **For each line, verify the checklist below.** Mark each line as: PASS, FINDING, or UNCERTAIN (needs deeper analysis).
3. **For FINDINGs**, classify severity and document: line number, what's wrong, what it should be, impact.
4. **For UNCERTAIN lines**, trace the execution context to resolve uncertainty before proceeding.
5. **After completing a file**, re-read every FINDING to confirm it's still valid in the full-file context.

**Per-line verification checklist:**

- Is the logic correct for the platform it runs on? (macOS vs. Ubuntu/Subiquity installer vs. Ubuntu target)
- Are all variable expansions properly quoted? (Every `"$VAR"` must be quoted, every unquoted `$VAR` is a finding)
- Are all conditional expressions correct? (`[[ ]]` for bash, `[ ]` only for POSIX contexts like autoinstall YAML `- |` blocks)
- Are exit codes properly checked? (No silent failures in `set -e` context)
- Are pipe failures caught? (`set -o pipefail` is set — verify pipe chains propagate failures)
- Is the line reachable? (not after unconditional exit/return/die)
- Does the line have side effects? If yes, are they expected and cleaned up on failure?
- Does the line depend on a variable set in a different scope? If yes, is that variable guaranteed to be set?
- Does the line correctly handle empty/missing values? (especially under `set -u`)
- If the line is in a conditional block, does it handle the NEGATED condition correctly? (errors in else/unexpected branches)
- If the line uses `eval`, `source`, or dynamic invocation, is every possible input safe?
- If the line calls an external command, does the command exist on the target platform?

Platform-specific line-by-line checks:
- **macOS (host) scripts** (prepare-deployment.sh, build-iso.sh, lib/disk.sh, lib/bless.sh, lib/detect.sh, lib/revert.sh): Use BSD tool semantics. `stat -f%z`, `diskutil`, `bless`, `newfs_msdos`, `hdiutil`
- **autoinstall YAML `- |` blocks** (lib/autoinstall.sh embedded content, generated autoinstall.yaml): Run via `sh -c` in Subiquity installer — POSIX ONLY, no `[[ ]]`, no arrays, no `<<<`. Variables are NOT shared between different `- |` blocks
- **Remote management scripts** (lib/remote.sh): SSH commands execute on the target Ubuntu system. `apt`, `dkms`, `systemctl`, `efibootmgr` commands
- **Remote deployment scripts** (lib/remote_mac.sh): Shell commands execute on macOS target via SSH when DEPLOY_MODE=remote, or locally when DEPLOY_MODE=local. All macOS-specific commands MUST be routed through `remote_mac_exec` or `remote_mac_sudo`
- **Node.js** (macpro-monitor/server.js): Node.js semantics, Promises, HTTP server

**FRESH EYES PRINCIPLE:** After completing the per-line checklist for a file, re-read the entire file WITHOUT the checklist and ask: "What would break this? What assumptions does this code make? What happens if those assumptions are violated?" The checklist catches known patterns. Fresh-eyes reading catches unknown bugs that no checklist can anticipate. Do not limit your review to confirming checklist items pass.

### 1.6 Generated Artifact Validation
Validate every `autoinstall.yaml` and `autoinstall-vm.yaml` variant (method × storage × network combinations) parses as valid YAML:
- `python3 -c "import yaml; yaml.safe_load(open('autoinstall.yaml'))"`
- Validate against `lib/autoinstall-schema.json` using a JSON Schema validator
- Verify all `__PLACEHOLDER__` tokens are replaced (no stray `__` in output)
- Validate the Python heredoc in `generate_dualboard_storage` is syntactically correct Python
- Verify partition type GUID values are lowercase hex (curtin normalizes to lowercase; uppercase causes `preserve: true` verification mismatches)
- Verify each `- |` block redefines KVER, ABI_VER, LOG, WHURL (POSIX constraint: variables not shared between blocks)
- Verify `netplan generate --root-dir /tmp/test-root` succeeds against generated netplan YAML (mock chroot)

**YAML structure boundary validation (systematic):**
For each variant of autoinstall.yaml (method × storage × network), verify YAML structure boundaries are correct:
- Regex/string replacements produce properly delimited YAML sections — adjacent keys are on separate lines, not merged onto the same line
- Conditional sections (ethernet vs wifi, dual-boot vs full-disk storage) produce valid YAML when included AND when excluded
- Template placeholders that expand to multi-line content (early-commands, late-commands) preserve proper indentation and YAML block scalar syntax
- After all replacements, the YAML has no lines containing two YAML keys (e.g., `path: / late-commands:`)
- After all replacements, the YAML has no missing newlines between sections

Verify autoinstall YAML complies with Subiquity's actual schema — check against https://ubuntu.com/server/docs/install/autoinstall-reference:
  - `network:` section CANNOT contain `wifis:` (networkd renderer does not support `match:` for wifis; Ubuntu Bug #2073155)
  - `early-commands` and `late-commands` run via `sh -c` — verify POSIX-only syntax
  - `storage:` section with `preserve: true` must have lowercase GUID type codes
  - `reporting:` section must use `{progress, stage, status, message}` fields, NOT `{name, event_type, origin}` (those trigger built-in Subiquity handler)

### 1.7 Systematic Execution Path Walkthrough

This section requires tracing EVERY possible execution path through each script, from entry point to exit. The goal is to discover logic errors, missing error handling, unreachable code, and incorrect branching — not just verify known patterns.

**Every script must have ALL its execution paths walked. This is not optional.** The walkthrough must be EXHAUSTIVE — trace every branch of every conditional, every case pattern, every loop iteraton count (0, 1, many), and every error exit. Do not skip paths that seem "obvious" or "unlikely" — bugs hide in edge cases.

**Beyond the specific paths listed below, the reviewer must identify and trace ANY execution path that is not explicitly listed.** If a function has 5 branches but only 3 are traced below, the reviewer must still trace the remaining 2. The specific paths listed are MINIMUM coverage, not maximum.

#### 1.7.1 Path Enumeration Methodology

For each script, enumerate ALL possible execution paths:

1. **Identify all entry points**: main(), flag-parsing, --agent mode, --revert, --operation
2. **Identify all branch points**: if/elif/else, case/esac, loop conditions, short-circuit operators (&&, ||), function return values, error exits
3. **For each branch point, enumerate all outcomes**: true/false for if, each case pattern, loop-iteration vs loop-skip, success vs failure for function calls
4. **Trace each complete path from entry to exit**: document the sequence of function calls, variable assignments, and side effects
5. **Count total paths**: if impractical (combinatorial explosion), prioritize paths that involve destructive operations or user input

**EXHAUSTIVENESS REQUIREMENT:** The paths listed in sections 1.7.2–1.7.6 are a STARTING POINT. The reviewer MUST also trace any paths NOT listed below — for example, new functions added since the last review, paths through error handling that branch unexpectedly, or combinations of flags that create novel execution orders. If a function has N branches that are not all traced below, trace the missing ones.

**Path trace template:**
```
Script: [filename]
Path ID: [P1, P2, ...]
Entry: [how this path is entered]
Branch decisions: [each branch point and which direction]
Function call sequence: [ordered list of functions called]
Side effects: [disk changes, file writes, network calls]
Exit: [exit code and cleanup performed]
Potential issues: [anything that looks wrong]
```

#### 1.7.2 prepare-deployment.sh Path Walkthrough

Trace ALL execution paths through prepare-deployment.sh:

**First-run paths (no existing deploy.conf):**
- Path: No config → "Configure new device?" → Yes → explore_environment → menu_deploy_select → prompt_config → _run_deploy_method → exit
- Path: No config → "Configure new device?" → No → exit
- Path: No config → "Configure new device?" → Cancel at any sub-prompt → exit without partial execution

**Returning-user paths (existing deploy.conf):**
- Path: Config exists → main menu → Deploy → menu_deploy → [method selection + execution] → return to menu
- Path: Config exists → main menu → Manage → run_manage_mode → [submenu loop] → return to main menu
- Path: Config exists → main menu → Revert → handle_revert_flag → exit
- Path: Config exists → main menu → Exit → break

**Agent mode paths:**
- Path: --agent --method N --storage N --network N → skip flow prompts → _run_deploy_method → exit
- Path: --agent --operation X → skip deploy entirely → run agent operation → exit
- Path: --agent --build-iso → run ISO build → exit
- Path: --agent --revert → handle_revert_flag → exit

**Error paths:**
- Path: Missing required dependency → die at startup
- Path: Invalid --method value → agent_error E_AGENT_PARAM → exit
- Path: --operation with missing --host → agent_error → exit

**For each path, verify:**
- The path terminates (no infinite loops except intentional menu loops)
- The exit code is correct for the outcome
- No destructive operation executes without user confirmation (except in --yes mode)
- No partial state is left behind on failure (trap/cleanup runs)
- The path does NOT accidentally execute code from a different path (fallthrough, missing break/return/exit)

#### 1.7.3 lib/deploy.sh Path Walkthrough

Trace all deployment method paths:

**Method 1 (Internal ESP):**
- Path: analyze_disk_layout → shrink_apfs_if_needed → create_esp_partition → extract_iso_to_esp → copy_packages_to_esp → generate_config_on_esp → verify_bless → done
- For each sub-path: trace what happens on failure (journal rollback, cleanup, error reporting)

**Method 2 (USB):**
- Path: detect_usb → partition_usb → extract_iso_usb → copy_packages_usb → generate_config_usb → verify_usb → done

**Method 3 (Manual):**
- Path: detect_iso → detect_usb → create_standard_usb → done

**Method 4 (VM):**
- Path: check_vbox → find_iso → build_iso → create_vm → start_monitor → done

**For EACH method, trace the journal phase progression and verify:**
- Phase markers are written at the correct time (BEFORE the phase starts, not after)
- Phase completion is recorded AFTER the phase succeeds
- On failure, the correct rollback function is called for the current phase
- After rollback, the system is in a recoverable state

#### 1.7.4 lib/remote.sh Path Walkthrough

Trace all manage mode operation paths:

- sysinfo → remote_get_info → format and display
- kernel_status → remote_kernel_status → display
- kernel_pin → tui_confirm → remote_kernel_repin → verify
- kernel_unpin → tui_confirm → remote_kernel_unpin → verify
- kernel_update → 7-phase interactive flow with rollback at each phase
- security_update → remote_non_kernel_update → verify
- health_check → remote_health_check → display
- driver_status → remote_driver_status → display
- driver_rebuild → tui_confirm → remote_driver_rebuild → verify
- erase_macos → tui_confirm → remote_erase_macos → verify
- reboot → tui_confirm → remote_reboot → wait + verify
- boot_macos → tui_confirm → remote_boot_macos → verify

**For kernel_update specifically:**
- Trace all 7 phases in order
- For each phase, trace: success path → next phase, failure path → rollback
- Phase 6 (reboot): trace what happens if SSH never comes back (timeout handling)
- Phase 7 (re-lock): trace what happens if re-lock fails partially

#### 1.7.4b lib/remote_mac.sh Path Walkthrough

Trace all deployment mode routing paths:

- DEPLOY_MODE=local: remote_mac_exec → direct local execution (pass-through)
- DEPLOY_MODE=local: remote_mac_sudo → direct local execution (assumes already root)
- DEPLOY_MODE=remote: remote_mac_exec → ssh $TARGET_HOST "$*"
- DEPLOY_MODE=remote: remote_mac_sudo → ssh $TARGET_HOST "sudo -S -p '' $*" (with REMOTE_SUDO_PASSWORD via stdin)
- DEPLOY_MODE=remote: remote_mac_cp → scp $SSH_OPTS $src $host:$dst
- DEPLOY_MODE=remote: remote_mac_cp_dir → scp -r $SSH_OPTS $src $host:$dst
- DEPLOY_MODE=remote: remote_mac_file_exists → ssh $TARGET_HOST "test -f '$path'"
- DEPLOY_MODE=remote: remote_mac_dir_exists → ssh $TARGET_HOST "test -d '$path'"
- DEPLOY_MODE=remote: remote_mac_mkdir → ssh $TARGET_HOST "mkdir -p '$path'"
- DEPLOY_MODE=remote: remote_mac_rm → ssh $TARGET_HOST "rm -f '$path'"
- remote_mac_preflight: SSH test → command availability check → sudo access check

**Verify:**
- All macOS-specific commands (diskutil, sgdisk, bless, xorriso, newfs_msdos, sw_vers, systemsetup, ipconfig) are wrapped with remote_mac_exec or remote_mac_sudo in deployment modules (disk.sh, bless.sh, detect.sh, deploy.sh, revert.sh)
- File operations (copying packages, configs, ISO) use remote_mac_cp/remote_mac_cp_dir in remote mode
- Path existence checks use remote_mac_file_exists/remote_mac_dir_exists in remote mode
- remote_mac_preflight is called before any remote deployment operation

#### 1.7.5 build-iso.sh Path Walkthrough

- Path: Check prerequisites → extract ISO → overlay custom files → rebuild ISO → cleanup staging
- For each step: trace failure handling (trap cleanup, staging directory removal)
- Verify: successful build removes staging directory (not just on failure)

#### 1.7.6 Cross-Script Path Analysis

**prepare-deployment.sh → lib/build-iso.sh subprocess:**
- How is build-iso.sh invoked? (subprocess vs sourced)
- What environment variables are passed?
- What exit codes are expected and how are they handled?

**prepare-deployment.sh → lib/remote.sh via SSH:**
- Each remote function runs in a separate SSH session
- Verify: SSH connection timeout is handled at every call site
- Verify: SSH failure mid-operation leaves the target in a recoverable state

**prepare-deployment.sh → lib/remote_mac.sh routing:**
- In DEPLOY_MODE=local: all commands run locally (pass-through)
- In DEPLOY_MODE=remote: all macOS commands run via SSH on TARGET_HOST
- Verify: every `diskutil`, `sgdisk`, `bless`, `xorriso`, `newfs_msdos`, `sw_vers`, `systemsetup`, `bless --info` call is wrapped with `remote_mac_exec` or `remote_mac_sudo`
- Verify: file operations use `remote_mac_cp`, `remote_mac_cp_dir`, `remote_mac_file_exists`, `remote_mac_dir_exists`, `remote_mac_mkdir`, `remote_mac_rm`
- Verify: `remote_mac_preflight` is called before any remote deployment
- Verify: root/sudo check skipped when DEPLOY_MODE=remote (no local sudo needed)
- Verify: ISO transfer to target uses SCP (`remote_mac_cp`) then remote xorriso extraction
- Verify: configuration generated locally, validated locally, then SCP'd to target

---

## PHASE 2: FUNCTIONAL BEHAVIOR TESTING

**Beyond the listed tests:** The test cases in sections 2.1–2.16 cover specific scenarios, but the reviewer MUST also think about what is NOT listed. For each module, consider: "What happens with empty input? What happens with maximum-length input? What happens when a prerequisite fails silently? What happens when two modules interact in an unexpected way?" Design ADDITIONAL test cases beyond those listed for any scenario that seems risky.

### 2.1 Mode and Flag Testing
Test EVERY command-line flag in prepare-deployment.sh:
- --dry-run, --verbose, --agent, --yes, --json
- --method (1|2|3|4), --storage (1|2), --network (1|2)
- --deploy-mode (local|remote), --target-host, --remote-password
- --host, --operation, --wifi-ssid, --wifi-password
- --webhook-host, --webhook-port
- --username, --hostname, --vm, --revert, --help

Test --flag=value syntax for all applicable flags (--method=1, --storage=2, etc.)
Test invalid flag values: --method 5, --storage 3, --network 0
Test missing required arguments: --method without value, --operation without value
Test --help output matches actual flag implementation
Test --revert flag standalone (should work without other flags)
Test --build-iso flag (agent mode only)
Verify exit codes match documentation (0=success, 1=general, 2=usage, etc.)
Test build-iso.sh flags: --vm flag for VM mode, default behavior for production mode

### 2.2 Execution Mode Testing
Test dry-run/simulation modes for EVERY deployment method:
- --agent --dry-run --method 1 --storage 1 --network 1 --yes --json (internal partition)
- --agent --dry-run --method 2 --storage 1 --network 1 --yes --json (USB)
- --agent --dry-run --method 3 (manual)
- --agent --dry-run --method 4 --vm (VM test)

Verify dry-run produces ZERO side effects — audit every code path to ensure no destructive command executes when DRY_RUN=1
Verify dry-run exits with code $E_DRY_RUN_OK (11)
Check specifically: does `dry_run_exec` wrap ALL destructive commands in lib/deploy.sh, lib/disk.sh, lib/bless.sh, lib/revert.sh?
Check specifically: does `dry_run_callback` properly fall through to the real command when NOT in dry-run?
Verify `dryrun.sh` guard variable prevents double-sourcing
Test verbose/quiet modes (VERBOSE=1, LOG_LEVEL overrides)
Test agent mode with --agent flag
Test --agent --yes confirms destructive operations automatically
Test --agent WITHOUT --yes denies destructive operations (CONFIRM_YES=0)
Test --json flag produces valid JSON output (validate with `python3 -m json.tool`)
Test TUI fallback when dialog/whiptail are unavailable (TUI_BACKEND="raw")

### 2.3 Normal Execution Path Testing
Execute all primary workflows that can be safely executed:
- prepare-deployment.sh --help
- prepare-deployment.sh --dry-run --agent --method 1 --storage 1 --network 1 --yes --json
- prepare-deployment.sh --dry-run --agent --method 2 --storage 2 --network 2 --yes --json
- prepare-deployment.sh --agent --build-iso --json
- prepare-deployment.sh --agent --operation kernel_status --host macpro-linux --json

Test with valid inputs across boundary conditions
Test file operations (create, read, modify, delete) where safe
Test network operations (webhook server start/stop)
Test process execution and subprocess handling
Test config file parsing: deploy.conf with all keys, empty values, missing file fallback to deploy.conf.example
Test config file encryption modes: plaintext, aes256, keychain
Test save_config and encrypt_config round-trip

### 2.4 Error Path Testing
Test with missing required arguments (--method without value)
Test with invalid input types (--method foo, --storage bar)
Test with missing/invalid file paths (nonexistent ISO, missing prereqs/ directory)
Test with insufficient permissions (running without sudo when DEPLOY_MODE=local)
Test remote mode without SSH connectivity (DEPLOY_MODE=remote with unreachable TARGET_HOST)
Test remote mode with missing prerequisites on target (xorriso, sgdisk, etc. not installed on Mac Pro)
Test remote mode with incorrect sudo password (REMOTE_SUDO_PASSWORD wrong)
Test resource exhaustion scenarios (disk full simulation, large ISO)
Test network failures and timeouts (unreachable webhook host)
Test dependency failures:
- Missing xorriso, sgdisk, python3, comm, diskutil
- Wrong versions of dependencies
- Missing dialog and whiptail (TUI_BACKEND="raw")

Remote mode error paths:
- What happens when remote_mac_preflight can't SSH to target?
- What happens when remote_mac_sudo password fails mid-deployment?
- What happens when SCP transfer fails (disk full on target, permission denied)?
- What happens when target macOS tools are missing (no xorriso on Mac Pro)?
- What happens when remote_mac_exec returns non-zero mid-phase?
- What happens when DEPLOY_MODE=remote but TARGET_HOST is empty?
- What happens when DEPLOY_MODE=remote but no SSH key configured?

Verify error messages are clear and actionable
Verify exit codes match documented values (E_SUCCESS=0 through E_AGENT_DENIED=13)
Specific error path tests:
- What happens when analyze_disk_layout can't find the internal disk?
- What happens when detect_iso can't find any ISO file?
- What happens when select_usb_device finds no USB devices?
- What happens when APFS resize fails mid-operation?
- What happens when bless fails with SIP enabled (error 0xe00002e2)?
- What happens when xorriso extraction fails mid-stream?
- What happens when journal_init finds an existing incomplete state file?
- What happens when build-iso.sh can't find the base ISO?
- What happens when the DKMS patches series file lists a patch that doesn't exist?

### 2.5 Journal State Machine Testing
Test the rollback journal system (lib/rollback.sh) independently:
- Test `journal_init` with fresh state, existing state, and corrupted state files
- Test `journal_set` / `journal_set_phase` records correct timestamps and phase names
- Test `journal_is_complete` returns correct boolean for each known phase
- Test `journal_destroy` properly cleans up state file
- Test `rollback_from_journal` dispatches to correct rollback function for each phase
- Test that `DRY_RUN=1` prevents journal writes (or records them with dry-run marker)
- Verify atomic write pattern (temp file + mv) for crash safety
- Test `journal_set` with keys containing only valid characters (alphanumeric + underscore)
- Test `journal_set` rejects keys with special characters or spaces
- Test rollback_from_journal when state file exists but is empty or has zero phases recorded

### 2.6 Config Round-Trip Testing
Test the full deploy.conf lifecycle:
- Write deploy.conf with all keys → `parse_conf()` → verify all values match
- Write deploy.conf with special characters in values (spaces, quotes, `#`, `$`, `\`, newlines) → `parse_conf()` → verify values preserved
- Write deploy.conf → `encrypt_config()` → `parse_conf()` with encrypted values → verify decryption matches original
- Write deploy.conf with `ENCRYPTION=aes256` → verify password is decrypted at runtime, not stored in plaintext
- Write deploy.conf with `ENCRYPTION=keychain` → verify keychain lookup works and falls back gracefully on failure
- Write deploy.conf with multiple `SSH_KEY=` lines → verify all keys are collected in order
- Write deploy.conf with `SSH_KEYS_FILE=/path/to/file` → verify file is read and merged with `SSH_KEY=` entries
- Test `save_config()` preserves all keys, including ones not in the original file
- Test that `save_config()` sets mode 600 on the output file
- Test `parse_conf()` with `IFS='=' read -r key value` correctly handles values containing `=` (only splits on first `=`)
- Test `parse_conf()` with empty lines, comment lines, and lines with only whitespace

### 2.7 Network Connectivity Circuit Breaker Testing
Test the WiFi connectivity verification circuit breaker that prevents disk wipe when networking is non-functional:
- Verify deployment aborts (does NOT proceed to APFS resize / disk wipe) if WiFi check fails
- Verify 169.254.x.x link-local addresses are excluded from DHCP lease validation
- Verify the circuit breaker fires in the correct phase order (after driver load, before storage)
- Test what happens when WiFi interface detection times out (≥60s timeout for `wl` module initialization)
- Test what happens when WiFi interface is detected but DHCP fails
- Verify `grep -q "inet "` checks exclude `inet 169.254.` per project constraint
- Verify POSIX `if ! cmd1 || cmd2` correctly means `(!cmd1) || cmd2` — both failure modes caught

### 2.8 TUI Interactive Prompt Testing
Test TUI functions with actual interactive input (requires keyboard, cannot be piped). The raw TUI backend (`TUI_BACKEND=raw`) is the fallback when dialog/whiptail are unavailable and is the most bug-prone code path.

**Menu option selection test** (tui_menu raw fallback):
```
TUI_BACKEND=raw ./prepare-deployment.sh --help 2>&1 | head -5
# Should show: "=== Mac Pro 2013 Ubuntu Deployment ===" and "Select operation mode:"
# Should show numbered options: "1) Deploy", "2) Manage", "3) Revert Failed Deploy", "4) Exit"
# Should show: "Enter choice [1-4]:"
```
Test: `echo "1" | ./prepare-deployment.sh` — should enter Deploy flow (not crash, not show "yes/no" prompt)

**SSH Key Configuration menu test** (first-run config flow):
```
TUI_BACKEND=raw source lib/colors.sh lib/tui.sh 2>/dev/null
echo "existing" | tui_menu "SSH Key Configuration" "Choose how to provide SSH public key:" \
    "Provide existing key" "existing" "Generate new key" "generate" "Skip SSH setup" "skip"
# Should display: "=== SSH Key Configuration ===", description, "1) Provide existing key", "2) Generate new key", "3) Skip SSH setup"
# Should show: "Enter choice [1-3]:"
# Should return: "existing" (the tag value, NOT "yes" or "no")
```

**Checklist selection test** (tui_checklist raw fallback):
- Verify numbered options are displayed with checkbox state
- Verify comma-separated input works: `echo "1,3" | tui_checklist ...`
- Verify /dev/tty read (not stdin — test by running from script with piped input)

**Error path tests**:
- Enter invalid choice: `echo "99" | tui_menu ...` — should re-prompt with error
- Enter empty input on tui_input: should use default value
- Enter empty password on tui_password: should use empty value
- Keyboard interrupt (Ctrl-C) during tui_input/tui_password: should exit cleanly

### 2.9 Option Selection Flow Pathway Tracing
Every menu choice, checklist selection, confirmation, and input value flows through a chain: TUI function → caller → conditional logic → next step. Trace EVERY selection pathway end-to-end to verify the resolved behavior matches the user's expectation.

**Trace methodology**: For each TUI call site in prepare-deployment.sh, document: (1) which TUI function is called, (2) what the expected return type is, (3) how the return value is used, (4) what the final resolved behavior is.

**Deploy mode menu** (tui_menu → case dispatch):
```
Function: select_mode()
  → tui_menu returns tag: "deploy", "manage", "revert", "exit"
  → case "$choice" dispatches to: run_deploy_mode, run_manage_mode, handle_revert_flag, break
  Verify: user selects "Deploy" → enters deployment method submenu
  Verify: each tag maps to the correct function with correct arguments
  Verify: no tag value can cause fallthrough to an unintended branch
```

**Deployment method submenu** (tui_menu → collect + execute):
```
Function: menu_deploy() or menu_deploy_select() (depending on flow path)
  → tui_menu returns tag mapping to DEPLOY_METHOD (1-4)
  → sets STORAGE_LAYOUT, NETWORK_TYPE via further tui_menu calls
  → show_pre_execution_summary → tui_confirm (final confirmation)
  Verify: collect-only function does NOT execute deployment
  Verify: execute step runs exactly once after all collection is complete
  Verify: cancellation at any point returns without partial execution
```

**SSH key configuration flow** (tui_menu → conditional):
```
Function: configure_ssh_config() or prompt flow in prompt_config()
  → tui_menu returns tag: "existing", "generate", "skip"
  → case dispatches to: prompt_existing_key, prompt_generate_key, or skip warning
  Verify: "existing" → scans ~/.ssh/*.pub → if none found → warns user
  Verify: "generate" → prompts key type → runs ssh-keygen → saves to ~/.ssh/macpro_ubuntu_*
  Verify: "skip" → skips SSH setup → warns about console access
  Verify: all file writes under ~/.ssh/ are chowned to SUDO_USER
```

**Kernel management submenu** (tui_menu, tag → multi-step confirm):
```
Function: run_kernel_submenu() or equivalent in run_manage_mode()
  → tui_menu returns tag: "status", "pin", "unpin", "update", "security", "back"
  → case dispatches with confirm gates for destructive operations
  Verify: "pin" → shows tui_confirm → on yes → calls remote_kernel_repin
  Verify: "unpin" → shows tui_confirm → on yes → calls remote_kernel_unpin
  Verify: each destructive operation requires tui_confirm "yes"
  Verify: read-only operations (status) do NOT require confirmation
```

**WiFi/Driver submenu** (tui_menu, destructive with confirm):
```
Function: run_wifi_submenu() or equivalent in run_manage_mode()
  → tui_menu returns tag: "status", "rebuild", "back"
  → case dispatches: status (no confirm), rebuild (confirm required), back (return)
  Verify: "rebuild" requires explicit confirm before calling remote function
```

**Storage submenu** (tui_menu, ERASE is destructive):
```
Function: run_storage_submenu() or equivalent in run_manage_mode()
  → tui_menu returns tag: "disk", "erase", "back"
  → case dispatches: disk (read-only, no confirm), erase (confirm with WARNING), back (return)
  Verify: "erase" shows explicit warning in tui_confirm, user must confirm to proceed
```

**Password input flow** (tui_password → validation):
```
Function: prompt_config()
  → tui_password captures password string
  → if empty: prompts confirmation password
  → if mismatch: FATAL error, does not continue
  Verify: password mismatch → FATAL, does not continue
  Verify: password match → proceeds to next step (usually encryption mode or SSH config)
```

**Tracing requirements** — for each flow pathway:
1. List all TUI functions called in order
2. List all expected return types (tag string, boolean via tui_confirm, string via tui_input, password via tui_password)
3. List all conditional branches (case statements, if statements)
4. For each branch, document the final resolved behavior (what actually happens)
5. Flag any pathway where: the return type doesn't match the caller's expectation, or the branch logic seems wrong

**Automated trace** (use grep to extract all TUI call sites, then trace each one manually):
```bash
# Extract all tui_* calls and their surrounding context
grep -n 'tui_menu\|tui_confirm\|tui_input\|tui_password\|tui_checklist\|tui_msgbox' prepare-deployment.sh

# For each tui_menu call found, locate the corresponding case/esac that consumes the result
# For each tui_confirm call, verify the if/then branch leads to correct action
# This grep is a starting point — full tracing requires reading the code context
```

**Key invariants to verify for every flow**:
- Menu tag values in `tui_menu` calls match the `case` statements that consume them
- All destructive operations (APFS resize, ESP create, kernel pin/unpin/update, macOS erase) are gated by `tui_confirm`
- All tui_menu/tui_input/tui_password callers use the global result variable pattern: `tui_X ...; VAR="$_TUI_RESULT"` — NOT `VAR=$(tui_X ...)` which hangs dialog
- All tui_confirm callers use it as `if tui_confirm ...` or `||` — NOT capturing output
- tui_input and tui_password results are checked for emptiness before use
- Back/exit choices always return from the function or exit the script, never fall through

### 2.15 Data Flow Tracing

Trace how user-supplied values flow through the entire codebase. This catches: values that are collected but never used, values that are overwritten before use, values that are transformed incorrectly, and values that reach execution context without proper sanitization.

#### 2.15.1 User Input to Execution Trace

For each user-facing input field, trace its full lifecycle:

```
Input: [field name] (e.g., WIFI_SSID)
Source: [tui_input, --flag, deploy.conf, autoinstall.yaml placeholder]
Storage: [variable name, conf file key]
Transformations: [sed replacement, escaping, validation]
Consumers: [which functions/commands receive this value]
Execution context: [local shell, SSH remote, sh -c in autoinstall, YAML value]
Sanitization: [quoting, escaping, validation applied before execution]
```

**Inputs to trace:**

| Input | Source | Flows To | Risk |
|-------|--------|----------|------|
| USERNAME | deploy.conf / --username | autoinstall.yaml, target /etc | Shell metacharacters in username |
| PASSWORD / HASH | deploy.conf / tui_password | autoinstall.yaml, chpasswd | Plaintext exposure, YAML injection |
| WIFI_SSID | deploy.conf / --wifi-ssid | autoinstall.yaml sed replacement, netplan YAML | `#`, `/`, `&` in SSID break sed |
| WIFI_PASSWORD | deploy.conf / --wifi-password | autoinstall.yaml, netplan YAML | YAML injection, sed delimiter clash |
| SSH_KEY | deploy.conf / tui_menu | autoinstall.yaml, /target/.ssh/authorized_keys | Newline handling, key format |
| HOSTNAME | deploy.conf / --hostname | autoinstall.yaml, target /etc/hostname | RFC 952 violations |
| DEPLOY_METHOD | --method / tui_menu | case dispatch to deploy_* functions | Invalid value handling |
| DEPLOY_MODE | deploy.conf / --deploy-mode | remote_mac_exec routing, sudo check bypass | Invalid mode handling |
| TARGET_HOST | deploy.conf / --target-host | ssh $TARGET_HOST commands | SSH injection, unreachable host |
| REMOTE_SUDO_PASSWORD | deploy.conf / --remote-password | ssh sudo -S -p '' via stdin | Password in process args |
| USB_DEVICE | tui_menu / auto-detect | diskutil, sgdisk, dd commands | Partition path injection |
| WEBHOOK_URL | deploy.conf / --webhook-* | logging.sh curl commands | URL injection |
| ENCRYPTION | --encryption / tui_menu | encrypt_config, decrypt_config | Invalid mode handling |

**For each input, verify:**
- Value is quoted at EVERY point it reaches a command (not just the first use)
- Value survives all transformations intact (collect → store → retrieve → use)
- No transformation step silently produces empty output from non-empty input
- Invalid values are caught BEFORE they reach destructive commands

#### 2.15.2 Config Value Round-Trip Integrity

**End-to-end trace for every deploy.conf value:**
1. User enters value via TUI or CLI flag
2. Value is stored in deploy.conf by save_config()
3. Value is retrieved by parse_conf() on next run
4. Value is passed to autoinstall.sh generate_autoinstall()
5. Value is string-replaced into autoinstall.yaml template
6. Value is embedded in YAML that runs via sh -c in the installer
7. Value reaches its final destination (netplan, chpasswd, hostname, etc.)

**Verify at each step:**
- The value is identical to what the user entered (no truncation, escaping loss, encoding change)
- Special characters survive the full trip: spaces, `#`, `/`, `$`, backticks, quotes
- Values containing newlines don't break the sed replacement or YAML structure

#### 2.15.3 Variable Overwrite Detection

Trace every variable from assignment to last use. Detect:
- Variables assigned but overwritten before first use
- Variables assigned in one code path but consumed in a different code path that may not have executed
- Variables consumed before assignment (especially across `- |` blocks in autoinstall YAML)
- Global variables that should be local (side effects leak to callers)
- Local variables that should be global (values lost when function returns)

### 2.16 Error Message Quality Audit

Every error path must produce a message that is: (1) accurate, (2) actionable, and (3) free of assumptions. This section audits error messages for quality, not just presence.

#### 2.16.1 Accuracy Verification

**For every die(), log_fatal(), agent_error(), and echo "[FATAL]" call:**
- Is the message factually correct for ALL conditions that trigger it?
- Does the message describe what actually went wrong (not a symptom or unrelated condition)?
- Does the message avoid referencing assumptions that may not hold? (e.g., "SIP is blocking bless" — SIP may not be the cause; the message should say "bless failed" and list possible causes)

**Common accuracy problems:**
- Messages that assume a specific cause when multiple causes are possible
- Messages that reference implementation details that may change (function names, variable names, file paths that depend on OUTPUT_DIR)
- Messages that include stale version numbers or hardcoded paths
- Messages that say "cannot find X" when the actual issue is "X exists but is invalid"

#### 2.16.2 Actionability Verification

**For every error message, answer: "What should the user DO next?"**
- If the message only says what went wrong but not how to fix it → needs improvement
- If the message suggests a fix that may not work → needs verification
- If the message says "see documentation" without specifying which section → needs specificity
- If the message suggests running a command → verify that command actually exists and works

**Actionable message template:**
```
[FATAL] What went wrong
  Cause: Most likely cause (or list of possible causes)
  Fix: Specific action the user should take
  Reference: Where to find more information (specific doc section)
```

#### 2.16.3 Error Context Completeness

**When an operation fails, does the error output include:**
- What was being attempted (operation name, phase)
- What specifically failed (command, file, network endpoint)
- The exit code of the failed command
- The stderr output from the failed command
- The state at failure point (journal phase, partial completion status)
- What the user can do to recover (revert, retry, manual fix)
- Whether the system is in a safe state or needs intervention

#### 2.16.4 log_fatal vs die Consistency

Two functions serve similar purposes but with different side effects:
- `die()` (from logging.sh): logs FATAL + calls log_shutdown + exits
- `log_fatal()`: logs FATAL + exits (may not call log_shutdown)
- `agent_error()`: emits NDJSON + exits (no logging.sh integration)

**Verify:**
- Every FATAL exit goes through one of these functions (never bare `exit 1`)
- The correct function is used for the correct context (TUI vs agent mode)
- log_shutdown is called in trap handlers (not from die — calling it from both trap and die causes double-call)
- agent_error produces valid JSON with all required fields

---

## PHASE 3: INTEGRATION AND SYSTEM TESTING

### 3.1 Script Interaction Testing
Test scripts calling other scripts:
- prepare-deployment.sh calls build-iso.sh via menu_build_iso
- prepare-deployment.sh sources all lib/*.sh files
- macpro-monitor/start.sh starts server.js
- tests/vm/create-vm.sh and test-vm.sh

Test scripts sourcing libraries — verify sourcing order matches Phase 0.1
Test scripts using shared resources (state files, journal, ESP mount)
Test scripts in different working directories (CWD != SCRIPT_DIR)
Test scripts with relative vs absolute paths (LIB_DIR override)
Test: does build-iso.sh work when run from a different directory than its location?

### 3.2 Environment Testing
Test with minimal environment (empty ENV, no deploy.conf)
Test with missing dependencies (xorriso not installed, python3 missing)
Test with conflicting configurations (deploy.conf has WIFI_password with shell metacharacters)
Test with different shell versions (bash 3.2 which ships on macOS vs bash 5.x)
- Specifically: test arrays in tui.sh (`local -a`), `[[ ]]` vs `[ ]`, `${var,,}` vs `tr`
Test on all target platforms (macOS for build/deploy, Ubuntu for remote manage)
Test: does build-iso.sh run correctly on Linux (where `stat -f%z` becomes `stat -c%s`)?

### 3.3 Concurrency and State Testing
Test scripts running simultaneously (two deploy instances, two monitor instances)
Test scripts modifying shared state (journal file concurrent access)
Test idempotency (run prepare-deployment.sh --dry-run multiple times)
Test cleanup on interrupt (Ctrl-C) during each deployment phase
Test cleanup on SIGTERM during deployment
Verify trap handlers execute correctly in all exit scenarios
Verify: does cleanup_on_error in prepare-deployment.sh properly call rollback_from_journal or revert_changes?
Verify: does build-iso.sh's cleanup trap properly remove staging directory on failure?

### 3.4 Resource Management
Verify all temporary files are cleaned up:
- build-iso.sh staging directory ($STAGING)
- retry_diskutil stderr temp files
- retry_ssh stderr temp files
- tui.sh temp files from _tui_mktemp
- journal state files in /var/tmp/macpro-deploy*

Verify all file descriptors are closed (serial FD in logging.sh, tui temp file FDs)
Verify all background processes are terminated (macpro-monitor start/stop)
Verify all locks are released
Verify proper handling of large files (ISO extraction ~3.4GB, ESP with limited space)

---

## PHASE 4: BEST PRACTICES AND PATTERNS

**Beyond the listed checks:** The items in sections 4.1–4.4 are common vulnerability patterns, but they are NOT exhaustive. The reviewer MUST think about categories that are not listed — for example, information disclosure through timing attacks, denial-of-service vectors, dependency confusion, or any other security concern relevant to a deployment tool that runs as root. Add findings beyond the checklist.

### 4.1 Error Handling Audit
Verify `set -Eeuo pipefail` usage (or equivalent) in ALL scripts:
- prepare-deployment.sh: set -e, set -o pipefail, set -u
- build-iso.sh: set -e, set -o pipefail, set -u
- lib/*.sh: verify each has appropriate error handling

Check for proper error trapping: `trap 'cleanup_on_error' ERR` in prepare-deployment.sh, `trap cleanup EXIT` in build-iso.sh
Verify all external commands have error handling
Check for proper exit codes (E_SUCCESS through E_AGENT_DENIED)
Verify error messages are clear and actionable
Specific checks:
- VERIFY: `set -e` behavior with `|| die` patterns — does the script exit immediately on failure or does die() handle it?
- CHECK: In build-iso.sh, `xorriso -report_el_torito as_mkisofs` output is eval'd — is the injection check (`grep -qE '[;&|${}()]`) sufficient?
- CHECK: In rollback.sh, `journal_set` uses `eval` to reconstruct state — is this safe given the regex key validation?
- CHECK: In remote.sh, all destructive operations (kernel pin, apt sources changes) use `dry_run_exec` — are there any that don't?
- CHECK: In remote.sh, `remote_kernel_update` is interactive (uses tui_confirm) — how does this work in agent mode?
- CHECK: In remote.sh, some functions use `read -rp` for confirmation (non-TUI) while others use `tui_confirm` — is this inconsistent?

### 4.2 Safety and Security Review

#### 4.2.1 Input Validation and Sanitization
Check for proper input validation and sanitization on ALL user-facing inputs
Verify no unsafe use of eval or source with user input
Trace every tui_input / tui_password / deploy.conf value from entry point to execution
Verify user-supplied values (SSID, password, ISO path, device path) are quoted in every command they reach
Check for proper quoting of ALL variable expansions — every `"$VAR"` must be quoted, every unquoted `$VAR` is a finding
Test every user input field with shell metacharacters: `; | & $ \` ' " \n \t` space and Unicode
Test every user input field with YAML metacharacters: `: - [ ] { } & * ! % @ \``
Test every user input field with path traversal: `../` `/etc/passwd` `/dev/sda`

#### 4.2.2 Credential and Secret Handling
Trace every path where credentials appear: deploy.conf → autoinstall.yaml → netplan → ESP
Verify WiFi SSID and password are NEVER written to log files
Verify WiFi password is never visible in process args (ps output)
Verify SSH_AUTHORIZED_KEYS are not logged
Verify deploy.conf permissions (should be 600, not world-readable)
Verify autoinstall.yaml on ESP is not world-readable (note: FAT32 limitation)
Check if any error message or debug output leaks credential values
Audit all printf/echo/log statements that reference variables containing secrets
Verify gitignore covers deploy.conf and any other files containing credentials
Check that --wifi-password flag value is not visible in process listing (/proc/cmdline, ps)
Specific checks:
- VERIFY: In autoinstall.sh, `sed -i "s#__WIFI_PASSWORD__#${escaped_password}#g"` — is the escaping sufficient? What if password contains `#` or `/`?
- VERIFY: In autoinstall.sh, SSH_KEYS are split by newline and inserted into YAML — are special characters in SSH keys handled?
- CHECK: Does `log()` or `log_info()` ever log WIFI_SSID or WIFI_PASSWORD values?
- CHECK: Does `agent_output()` ever include credential values in its JSON output?
- CHECK: In save_config(), WIFI_PASSWORD is written in plaintext — verify chmod 600 is applied after

#### 4.2.3 Command Injection Attack Surface
This script runs as root (sudo). Any path from user input to command execution is root-level code execution.
Map every path from user-controlled input to shell command execution
Check: do any user inputs reach diskutil, xorriso, dd, sgdisk, newfs_msdos without proper quoting?
Check: does eval usage (e.g., return-by-name pattern in disk.sh deploy.sh detect.sh) allow injection through variable values?
Check: can any deploy.conf value break out of its intended context?
Check: are autoinstall.yaml early-commands and late-commands properly escaped when they contain variable interpolation?
Verify: every command constructed with user input uses proper quoting or array form
Specific checks:
- TRACE: WIFI_SSID from deploy.conf → exported → used in autoinstall.sh sed replacement → embedded in YAML early-commands → executed by sh -c in installer
- TRACE: USB device path from select_usb_device → diskutil, sgdisk commands in disk.sh deploy.sh — is it properly quoted?
- TRACE: ISO path from detect_iso → xorriso command — is it properly quoted?
- CHECK: In autoinstall.sh, python3 -c blocks receive $OUTPUT_PATH — is this safe from injection?
- CHECK: In remote.sh, remote__exec constructs SSH commands — are all arguments properly quoted for the remote shell?

#### 4.2.4 YAML Injection
User-controlled SSID and password get string-replaced into autoinstall.yaml
Test: can special characters in SSID/password break YAML parsing or inject arbitrary keys?
Test: can a SSID like 'sshd: enabled' inject YAML keys?
Test: can a password containing a colon or newline break the autoinstall structure?
Verify: the autoinstall generation properly escapes or quotes all user-controlled values
Check: does the YAML generation use printf with proper quoting, or does it use heredocs that might allow expansion?
Verify: netplan YAML generation (inside autoinstall early-commands) properly escapes SSID/password
Specific checks:
- VERIFY: generate_autoinstall() uses sed for placeholder replacement — test with SSID containing `#`, `/`, `&`, `\`
- VERIFY: The `generate_dualboot_storage()` Python script uses subprocess.run with sgdisk — is disk_dev properly validated before passing to sgdisk?
- CHECK: autoinstall.yaml early-commands are executed by `sh -c` in the installer — are all variable interpolations safe?
- CHECK: Does netplan YAML generation use `printf` (correct) or heredoc (risky — indentation inside `|` blocks adds unwanted spaces)?

#### 4.2.5 Supply Chain Integrity
The packages/ directory contains 34 .deb files installed via dpkg on the target system
Verify: are any .deb checksums or signatures validated before installation?
Document: what is the current trust model for packages/ (assumed: trusted source + git)
Check: could a malicious .deb in packages/ achieve root execution on the target?
Assess: is there a mechanism to verify package integrity (sha256sums, signatures)?
Check: are dkms-patches applied without integrity verification?
Recommend: add checksum verification for .deb files if not present
Verify: build-iso.sh checks for `.deb` file count but not integrity

#### 4.2.6 Privilege Escalation and Execution Context
Map every code path that runs as root (via sudo or in autoinstall context)
Identify all autoinstall early-commands and late-commands — these run as root in the installer
Verify: no autoinstall command downloads and executes arbitrary code from the internet
Verify: no autoinstall command exposes a network service unnecessarily
Check: does the webhook listener (macpro-monitor) accept connections from any interface? (HOST = '0.0.0.0')
Check: is the webhook URL (containing potential secrets) logged or stored insecurely?
Verify: SSH connections in remote.sh properly validate host keys (NOT StrictHostKeyChecking=no)
Note: remote_mac.sh uses `-o StrictHostKeyChecking=no -o BatchMode=yes` for deployment convenience — this is a known trade-off for headless local network deployment. Verify: REMOTE_SUDO_PASSWORD is not logged or stored in plaintext beyond deploy.conf

#### 4.2.7 TOCTOU and Race Conditions
Identify all check-then-act sequences (e.g., check disk exists → modify disk)
Check: `diskutil list` → `diskutil addPartition` — can partition layout change between calls?
Check: `diskutil info` → `diskutil apfs resizeContainer` — can container change between calls?
Check: `verify_esp_mount` → write to ESP — can ESP be unmounted between calls?
Document: which race conditions are acceptably unlikely vs which need mitigation
Check: are lock files or other serialization mechanisms used for shared resources?

#### 4.2.8 Filesystem and Permission Security
**This section expands on Phase 2.11 (Sudo File Ownership Audit)** with broader filesystem security concerns. Phase 2.11 provides the detailed root-ownership audit methodology for files under `$HOME`; this section covers additional permission and filesystem concerns.

Verify: temporary files created with mktemp (not predictable paths in /tmp)
Verify: temporary directories created with safe permissions (not world-readable)
Verify: ESP mount point permissions (note: FAT32 has no Unix permissions)
Verify: journal files (.Ubuntu_Deployment/, /var/tmp/macpro-deploy-state.env) are not world-readable
Verify: log files do not contain credentials or sensitive configuration
Check: are cleanup trap handlers robust against partial state (e.g., ESP mounted but not formatted)?
Specific checks:
- VERIFY: retry_diskutil and retry_ssh use mktemp for stderr files — are they cleaned up in all paths?
- VERIFY: tui.sh _tui_mktemp uses mktemp but falls back to /tmp/tui_$$ — is this safe?
- VERIFY: rollback.sh STATE_FILE at /var/tmp/macpro-deploy-state.env — is this world-readable?
- VERIFY: build-iso.sh STAGING directory at /tmp/macpro-iso-staging or /tmp/vmtest-iso-staging — predictable path vulnerability?
- CHECK: Is /var/tmp/macpro-deploy-state.env cleaned up by journal_destroy on success?

#### 4.2.9 Network Security
Verify: SSH connections use key-based auth, not password-in-command-line
Verify: SSH config does not disable StrictHostKeyChecking
- CHECK: remote.sh uses `-o ConnectTimeout=10 -o BatchMode=yes` — verify host key verification behavior
- CHECK: Verify SSH config example in ssh/config.example uses proper key-based auth
Verify: webhook server (macpro-monitor) does not expose sensitive data without auth
- CHECK: server.js listens on 0.0.0.0 by default — accessible from any network
- CHECK: server.js has rate limiting (RATE_LIMIT_MAX_REQUESTS = 10 per second) — is this sufficient?
- CHECK: server.js sanitizes input (sanitizeString, sanitizeProgress) — test with XSS payloads
Check: can the webhook URL be used to inject false progress reports or trigger actions?
Verify: no credentials transmitted in plaintext over network (webhook is HTTP, not HTTPS)
Macpro-monitor specific security checks:
- Test: POST to /webhook with malformed JSON — does it handle gracefully or crash?
- Test: POST to /webhook with oversized body (>256KB) — is it rejected?
- Test: GET /api/progress — does it expose any sensitive data?
- Test: Can XSS be injected through webhook progress messages? (check escapeHtml usage)
- Check: ALLOWED_ORIGINS environment variable — default empty means CORS allows any origin

#### 4.2.10 Autoinstall Environment Security
Review all early-commands in autoinstall.yaml (and autoinstall-vm.yaml) for security implications
Verify: no early-command writes to locations outside the target filesystem
Verify: no early-command creates setuid binaries
Verify: no early-command modifies SSH configuration to allow root login with password
- CHECK: early-commands start SSH server with `useradd -m -s /bin/bash ubuntu` and `echo "ubuntu:ubuntu" | chpasswd` — this creates a known password!
Verify: late-commands do not leave backdoors or disable security features
Check: is UFW configuration applied in late-commands correct and restrictive?
Check: is the kernel pin mechanism (apt preferences) tamper-resistant?

### 4.3 Portability Review
Check for bashisms if POSIX compatibility required (note: scripts use bash 3.2 features, not POSIX)
**Critical distinction:** Code that runs on macOS uses bash 3.2+ and BSD tools. Code embedded in autoinstall YAML `- |` blocks runs via `sh -c` (dash) in Ubuntu's Subiquity installer — POSIX ONLY. Verify each `- |` block contains NO bashisms:
- No `[[ ]]` — use `[ ]` instead
- No arrays — use positional parameters or string iteration
- No `<<<` herestrings — use `echo "..." | command` or `printf`
- No `${var,,}` or `${var^^}` — use `tr` or `awk`
- No `local -n` namerefs — use `eval` pattern with validated variable names
- No `mapfile`/`readarray` — use `while read` loops
- No associative arrays — use flat key=value files or case statements

Verify GNU vs BSD command compatibility (macOS uses BSD, Ubuntu uses GNU):
- CHECK: `stat -f%z` in detect_iso — macOS syntax. Does this work on Linux? (Linux uses `stat -c%s`)
- CHECK: `sed -i` patterns in autoinstall.sh use both GNU (`sed -i s/.../`) and BSD (`sed -i '' s/.../`) syntax — are both covered?
- CHECK: `diskutil` is macOS-only — does remote.sh use any diskutil commands for Linux?
- CHECK: `sgdisk` usage — is it available on both macOS (via Homebrew) and Ubuntu?

Check for hardcoded paths:
- VERIFY: Are there any hardcoded absolute paths that won't work on both platforms?
- CHECK: /tmp paths in build-iso.sh, logging.sh, retry.sh — are they appropriate for both platforms?
- CHECK: /var/tmp paths in rollback.sh — are they writable on both platforms?

Verify proper shebang lines (`#!/bin/bash` on all .sh files)
Check for platform-specific code paths:
- VERIFY: Does logging.sh properly detect platform (Darwin vs Linux) for serial device paths?
- VERIFY: Does detect_iso's stat command handle both macOS and Linux?
- CHECK: Does remote.sh's SSH command construction work with both macOS and Linux SSH clients?

### 4.4 Documentation Consistency and Accuracy Review

This project maintains three documentation files with distinct audiences:
- **AGENTS.md** — For LLM agents and automated tools: architecture, constraints, code conventions, implementation details
- **README.md** — For humans: usage instructions, quick start, troubleshooting, feature descriptions
- **CHANGELOG.md** — For everyone: version-by-version record of what changed

#### 4.4.1 Delineation Enforcement
Verify each document contains its audience delineation header
Verify AGENTS.md header states: "for LLM agents and automated tools" and cross-references README.md and CHANGELOG.md
Verify README.md header states: "for humans" and cross-references AGENTS.md and CHANGELOG.md
Verify CHANGELOG.md header explains its purpose as the version history record
Verify no document contains content that belongs in another (see 4.4.2–4.4.4)

#### 4.4.2 Content Boundary Audit
AGENTS.md MUST contain (and README.md must NOT duplicate):
- Code style guidelines (naming conventions, set -e patterns, etc.)
- Module API descriptions (each lib/*.sh function signature and behavior)
- deploy.conf parsing internals (IFS behavior, KEY=VALUE split semantics)
- Key Constraints section (hardware limitations, platform quirks)
- Context Management Rules (memory, context reduction, session notes)
- YAML generation internals (string replacement vs yaml.dump, block scalar handling)
- DKMS Patch Architecture (install order, symlink behavior, patch guards)
- Kernel Update Process internals (7-phase function, rollback function, apt preferences internals, DKMS circular dependency)
- macOS Erasure internals (partition classification rules, sgdisk commands, GRUB update commands, rollback function)
- Agent Operations Reference (exact --operation flag mappings, function names, destructive flags)

README.md MUST contain (and AGENTS.md must NOT duplicate):
- Quick Start guide
- Prerequisites and installation commands (brew install ...)
- Troubleshooting section
- Monitoring stages table (human-readable progress descriptions)
- Risk assessment and mitigations section
- Switching between macOS and Ubuntu table
- Serial console instructions
- VM test environment usage
- Updating the System (Kernel Updates) — step-by-step commands, pre-update checklist, rollback procedures
- Erasing macOS and Expanding to Full Disk — step-by-step commands, danger warnings, partition classification

CHANGELOG.md MUST contain (and neither other doc should duplicate):
- Version-by-version change lists
- What was added/changed/fixed in each release
- Corresponding git tag for each entry

BOTH documents should contain (with appropriate framing for their audience):
- Deployment method descriptions (README: how to use, AGENTS: method codes, phase names, internals)
- Agent mode CLI flags (README: usage examples, AGENTS: flag implementation details)
- Exit codes (README: table with meanings, AGENTS: constant names and values)
- deploy.conf keys (README: what each key means, AGENTS: parsing behavior, encryption modes)
- Kernel update process (README: step-by-step commands, AGENTS: function internals, phase names, rollback logic)
- macOS erasure (README: step-by-step commands and warnings, AGENTS: partition classification rules, agent prompt template)

#### 4.4.3 Accuracy Verification
Verify AGENTS.md project structure tree matches actual filesystem (`ls -R`)
Verify AGENTS.md lib/*.sh descriptions match actual function signatures
Verify AGENTS.md Key Constraints are still accurate (no stale hardware assumptions)
Verify README.md deployment method numbers match --method flag values (1=ESP, 2=USB, 3=manual, 4=VM)
Verify README.md --help output matches actual prepare-deployment.sh --help output
Verify README.md agent mode operations table matches actual _AGENT_OPERATIONS in code
Verify deploy.conf.example documents ALL keys that parse_conf() accepts
Verify Exit code documentation in --help matches E_* constants in dryrun.sh
Verify DKMS patch instructions in AGENTS.md match actual patches in packages/dkms-patches/
Verify AGENTS.md Kernel Update and macOS Erasure sections cover all manage mode operations from lib/remote.sh
Verify AGENTS.md agent operations table has NO phantom operations (driver_status, driver_rebuild, erase_macos, apt_enable, apt_disable — all functions verified to exist in lib/remote.sh at remote_driver_status, remote_driver_rebuild, remote_erase_macos, remote_apt_enable, remote_apt_disable)
Verify AGENTS.md agent operations table includes health_check and rollback_status (these exist but may be missing)
Verify documentation does NOT reference --build-iso flag (it does not exist; use `sudo ./lib/build-iso.sh` directly)
Verify documentation does NOT reference How-to-Update.md or Post-Install.md (they have been deleted; content is in AGENTS.md and README.md)
Verify README.md kernel update phase count matches code (7 phases in remote_kernel_update, not 8)
Verify README.md macOS erasure step count matches code (6 steps, not 7)
Verify CHANGELOG.md version tags correspond to actual git tags (`git tag --list`)
Verify CHANGELOG.md entries match commit messages at each tag (`git log -1 <tag>`)

#### 4.4.4 Stale Content Detection
Scan all documentation for references to removed/renamed files, functions, or variables
Check for documentation describing features that no longer exist
Check for documentation referencing old default values
Check for TODO/FIXME/NOTE/HACK markers that should be resolved or documented
Verify no documentation references bug fixes or changes — those belong in CHANGELOG.md
Verify no documentation contains version-specific deltas — those belong in CHANGELOG.md
Verify vm-test/ section in AGENTS.md reflects that vm-test/ is superseded by --vm flag
Check for references to deleted files (How-to-Update.md, Post-Install.md — content moved to AGENTS.md/README.md)
Check for agent operations that reference nonexistent functions (driver_status → remote_driver_status, driver_rebuild → remote_driver_rebuild, erase_macos → remote_erase_macos, apt_enable → remote_apt_enable, apt_disable → remote_apt_disable)
Check for references to --build-iso flag (does not exist — ISO is built via `sudo ./lib/build-iso.sh`)

---

## PHASE 5: EXECUTION AND VALIDATION

**SAFETY BOUNDARIES** — classify every testable unit before execution:
- **SAFE** (run on development Mac): syntax checks, --help, --dry-run, read-only operations, Node.js monitor
- **DESTRUCTIVE** (only via --dry-run flag or in VirtualBox): disk partitioning, APFS resize, format, dd, USB writes
- **REMOTE-ONLY** (requires ssh access to target): all lib/remote.sh operations, manage mode
- **VM-REQUIRED**: deploy_vm_test, VirtualBox operations

### 5.1 Deployment Path Testing
For EACH deployment method, test the complete flow in dry-run mode:

METHOD 1: Internal Partition (ESP)
- prepare-deployment.sh --agent --dry-run --method 1 --storage 1 --network 1 --yes --json
- prepare-deployment.sh --agent --dry-run --method 1 --storage 2 --network 1 --yes --json
- prepare-deployment.sh --agent --dry-run --method 1 --storage 1 --network 2 --yes --json
- prepare-deployment.sh --agent --dry-run --method 1 --storage 2 --network 2 --yes --json
- Verify: all phases (analyze → shrink_apfs → create_esp → extract_iso → copy_pkgs → generate_config → verify_bless) are walked in dry-run
- Verify: generate_autoinstall produces valid YAML for each storage/network combination
- Verify: generate_dualboot_storage produces valid YAML with preserve:true entries for dual-boot

METHOD 2: USB
- prepare-deployment.sh --agent --dry-run --method 2 --storage 1 --network 1 --yes --json
- Verify: all phases (detect_usb → partition_usb → extract_iso_usb → copy_pkgs_usb → generate_config_usb → verify_usb) are walked
- Verify: USB device selection works in agent mode (auto-selects first device)

METHOD 3: Full Manual
- prepare-deployment.sh --agent --dry-run --method 3 --yes --json
- Verify: prompts for ISO path and USB device, creates standard Ubuntu USB

METHOD 4: VM Test
- prepare-deployment.sh --agent --dry-run --method 4 --vm --yes --json
- Verify: all phases (check_vbox → find_iso → build_iso → create_vm → start_monitor) are walked
- Verify: VM-specific autoinstall is used (autoinstall-vm.yaml)

Build ISO
- prepare-deployment.sh --agent --build-iso --dry-run --json
- Verify: ISO build steps are walked in dry-run

Manage Mode Operations
- prepare-deployment.sh --agent --operation kernel_status --host macpro-linux --json
- prepare-deployment.sh --agent --operation sysinfo --host macpro-linux --json
- prepare-deployment.sh --agent --operation driver_status --host macpro-linux --json
- (These are remote-only, will fail without target — verify error handling)

Revert
- prepare-deployment.sh --revert (requires prior failed deployment state)

### 5.2 Failure Mode Testing
For each deployment path, inject failures at critical points:
- METHOD 1: What happens if APFS resize fails mid-operation? Does rollback restore original size?
- METHOD 1: What happens if ESP creation succeeds but ISO extraction fails? Does cleanup remove the ESP partition?
- METHOD 2: What happens if USB partition creation succeeds but ISO extraction to USB fails?
- METHOD 4: What happens if VM creation succeeds but ISO copy fails?

Test recovery mechanisms:
- journal_init should detect and offer to resume from previous incomplete state
- rollback_from_journal should properly roll back based on recorded phase
- handle_phase_failure should collect error context and offer recovery instructions

Verify rollback works correctly for each deployment method (rollback_internal, rollback_usb, rollback_vm)
Test cleanup on failure:
- SIGINT during deploy: does cleanup_on_error fire? Does it call rollback?
- SIGTERM during deploy: same test
- Verify trap handlers in prepare-deployment.sh and build-iso.sh

Verify logs/reports are accurate after failure:
- STATE_FILE should contain last completed phase
- ERROR_REPORT_FILE should contain system state at failure point
- collect_error_context should gather disk, mount, SIP, FileVault info

### 5.3 Node.js Monitor Testing
Test macpro-monitor/server.js independently:
- Start server: `node server.js`
- POST /webhook with valid JSON progress event
- POST /webhook with built-in Subiquity event format
- GET / to verify HTML dashboard renders
- GET /api/progress to verify JSON API
- Test rate limiting: send >10 requests/second from same IP
- Test CORS headers: verify Access-Control-Allow-Origin
- Test XSS prevention: POST with `<script>alert(1)</script>` in message field
- Test stall detection: start with progress, wait >5 minutes, verify STALLED state
- Test graceful shutdown: SIGTERM, verify server closes and saves state
- Test persistence: start server, POST events, restart server, verify events are loaded from logs/progress.json
- Test WebSocket refresh: verify dashboard auto-refreshes every 3 seconds
- Test body size limit: POST >256KB, verify 413 response

### 5.4 VM Integration Test (Deferred to Phase 5.5)

The VM integration test is deferred to **Phase 5.5** to avoid spinning a VM on every 0-5 bug fix iteration. Phases 0-5 focus on static analysis, functional verification, and dry-run testing — the VM test only runs once those phases pass clean.

See **Phase 5.5** for the full VM integration test procedure.

### 5.5 Logging Verification
Verify multi-target logging writes to all configured targets:
- Verify `log_init` creates log directory and sets up webhook connection
- Verify log levels work correctly: DEBUG only to file, INFO/WARN/ERROR to all targets
- Verify serial FD is opened and written to on Linux (logging.sh detects platform)
- Verify webhook POST failure does not block or crash the main script
- Verify `log_shutdown` flushes all targets and closes file descriptors
- Verify log files contain timestamps, severity levels, and module context
- Verify serial console output includes all webhook progress stages (per AGENTS.md workflow)

---

## PHASE 5.5: VM INTEGRATION TEST

**This phase ONLY executes after Phases 0–5 all pass with zero P0, P1, P2 findings.** The VM integration test is the ONLY way to verify the autoinstall works end-to-end. It is deliberately separated from Phase 5 to avoid spinning a VM on every bug-fix iteration — VM tests are expensive (30+ minutes, 30GB+ disk) and should only run when static analysis and dry-run testing have already confirmed the code is correct.

**Gate:** Do NOT start Phase 5.5 until ALL of the following are true:
- Phase 0: Architecture model complete, no P0 issues
- Phase 1: Zero P0, zero P1 findings
- Phase 2: All deployment methods produce correct output, no P0/P1 findings
- Phase 3: No P0/P1 integration issues
- Phase 4: No P0/P1 security findings
- Phase 5: All SAFE-classified tests pass, dry-run deployment paths complete

**If Phase 5.5 uncovers bugs:** Fix them, then restart from Phase 0 (NOT just Phase 5.5 — a bug found in VM testing may have static analysis signatures that Phases 0-5 should have caught).

**Prerequisites:**
- VirtualBox installed and `VBoxManage` in PATH
- Stock Ubuntu 24.04.4 Server ISO in `prereqs/` directory
- `sshpass` available for automated SSH log grabbing
- Node.js available for the webhook monitor
- At least 30GB free disk space (ISO ~3.5GB, VM disk 25GB, staging ~3GB)

### 5.5.1 Build VM Test ISO

```bash
sudo ./lib/build-iso.sh --vm
```

**Verify:**
- ISO exists at `~/.Ubuntu_Deployment/ubuntu-vmtest.iso`
- ISO size is reasonable (~3-4GB)
- `xorriso` extraction completed without errors
- Build log shows "VM Test Mode" prefix
- GRUB config includes `console=ttyS0,115200` in kernel command line
- No `__REPLACE__` placeholders remain in the generated autoinstall.yaml
- autoinstall.yaml uses `fulldisk` storage (no `preserve:` entries)
- autoinstall.yaml uses `ethernet` network (enp0s3, not wlp*/wl*)
- Webhook URL is `http://10.0.2.2:8081/webhook` (VirtualBox NAT host gateway)

### 5.5.2 Create VirtualBox VM

```bash
cd tests/vm && sudo ./create-vm.sh
```

**Verify:**
- VM `macpro-vmtest` appears in `VBoxManage list vms`
- VM has EFI firmware (not BIOS)
- VM has 4 CPUs, 4.5GB RAM
- VM has serial port UART1 configured: `--uart1 0x3F8 4 --uartmode1 file /tmp/vmtest-serial.log`
- VM has NAT networking with SSH port forward: host 2222 → guest 22
- VM disk is at the correct path (VirtualBox default machine folder, NOT the project directory)
- ISO is attached as IDE DVD

**Critical: Serial Console Configuration**

The VM MUST have UART1 outputting to `/tmp/vmtest-serial.log`. This is the primary mechanism for observing the installation without a display. Verify:
- `VBoxManage showvminfo macpro-vmtest | grep "UART 1"` shows the serial port configuration
- The file `/tmp/vmtest-serial.log` will be created when the VM starts
- The autoinstall kernel command line includes `console=ttyS0,115200` which directs all kernel and installer output to serial

### 5.5.3 Start Webhook Monitor

```bash
cd macpro-monitor && PORT=8081 ./start.sh
# Or use test-vm.sh:
./tests/vm/test-vm.sh monitor
```

**Verify:**
- Monitor server starts on port 8081
- Webhook endpoint accessible at `http://localhost:8081/webhook`
- Dashboard accessible at `http://localhost:8081/`

### 5.5.4 Run VM Installation

```bash
cd tests/vm && ./test-vm.sh run
# Or manually: VBoxManage startvm macpro-vmtest --type headless
```

**Monitor the installation in real-time:**

```bash
# Watch serial log (kernel + Subiquity output):
tail -f /tmp/vmtest-serial.log

# Watch webhook events:
curl -s http://localhost:8081/api/progress | python3 -m json.tool

# Take screenshots (if VM has graphics):
./tests/vm/test-vm.sh screenshot
```

**Serial log timeline — the agent MUST verify these stages appear in `/tmp/vmtest-serial.log`:**

| Stage | Serial Log Marker | Timeout |
|-------|-------------------|---------|
| VM boot, GRUB menu | `GNU GRUB` or `menuentry` | 30s |
| Kernel boot | `Linux version 6.8.0` | 60s |
| Subiquity installer start | `subiquity` or `curtin` | 120s |
| Early-commands begin | `macpro-pkgs` or `early-commands` | 180s |
| Driver DKMS build | `dkms` or `wl.ko` | 300s (5 min) |
| Network config (ethernet) | `enp0s3` or `DHCP` | 60s after network |
| Storage provisioning | `curtin` or `partition` | 120s |
| Late-commands begin | `late-commands` or `macpro-install` | 300s |
| GRUB install | `grub-install` | 60s |
| System reboot | `reboot: Power down` or `systemd-shutdown` | 60s |
| Post-reboot SSH available | SSH on port 2222 | 300s (5 min) |

**If any stage is missing from the serial log after its timeout expires:**
1. Take a screenshot: `./tests/vm/test-vm.sh screenshot`
2. Check if the VM is still running: `VBoxManage showvminfo macpro-vmtest | grep State`
3. Check last 200 lines of serial log for errors: `tail -200 /tmp/vmtest-serial.log`
4. Document the failure stage and any error messages

### 5.5.5 Verify Installation Completion via SSH

After SSH becomes available (port 2222), run comprehensive verification:

```bash
# SSH into the VM
ssh -p 2222 ubuntu@localhost

# Or use the test script:
./tests/vm/test-vm.sh ssh
```

**Mandatory verification commands (run on the installed VM):**

```bash
# 1. DKMS status — wl driver MUST show "installed"
sudo dkms status

# 2. WiFi driver module (non-fatal — no Broadcom HW in VM)
lsmod | grep wl
# Expected: module loads but may not associate (no hardware)

# 3. Network connectivity
ip addr show enp0s3
ping -c 3 google.com

# 4. Disk layout verification
lsblk
# Expected: /dev/sda with EFI, /boot, / partitions (no macOS partitions)

# 5. Kernel version
uname -r
# Expected: 6.8.0-100-generic or whichever kernel the ISO was built with

# 6. Kernel pin verification
cat /etc/apt/preferences.d/99-pin-kernel
sudo apt-mark showhold | grep linux

# 7. Netplan configuration
cat /etc/netplan/*.yaml
# Expected: enp0s3 with DHCP, no match: clause, cloud-init disabled

# 8. Cloud-init network config disabled
cat /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg
# Expected: network: {config: disabled}

# 9. UFW firewall
sudo ufw status
# Expected: Status: active, 22/tcp ALLOW

# 10. GRUB configuration
cat /etc/default/grub.d/macpro.cfg
# Expected: nomodeset amdgpu.si.modeset=0 console=ttyS0,115200
```

**Log collection (automated via test-vm.sh or manual):**

```bash
./tests/vm/test-vm.sh logs
# Saves to tests/vm/vm-logs/:
#   macpro.log, curtin-install.log, subiquity.log, dmesg.log,
#   dkms-status.log, lsmod.log, lspci.log, netplan-configs.txt,
#   wl-module.txt
```

**Critical success criteria — the VM test PASSES only if ALL of the following are true:**

1. Serial log contains all 11 stages from the timeline table above
2. SSH is reachable on port 2222 within 5 minutes of VM start
3. `dkms status` shows broadcom-sta module installed (non-fatal if DKMS attempted but no Broadcom hardware)
4. Ethernet networking works (enp0s3 has IP, can ping external host)
5. Disk layout has no macOS/APFS partitions (fulldisk)
6. Netplan config uses enp0s3 with DHCP, no `match:` clause
7. Cloud-init network config is disabled
8. UFW is active with SSH allowed
9. GRUB command line includes `nomodeset` and `console=ttyS0,115200`
10. No errors in `/var/log/macpro-install/late-commands.log`

**Non-fatal conditions (VM test passes but logs warnings):**
- `wl.ko` driver loads but doesn't associate (no Broadcom hardware in VM — expected)
- `lspci` doesn't show Broadcom device (expected in VM)
- DKMS build for `wl` shows warning about missing hardware (expected)

**Fatal conditions (VM test FAILS):**
- DKMS build exits with error code (driver source compilation failed)
- Subiquity crashes or halts (storage or network misconfiguration)
- SSH not reachable within 5 minutes of reboot (broken GRUB or network)
- Ethernet not functional (enp0s3 has no IP or can't ping out)
- Disk layout has APFS or macOS partitions (dual-boot config leaked into VM test)

### 5.5.6 Serial Log Deep Analysis

Beyond verifying stages exist, the agent MUST review the serial log for ERRORs, WARNINGs, and failures:

```bash
# Extract all error-level messages
grep -iE 'error|fail|panic|oops|warning' /tmp/vmtest-serial.log | grep -v 'expected\|non-fatal\|DEBUG'

# Find DKMS build output
grep -A5 -B5 'dkms\|DKMS\|wl.ko\|broadcom' /tmp/vmtest-serial.log

# Find network configuration events
grep -A3 -B3 'enp0s3\|netplan\|DHCP\|networkd' /tmp/vmtest-serial.log

# Find Subiquity status events
grep -iE 'subiquity.*event|curtin.*install|install.*complete' /tmp/vmtest-serial.log

# Find late-commands execution
grep -A10 'late-commands\|macpro-install\|macpro-pkgs' /tmp/vmtest-serial.log
```

**For each ERROR or WARNING found:**
1. Classify as fatal or non-fatal (see criteria in §5.5.5)
2. Trace the error back to its source (which `- |` block in autoinstall.yaml, which package, which command)
3. Determine if the error exists in production autoinstall.yaml too (not just VM-specific)
4. If production-affecting: fix the root cause, rebuild ISO, and restart from Phase 0
5. If VM-specific: document the difference and whether it needs a code change

### 5.5.7 Webhook Event Verification

During the VM installation, the webhook monitor should receive progress events. Verify:

```bash
# Check all events received
curl -s http://localhost:8081/api/progress | python3 -m json.tool

# Expected event stages (from AGENTS.md progress list):
# prep-init(2%), prep-headers(5%), prep-toolchain(10%), prep-dkms(13-15%),
# prep-wifi(18-22%), prep-ssh(23-25%), late-init(30%), late-headers(35%),
# late-libs(45%), late-tools(55%), late-dkms(60-65%), late-netplan(70-73%),
# late-grub(75-78%), late-mdns(80-83%), late-hold(85-88%), late-sudo(90%),
# late-logs(95%), complete(100%)
```

**Verify webhook events:**
- Events are received in chronological order with increasing progress
- No event uses `{name, event_type, origin}` fields (those trigger built-in Subiquity handler)
- All events use `{progress, stage, status, message}` format
- Final event shows `status: "complete"` with `progress: 100`

### 5.5.8 Cleanup

After successful verification:

```bash
# Power off and destroy VM
cd tests/vm && ./test-vm.sh destroy

# Stop webhook monitor
./macpro-monitor/stop.sh

# Remove serial log (contains sensitive data)
rm -f /tmp/vmtest-serial.log

# Remove VM test ISO (optional — keep for re-runs)
# rm -f ~/.Ubuntu_Deployment/ubuntu-vmtest.iso
```

**If the VM test FAILS:** Do NOT destroy the VM. Save all logs first:
```bash
# Save serial log
cp /tmp/vmtest-serial.log tests/vm/vm-logs/serial-failure.log

# Grab SSH logs (if reachable)
./tests/vm/test-vm.sh logs

# Take final screenshot
./tests/vm/test-vm.sh screenshot
```

Then diagnose the failure from the logs, fix the root cause, rebuild the ISO, and restart from **Phase 0** (not just Phase 5.5 — VM bugs may have static analysis signatures that earlier phases should catch).

---

## PHASE 6: REFACTORING AND SIMPLIFICATION

**This phase only executes once Phases 0–5 all pass with zero P0, P1, P2 findings.** Its purpose is to identify opportunities to simplify, consolidate, and improve code clarity — not to find new bugs, but to reduce maintenance burden and cognitive complexity.

**Gate:** Do NOT start Phase 6 until ALL of the following are true:
- Phase 0: Architecture model complete, no P0 issues
- Phase 1: Zero P0, zero P1 findings
- Phase 2: All deployment methods produce correct output, no P0/P1 findings
- Phase 3: No P0/P1 findings, all safety boundaries verified
- Phase 4: No P0/P1 security or accuracy findings
- Phase 5: All SAFE-classified tests pass, dry-run deployment paths complete
- Phase 5.5: VM integration test completes successfully (all 10 criteria in §5.5.5)

If Phase 6 identifies changes, those changes are implemented, committed, and the ENTIRE cycle restarts from Phase 0 (because refactoring can introduce regressions).

### 6.1 Function Consolidation

**Identify functions that do nearly the same thing and could be unified:**

- Find function pairs/groups where the body differs by only 1-2 parameters or conditionals
- Find functions whose names differ but whose logic is identical except for the data they operate on
- Find helper functions called from exactly one call site — can the logic be inlined for clarity?
- Find functions that are thin wrappers around a single command — is the wrapper providing value (error handling, logging) or just indirection?

**For each candidate, evaluate:**
- Would merging reduce total lines of code without reducing readability?
- Would merging eliminate a class of potential inconsistency (e.g., two functions that should stay in sync)?
- Is the function providing meaningful abstraction (error handling, logging, retry) or just adding a call layer?
- Would inlining make the caller easier to read or harder?

**Rules:**
- Do NOT merge functions that serve different purposes just because they look similar
- Do NOT inline functions that are called from multiple call sites
- Do NOT remove error handling, logging, or retry logic in the name of simplification
- ALWAYS restart from Phase 0 after any consolidation change

### 6.2 Variable and Configuration Simplification

**Identify variables and configuration that could be simplified:**

- Find variables that are set but never meaningfully varied (always the same value, or derived from one other variable with no branching)
- Find configuration keys that are parsed but have identical behavior for all possible values
- Find flags/switches that are checked in only one place — could the logic be simplified?
- Find environment variables that are read but their default is always used in practice
- Find duplicated default values defined in multiple places (e.g., same default in both the variable declaration and the config parser)

**For each candidate, evaluate:**
- Would removing the variable/flag/option reduce the number of code paths to test?
- Is the option providing genuine user value or just configuration surface area?
- Would removing it break backward compatibility? (If yes, consider deprecation path instead)

### 6.3 Control Flow Simplification

**Identify overly complex control flow that could be simplified:**

- Find deeply nested if/elif/else chains (3+ levels) — can they be flattened with early returns or guard clauses?
- Find case/esac blocks where multiple patterns do the same thing — can they be combined?
- Find functions with multiple exit points that could be simplified to a single return
- Find loops with complex condition logic — can they be simplified with a helper function?
- Find `if [ "$VAR" = "1" ]; then ... elif [ "$VAR" = "2" ]; then ... elif [ "$VAR" = "3" ]` patterns that could use case/esac instead

**For each candidate, evaluate:**
- Does the simplification reduce cognitive complexity (measured by nesting depth, branch count)?
- Does it preserve all existing behavior and error handling?
- Is the simplified version equally readable by someone unfamiliar with the code?

### 6.4 Module Boundaries and Responsibilities

**Identify modules with unclear or overlapping responsibilities:**

- Find functions in module A that are only called from module B — should they move to module B?
- Find modules that source other modules they don't actually need — can the dependency be removed?
- Find modules where the name doesn't match the contents — is a rename warranted?
- Find circular dependency patterns (A sources B, B sources A) — can they be broken?
- Find shared state between modules that could be replaced by function parameters — reduces coupling

**For each candidate, evaluate:**
- Would moving the function reduce the number of modules that need sourcing?
- Would the move improve cohesion (functions in a module are related) or reduce it?
- Is the current organization causing bugs or confusion? (If not, consider leaving it)

### 6.5 Dead Code and Redundancy Elimination

**This builds on Phase 2.12 (Orphan Detection) but goes further:**

- Find functions that are called but whose return value is never used — can the return value be removed?
- Find functions that compute the same value in multiple places — extract a shared helper
- Find repeated code blocks (3+ lines identical) across different functions — extract a shared helper
- Find comments that restate what the code does without adding value — remove or replace with "why" comments
- Find commented-out code blocks — remove them (git history preserves them)
- Find TODO/FIXME/HACK markers that were left from previous reviews — resolve or document in AGENTS.md constraints
- Find redundant variable assignments (variable set, then immediately overwritten without being read)
- Find redundant conditional checks (condition checked twice in the same flow, or always true/false)

### 6.6 Readability and Naming Improvements

**Identify naming that obscures intent:**

- Find variable names that are too short to be self-documenting in context (`_f`, `$1` used without local naming)
- Find function names that don't describe what the function does (`handle_stuff`, `_process`)
- Find variable names that are misleading (`WIFI_CRITICAL` is true when WiFi is broken — inverted semantics)
- Find inconsistent naming patterns (some functions use `remote_` prefix, some use `verify_`, some use bare names)
- Find parameter names in function definitions that use positional references (`$1`, `$2`) instead of `local` named variables

**For each candidate, evaluate:**
- Would the rename make the code self-documenting?
- Does the current name cause confusion? (Misleading names MUST be renamed — e.g., inverted booleans)
- Is there a consistent naming convention already in the codebase that should be followed?

### 6.7 Refactoring Execution Rules

**These rules are MANDATORY for any change made during Phase 6:**

1. **One refactoring per commit** — each commit should change one thing only (one function consolidated, one variable simplified, one flow simplified). This makes regression debugging precise.
2. **Tag each commit** with the next v0.2.N version — refactoring commits get version tags like bug-fix commits.
3. **Restart from Phase 0 after each commit** — refactoring can introduce regressions. A full cycle proves it didn't.
4. **No functional changes in refactoring commits** — refactoring does NOT change behavior. If a refactoring would change observable behavior, it's a bug fix, not a refactoring — classify it properly.
5. **Document each refactoring in CHANGELOG.md** — under the version tag, list what was simplified and why.
6. **If a Phase 0–5 regression is found during refactoring** — STOP refactoring, fix the regression as a bug (Phases 0–5 cycle), then resume Phase 6 from the beginning after the fix cycle completes.

---

## PHASE 7: SELF-IMPROVEMENT AND COVERAGE GAP ANALYSIS

**This phase executes AFTER Phase 6 completes (or after Phases 0-5 complete with zero findings).** Its purpose is to improve the testing protocol itself by analyzing what the protocol missed, what was found outside the protocol, and where coverage gaps exist. This makes the protocol self-improving — each cycle should be strictly better than the last.

**Gate:** Do NOT start Phase 7 until Phases 0–5 pass with zero P0, P1, P2 findings (or Phase 6 completes with zero regressions).

### 7.1 Coverage Gap Detection

**The fundamental question:** "If this protocol were run on the codebase in its BEFORE-fix state, would it have caught the bugs that were found manually?"

For each bug found outside a formal review cycle:
1. Which phase SHOULD have caught it? (Map the bug to a phase)
2. Did that phase's checklist include a check that would find it?
3. If yes: why didn't the check catch it? (Stale grep pattern? Reviewer didn't execute it? Check was too specific?)
4. If no: what new check should be added? (This feeds §0.6 Bug Class Taxonomy)

**Coverage gap categories:**
- **Missing check**: No checklist item addresses this bug class → add one
- **Stale check**: Check references specific patterns that have changed → update
- **Unevaluated check**: Check exists but reviewer skipped it or misapplied it → strengthen enforcement mechanism
- **Wrong-phase check**: Check exists but in the wrong phase (e.g., architecture issue checked in Phase 2 instead of Phase 0) → move

### 7.2 Checklist Staleness Audit

Grep patterns, function names, and file references in this document become stale as the codebase evolves. Before each review cycle, validate that the document's references are current:

- `grep -c 'grep.*lib/' tests/TESTING_PROMPT.md` — count all grep commands that reference specific file paths. For each, verify the file still exists
- `grep -c 'tui_menu\|tui_confirm\|tui_input' tests/TESTING_PROMPT.md` — verify all referenced TUI functions still exist in lib/tui.sh
- Check for TODO/FIXME items added to this document that were intended to be resolved but weren't
- If a module was renamed, split, or merged since the last update, update all references in this document

### 7.3 Cross-Phase Feedback Loop

**Architecture findings from later phases must feed back to Phase 0.** The current protocol assumes Phase 0 runs first and later phases consume its output, but in practice, Phase 2+ often discovers architectural issues that Phase 0 missed. This feedback is currently lost.

**Mechanism:** When any phase (1-5) discovers an architectural issue (e.g., a function called from the wrong place in a flow, a module boundary violation, a variable lifecycle problem), that finding must be:

1. **Recorded as a Phase 0 finding** — add it to the architecture model as if Phase 0 had found it
2. **Cross-referenced** — note which phase found it and why Phase 0 missed it
3. **Used to improve Phase 0** — add a check to Phase 0 that would catch this class of architecture issue proactively

**Concrete example:** The confirmation-before-collection bug (found by user testing, not by the protocol) is an architecture issue — a function is called from the wrong position in a flow. Phase 0's architecture model should include "call sequence verification" — tracing that every function is called from the correct position relative to the data it depends on.

### 7.4 Quality Signal Tracking

**The binary pass/fail gate doesn't distinguish "nothing wrong" from "didn't look hard enough."** Track quality signals that indicate review depth:

- **Findings per phase**: How many NEW (not checklist-expected) findings did each phase produce? Zero new findings in a phase may indicate insufficient depth
- **Findings beyond checklist**: Count findings that are NOT covered by any checklist item — these indicate genuine discovery vs. rote verification
- **False negative rate**: After each cycle, track how many bugs were found OUTSIDE the protocol (by user testing, ad-hoc investigation, etc.) within N days of the cycle completing. This is the protocol's miss rate
- **Bug class coverage**: After extracting bug classes per §0.6, verify each class has a check in at least one phase. A class without a check is a coverage gap

**Quality signal targets:**
- Each phase should produce at least 1 finding not covered by its checklist items (indicates genuine review, not just checking boxes)
- Post-cycle miss rate should trend toward zero over successive cycles
- All known bug classes should have ≥1 check in the protocol

### 7.5 Protocol Self-Update

After completing Phase 7, update this document with all changes:

1. **Add new bug classes** to §0.6 Bug Class Taxonomy (generalized, no instance-specific details)
2. **Add new checks** to the appropriate phase sections with `[BUG-CLASS]` tags
3. **Update stale references** from §7.2 Checklist Staleness Audit
4. **Add cross-phase feedback** entries from §7.3
5. **Record quality metrics** from §7.4 for trend tracking

**Commit the protocol update separately from code changes** — the testing protocol is a living document that evolves with the project.

---

## ITERATIVE FIX AND TEST CYCLE

**Discovery vs. verification:** Each phase has two purposes: (1) verify the SPECIFIC items listed in that phase's checklists pass, and (2) DISCOVER new issues NOT listed in any checklist. The checklists define MINIMUM coverage, not maximum. If a reviewer finds themselves only checking items off a list and not finding any new issues, they are not reviewing thoroughly enough. Every phase should produce findings beyond the checklist items.

**Bug class extraction (MANDATORY for every bug found):** Before fixing any bug, extract its abstract pattern per §0.6. Every fix must be accompanied by a generalized bug class entry. This transforms individual fixes into institutional knowledge that prevents the entire class from recurring.

Process findings in severity order: P0 first, then P1, then P2, then P3.
Within each severity level, fix bugs one at a time, **except when a single root cause affects multiple files** — in that case, fix all affected files in one commit with a clear commit message listing all files changed. Then re-run all phases. Do not fix one file, test, fix the next file, test — this wastes regression cycles on what is logically one change.

For each bug:
1. **Fix Implementation**
   Document the bug in detail
   Identify root cause
   Implement minimal, focused fix
   Add comments explaining the fix if non-obvious

2. **Full Regression Testing**
   After ANY code change, re-run ALL phases from the beginning:
   - Phase 0: Re-verify architecture model is still accurate
   - Phase 1: Re-run all static analysis
   - Phase 2: Re-run all functional tests
   - Phase 3: Re-run all integration tests
   - Phase 4: Re-run all best practices checks
   - Phase 5: Re-run all execution tests
   Document any NEW findings introduced by the fix

3. **Version Control and Documentation**
   When all phases pass for a fix:
   Query current version: `git tag --list 'v0.2.*' | sort -V | tail -1`
   Append CHANGELOG.md entry under next version:
     ```
     ### v0.2.X — [brief description]
     - fix: [specific change]
     - fix: [specific change]
     ```
   Stage changes: `git add -A`
   Commit with descriptive message:
     ```
     fix: [brief description]

     - Fixed [specific issue]
     - Root cause: [explanation]
     - Verified by: [phases re-run]
     ```
   Tag with next version: `git tag -a v0.2.X -m "fix: [brief description]"`
   Push: `git push && git push --tags`

### Continue Until
- ALL phases (0-5) pass with zero P0, P1, P2 findings
- Phase 6 (Refactoring) can begin and produces zero regressions (Phases 0-5 re-pass after each refactoring)
- P3 findings are documented (fix if trivial, document if not)
- ShellCheck reports zero errors (warnings acceptable if covered by .shellcheckrc)
- Scripts execute correctly in all tested environments within safety boundaries
- Documentation reflects current reality
- No simplification opportunities remain that would reduce code by 10+ lines or reduce nesting by 2+ levels

---

## REPORTING REQUIREMENTS

After each phase, provide:

- **Findings:** Complete list of all issues discovered
- **Severity:** P0/P1/P2/P3 classification for each finding
- **Impact:** What breaks and for whom
- **Evidence:** Logs, output, or reproduction steps
- **Root Cause:** Why this happens (especially for cross-module issues found via Phase 0)
- **Fix Applied:** What was changed and why
- **Verification:** How the fix was validated and which phases were re-run
- **Next Steps:** What needs to be checked next

### Phase Pass Criteria
- **Phase 0 PASS:** Architecture model is complete, all collisions documented, no P0 issues blocking further testing
- **Phase 1 PASS:** Zero P0 findings, zero P1 findings, all P2/P3 findings documented
- **Phase 2 PASS:** All deployment methods produce correct output in dry-run mode, no P0/P1 findings
- **Phase 3 PASS:** No P0/P1 findings, all safety boundary classifications verified
- **Phase 4 PASS:** No P0/P1 security findings, no P0/P1 accuracy findings
- **Phase 5 PASS:** All SAFE-classified tests pass, dry-run deployment paths complete
- **Phase 5.5 PASS:** VM integration test completes with all 10 success criteria met (§5.5.5), DKMS builds successfully
- **Phase 6 PASS:** No remaining simplifications that reduce code by 10+ lines or nesting by 2+ levels; all refactoring changes verified via Phases 0-5 re-run with zero regressions

---

## FINAL CHECKLIST

Before completion, verify:

- [ ] All scripts pass `bash -n` syntax check
- [ ] All scripts pass ShellCheck with zero errors
- [ ] All command-line flags tested individually and in combination
- [ ] All execution modes tested (dry-run, verbose, agent, json)
- [ ] All 4 deployment methods tested in dry-run mode (method 1/2/3/4 × storage 1/2 × network 1/2)
- [ ] All manage mode operations tested
- [ ] Build ISO path tested
- [ ] Revert path tested
- [ ] All readonly/export variable collisions resolved
- [ ] All guard variables present and effective
- [ ] All lib modules source-compatible with main script's declarations
- [ ] Dry-run mode produces zero side effects for all deployment methods
- [ ] All error paths tested with proper messages and exit codes
- [ ] All dependencies documented and verified
- [ ] All temporary resources properly cleaned up
- [ ] All exit codes match documentation
- [ ] All integration scenarios tested
- [ ] Architecture model (Phase 0) still accurate after all fixes
- [ ] All commits properly tagged on v0.2.* sequence and pushed
- [ ] No credentials leaked in logs, error messages, or process args
- [ ] All user inputs validated and quoted in every execution path
- [ ] deploy.conf permissions are 600 (not world-readable)
- [ ] YAML injection tested — SSID/password cannot break autoinstall structure
- [ ] Command injection tested — no user input reaches shell execution unquoted
- [ ] SSH connections validate host keys (note: remote_mac.sh uses StrictHostKeyChecking=no for headless deployment — documented trade-off)
- [ ] REMOTE_SUDO_PASSWORD not leaked to logs, process args, or unencrypted files beyond deploy.conf
- [ ] Autoinstall early/late-commands reviewed — no backdoors or unsafe downloads
- [ ] Webhook server does not expose sensitive data without authentication
- [ ] Supply chain: .deb integrity verification mechanism documented or implemented
- [ ] TOCTOU race conditions identified and mitigated where feasible
- [ ] Node.js monitor tested — XSS, rate limiting, body size, persistence
- [ ] macpro-monitor CORS and security headers verified
- [ ] Server.js stall detection and graceful shutdown verified
- [ ] VM integration test executed per Phase 5.5 (all 10 success criteria met)
- [ ] VM serial log contains all 11 installation stages
- [ ] DKMS compilation verified in VM (non-fatal: wl module loads but no hardware)
- [ ] VM SSH verification: networking, disk layout, kernel pin, netplan, UFW, GRUB
- [ ] Multi-target logging verified (serial + file + webhook)
- [ ] Journal state machine tested (init, set, destroy, rollback, crash recovery)
- [ ] Config round-trip tested (parse_conf → save_config → parse_conf)
- [ ] WiFi connectivity circuit breaker tested
- [ ] Autoinstall YAML validated against Subiquity schema for all method/storage/network combinations
- [ ] Every autoinstall YAML `- |` block verified POSIX-only (no bashisms)
- [ ] AGENTS.md has LLM audience delineation header with cross-references
- [ ] README.md has human audience delineation header with cross-references
- [ ] CHANGELOG.md exists and covers all tagged versions
- [ ] No bug fix histories or change logs in AGENTS.md or README.md
- [ ] AGENTS.md project structure tree matches actual filesystem
- [ ] README.md --method values match actual code implementation
- [ ] deploy.conf.example documents all parse_conf() keys
- [ ] Documentation accuracy verified against actual code behavior
- [ ] First-run flow: welcome prompt appears before config detail prompts
- [ ] First-run flow: deployment method selected before config values collected
- [ ] First-run flow: all paths exit cleanly (no fallthrough to returning-user code)
- [ ] Returning-user flow: main menu appears directly (no first-run prompts)
- [ ] Agent mode: bypasses first-run flow entirely
- [ ] Flow paths are mutually exclusive — no path can execute another path's code
- [ ] Sudo file ownership: all file writes under $HOME chowned to SUDO_USER
- [ ] Sudo file ownership: find ~ -user root returns zero results in user home
- [ ] Orphan audit: all functions have at least one call site (or documented reason)
- [ ] Orphan audit: all exported variables are consumed by at least one module
- [ ] Orphan audit: all config keys parsed are consumed, all consumed keys are parsed
- [ ] Orphan audit: all lib/ modules have at least one external function call
- [ ] Bash 3.2: no bash 4.0+ features (local -n, mapfile, declare -A, ${var,,}, etc.)
- [ ] Platform boundaries: macOS commands wrapped with remote_mac_* for remote mode, not in remote.sh
- [ ] Remote mode: DEPLOY_MODE=remote routes all macOS commands via SSH (remote_mac_exec/remote_mac_sudo)
- [ ] Remote mode: preflight checks run on target host (remote_mac_preflight)
- [ ] Remote mode: root check skipped on local machine (no local sudo needed)
- [ ] Remote mode: ISO transfer, config generation, and verification all handle remote path correctly
- [ ] Function scope: every function classified as collect-only, execute-only, or collect-and-execute
- [ ] Single-execution: every destructive action runs exactly once per invocation per flow path
- [ ] Single-execution: collect-and-execute functions don't have callers that also execute the same action
- [ ] Execution path walkthrough: all paths through main() traced from entry to exit
- [ ] Execution path walkthrough: all deployment method paths traced through journal phases
- [ ] Execution path walkthrough: all remote.sh operation paths traced including rollback branches
- [ ] Execution path walkthrough: all remote_mac.sh routing paths traced for both local and remote modes
- [ ] Execution path walkthrough: build-iso.sh path traced including failure cleanup
- [ ] Execution path walkthrough: cross-script paths (subprocess, SSH, SCP) traced
- [ ] Data flow: every user input traced from collection to final execution context
- [ ] Data flow: config values survive full round-trip (TUI → save → parse → autoinstall → target)
- [ ] Data flow: variable overwrite detection — no value collected then overwritten before use
- [ ] Data flow: variables consumed before assignment detected and fixed
- [ ] Error messages: every die/fatal/agent_error message is accurate for ALL trigger conditions
- [ ] Error messages: every error message tells the user what to DO (not just what went wrong)
- [ ] Error messages: error context includes operation, command, exit code, and recovery options
- [ ] Error messages: die vs log_fatal vs agent_error used correctly in each context
- [ ] Line-by-line: every shell script line verified against 12-point checklist
- [ ] Line-by-line: every FINDING confirmed valid in full-file context before reporting
- [ ] Refactoring: function consolidation candidates identified and evaluated (merge, inline, or keep)
- [ ] Refactoring: variable/configuration simplification candidates identified
- [ ] Refactoring: control flow simplification candidates identified (nesting reduction, case consolidation)
- [ ] Refactoring: module boundary clarity verified (functions in correct module, no circular deps)
- [ ] Refactoring: dead code, redundant conditionals, and redundant assignments removed
- [ ] Refactoring: naming improvements applied where current names are misleading or unclear
- [ ] Refactoring: each change is one commit, tagged, with full Phase 0-5 regression pass

---

## PHASE 2.10: FIRST-RUN FLOW VERIFICATION

This section verifies that the application correctly handles the first-run experience when no existing configuration is found, and that the existing-user flow is not disrupted. The general pattern: **conditional flows must be mutually exclusive** — a first-run user and a returning user must see completely different prompts, with no overlap or leakage.

### 2.10.1 Config File Existence as Flow Switch

Many applications use a "config exists?" check to branch between first-run and returning-user flows. This pattern is fragile because:

- The config file path may be overridden (OUTPUT_DIR, CONF_FILE redirection)
- The config file may exist but contain placeholder/template values rather than real data
- Agent mode may need to bypass the first-run flow entirely
- Multiple scripts in the project may independently check for the config file

**Verify the config-detection pattern in this project:**
- Is the config file check performed exactly ONCE at startup, with the result stored in a flag variable?
- Is the flag variable checked consistently at every branch point? Or do some code paths re-check the file directly (creating inconsistency if the file is created mid-session)?
- When the config file is absent and a template/substitute is used instead, are all "real vs template" differences handled? (e.g., placeholder values that would fail validation if treated as real data)
- Does agent mode bypass the first-run flow? Verify every flow gate checks both "config absent" AND "not agent mode"
- If OUTPUT_DIR is overridden, does the config file path re-resolve correctly? Check for circular references

**General test methodology:**
```bash
# Test absence of config → first-run flow
# Test presence of config → returning-user flow
# Test agent mode + absent config → agent flow (NOT first-run)
# Test agent mode + present config → agent flow
# Test config with placeholder values → treated same as absent?
```

### 2.10.2 First-Run Prompt Ordering Invariants

Any first-run flow must present prompts in a specific logical order. Verify these invariants:

**Invariant 1: Welcome/confirmation before detail collection**
- A user MUST be asked "Do you want to set up?" BEFORE being asked for username, password, or any technical details
- Test: Remove config file, run script. The FIRST interactive prompt must be a yes/no confirmation, not a username input

**Invariant 2: Environment context before deployment choices**
- A user making deployment decisions benefits from seeing their environment info first
- Test: After confirmation, environment information should be displayed/explorable before the deployment method menu

**Invariant 3: Deployment method before config details**
- The deployment method (ESP/USB/VM) determines WHICH config values are needed
- Test: Deployment method selection must occur BEFORE username/password/WiFi prompts

**Invariant 4: No prompt duplication across flow paths**
- If a function collects user selections AND performs an action, and the caller also performs that same action, the action runs twice
- Test: For every call from main() to a menu/function, verify the callee's scope (collect-only vs collect-and-execute) and ensure the caller doesn't redundantly execute

**Invariant 5: Confirmation/summary AFTER all data collection**
- The pre-execution summary (`show_pre_execution_summary`) and final confirmation prompt MUST appear AFTER `prompt_config()` completes — never before
- Test: Trace the call sequence. If `show_pre_execution_summary` appears between `menu_deploy_select` and `prompt_config`, it will display blank/placeholder values for Username, WiFi, SSH Keys, etc. because the user hasn't been prompted for them yet
- Test: Verify the summary function is NOT called inside a menu/selection function that runs before config gathering
- General rule: **a summary function must NEVER be called from a function that is itself called before the data it summarizes has been collected**

**Invariant 6: Config prompt functions must see empty/placeholder values as "not set"**
- When using a template/example config (e.g., `deploy.conf.example` with `__REPLACE__` placeholders), the `prompt_config()` skip conditions must treat placeholder values as equivalent to empty
- Test: `grep -c '__REPLACE__' lib/deploy.conf.example` — count all placeholder keys, then verify each one is either: (a) stripped to empty before `prompt_config()` runs, or (b) explicitly checked in `prompt_config()` with `[ "$VAR" = "__REPLACE__" ]`
- Test: Also check for non-`__REPLACE__` placeholder patterns (e.g., `192.168.1.X` for WEBHOOK_HOST, `macpro-linux` for HOSTNAME) — these are "valid-looking but not user-configured" values that should trigger prompting on first-run

**General test methodology — prompt sequence trace:**
```
For each entry condition (new user, returning user, agent mode):
  1. Run the script (or dry-run)
  2. Record the exact sequence of TUI functions called
  3. Verify the sequence matches the expected ordering
  4. Verify no prompt appears in the wrong flow path
```

### 2.10.3 Flow Path Mutual Exclusivity

When a script has multiple flow paths (first-run, returning-user, agent, revert), they must be **mutually exclusive** — exactly one path runs per invocation.

**Verify mutual exclusivity:**
- Does every flow path end with `exit` or an explicit `return` that prevents fallthrough to another path?
- After the FIRST flow path's code block ends, is subsequent code reachable? (It should NOT be if the first path was taken)
- Trace each flow path from entry to exit — is there any path that "falls through" into a different flow's code?

**General test methodology — exit point audit:**
```bash
# For every flow path, identify:
# 1. Entry condition (the if/elif/case that gates the path)
# 2. All exit points (exit N, return N, or die)
# 3. Any code after the exit point in the same scope
# 4. Whether the exit is unconditional (always taken) or conditional (could be skipped)
```

### 2.10.4 Environment Information Gathering

Functions that gather and display system information must handle failures gracefully — many system commands may fail or return unexpected output depending on system configuration.

**Verify for every system-info command:**
- Command not found → graceful fallback (not crash)
- Command returns non-zero → check stdout (some commands exit 0 on failure with error in stdout)
- Command returns empty output → sensible default displayed
- Command returns unexpected format → no crash, display raw or "Unable to determine"

**Cross-check: are any platform-specific commands accidentally used in the wrong context?**
- macOS-only commands (diskutil, bless, csrutil, sw_vers, systemsetup, ipconfig) should NEVER appear in lib/remote.sh (runs on Linux target)
- Linux-only commands (dkms, apt, efibootmgr, systemctl) should NEVER appear in prepare-deployment.sh main flow (runs on macOS host)

### 2.10.5 Returning-User Flow Preservation

When adding a first-run flow, the returning-user flow must be preserved unchanged. Verify:

**Regression checklist:**
- With existing config, the main menu appears directly (no first-run prompts)
- With existing config, all menu items (Deploy/Manage/Revert/Exit) still work
- With existing config, missing values in config still trigger prompt_config for those values only
- The decrypt_config call still runs for returning users
- The root/permission check still runs in the correct position
- The main while loop and select_mode() are still reachable

---

## PHASE 2.11: SUDO PRIVILEGE ESCALATION SIDE-EFFECTS AUDIT

When a script runs as root (via sudo or otherwise), any file it creates inherits root ownership. This causes silent failures when user-space tools (SSH, git, shells) refuse to read root-owned files in user directories. This is a **class of bugs** — not a one-off issue.

### 2.11.1 Root-Ownership Contamination Pattern

**The pattern:** Script runs as root → writes files under `$HOME` → files owned by root → user-space tools silently ignore them.

**Common victims:**
- `~/.ssh/config` — SSH ignores configs owned by wrong user (silent, no error)
- `~/.ssh/id_*` — SSH refuses to use keys with wrong ownership
- `~/.gitconfig` — Git may refuse to read root-owned config
- `~/.ssh/authorized_keys` — SSHd ignores root-owned authorized_keys in user dirs
- Any dotfile in `$HOME` that tools check ownership on

**Audit methodology for ALL scripts running as root:**
1. Search for ALL file-write operations under `$HOME`:
   ```bash
   grep -n '>>.*\$HOME\|>.*\$HOME\|mkdir.*\$HOME\|cp.*\$HOME\|ssh-keygen.*\$HOME\|touch.*\$HOME' prepare-deployment.sh lib/*.sh
   ```
2. For each match, verify `chown "${SUDO_USER:-$USER}"` follows the write
3. Also check: does `SUDO_USER` exist as a variable? It is set by sudo on most platforms, but verify it's available on the target macOS version
4. Check for file-move operations (`mv`) that may move a root-owned temp file into a user directory

### 2.11.2 Directory Ownership Chain

When a script creates directories and then files within them:
- The directory must be chowned BEFORE files are created (or after — but both must be chowned)
- If the directory is created but the script exits before chown, the user gets a root-owned directory they can't write to
- Verify: trap/cleanup handlers also chown any partially-created directories

### 2.11.3 Config File and Output Directory Ownership

- `save_config()` writes deploy.conf — verify ownership is set for the non-root user
- `OUTPUT_DIR` (typically `~/.Ubuntu_Deployment/`) — verify directory and contents are chowned
- Any generated files (autoinstall.yaml, ISO) written under OUTPUT_DIR — verify ownership
- Log files written under OUTPUT_DIR — verify ownership

**General test:** Run any script path as root, then `find ~ -user root` — should return zero results in user home directory.

---

## PHASE 2.12: ORPHANED AND UNUSED CODE DETECTION

This section systematically identifies dead code, unreachable paths, and code that was implemented but never wired up. The goal is to find **structural integrity issues** — code that exists but serves no purpose, or code that should exist but was never connected.

### 2.12.1 Function Definition-to-Call Site Audit

**The pattern:** A function is defined but never called from any reachable code path. This indicates either:
- Dead code from a removed feature → should be deleted
- An implemented-but-unwired feature → needs wiring or removal
- A callback target called dynamically → verify the dynamic dispatch actually reaches it

**Audit methodology:**
1. Extract ALL function definitions: `grep -n '^[a-z_]*()' prepare-deployment.sh lib/*.sh`
2. For each function, search for call sites across all non-test files
3. Report functions with ZERO call sites
4. For dynamic dispatch (case/esac, variable indirection, eval), verify separately:
   - Every `case` branch maps to a function that exists
   - Every `--operation` flag maps to a function that exists
   - Every menu item's action function exists

**Classification of uncalled functions:**
- **Dead code**: Was used previously but the caller was removed → delete
- **Unwired implementation**: Implemented but never connected → wire up or delete
- **Internal helper**: Only called by other orphaned functions → chain removal
- **Template-embedded**: Defined in a template (e.g., autoinstall YAML) that runs in a different context → document, don't delete
- **Dynamic dispatch target**: Called via case/esac or eval → verify the dispatch actually reaches it

### 2.12.2 Variable Definition-to-Consumption Audit

**The pattern:** A variable is exported or set but never read by any other module. Exports that aren't consumed are dead surface area — and variables consumed but never set are P1 bugs.

**Audit methodology:**
1. List all `export` and `readonly` declarations
2. For each variable, search for read access (not just the declaration line)
3. Report variables that are set but never read
4. Report variables that are read but never set (P1 bug)
5. For exported variables, verify the consuming subprocess actually uses them

**Check for semantically inverted variables:**
- Variables where the name implies the opposite of the value (e.g., `CRITICAL=false` meaning "is critical" vs "not critical")
- Verify variable naming matches boolean interpretation at every use site

### 2.12.3 Unreachable Code Path Detection

**The pattern:** Code exists that can never execute in any possible runtime state.

**Systematic checks:**
- Code after unconditional `exit` or `die` in the same scope
- Code in an `else` branch where the `if` condition is always true (e.g., after a guard pattern)
- `case` patterns that are shadowed by earlier matching patterns
- Functions that are only called from other unreachable functions
- Guard-protected blocks where the guard is always true on second source (double-source guards)

**Trace-based detection:**
For each function that contains `exit`, `die`, or `return` with no fallthrough:
1. Identify all exit points
2. Check if any code follows an unconditional exit in the same scope
3. For conditional exits, trace the condition — can it ever be false?

### 2.12.4 Config Key Completeness Audit

**The pattern:** A config key is parsed but never consumed, or a value is consumed but never parsed. Both indicate incomplete wiring.

**Audit methodology:**
1. List all keys accepted by `parse_conf()`
2. For each key, trace where the value is consumed after parse_conf
3. List all values consumed by downstream functions (autoinstall.sh, deploy.sh, etc.)
4. Cross-reference: every parsed key must have a consumer, every consumed value must have a parser
5. Check for keys that are used differently in different flow paths (first-run vs returning-user)

### 2.12.5 Module Sourcing Audit

**The pattern:** A module is sourced but none of its functions are ever called, OR a module's functions are called but the module is never sourced.

**For each lib/*.sh module:**
1. List all functions defined in the module
2. List all functions called from outside the module
3. Verify: Is the module sourced by every script that calls its functions?
4. Verify: If no functions from a module are called externally, is the module dead weight?
5. Check conditional sourcing: if a module is conditionally sourced, what happens when the condition is false but a function is still called?

---

## PHASE 2.13: BASH 3.2 COMPATIBILITY VERIFICATION

macOS ships with bash 3.2. All scripts must be compatible with this version. This section verifies no bash 4.0+ features are used in the main execution path.

### 2.13.1 Forbidden Feature Audit

Verify NO usage of these bash 4.0+ features anywhere in the project:

| Feature | Bash Version | Replacement |
|---------|-------------|-------------|
| `local -n` (namerefs) | 4.3+ | `eval` with validated variable names |
| `mapfile` / `readarray` | 4.0+ | `while read` loop |
| Associative arrays `declare -A` | 4.0+ | Case statements or flat files |
| `${var,,}` / `${var^^}` | 4.0+ | `tr '[:lower:]' '[:upper:]'` |
| `${var//pattern/replacement}` | — | `sed` or single `${var/pattern/replacement}` |
| `|&` (pipe stderr) | 4.0+ | `2>&1 |` |
| `read -N` (exact byte count) | 4.1+ | `dd` or `head -c` |
| `coproc` | 4.0+ | Background subshells |
| `|&` combined pipe+redirect | 4.0+ | `2>&1 |` |

**Search patterns:**
```bash
grep -rn 'local -n\|mapfile\|readarray\|declare -A\|\${[a-zA-Z_]*,,}\|\${[a-zA-Z_]*^^}\|\${[a-zA-Z_]*//\| |&' prepare-deployment.sh lib/*.sh
```

### 2.13.2 Platform-Specific Command Boundary Audit

**This section provides a systematic audit of command platform boundaries**, complementing the per-line checks in Phase 1.5 (platform-specific line-by-line checks). Phase 1.5 catches individual instances during line-by-line review; this section ensures complete coverage by auditing every external command's platform context.

Scripts in this project run on different platforms: macOS (host), Ubuntu installer (dash), Ubuntu target (bash). Commands and syntax must match their execution context.

**Verify command platform boundaries:**
- macOS-only commands (`diskutil`, `bless`, `csrutil`, `sw_vers`, `systemsetup`, `ipconfig`, `newfs_msdos`, `hdiutil`) MUST NOT appear in lib/remote.sh (runs on Linux)
- macOS-only commands in lib/disk.sh, lib/bless.sh, lib/detect.sh, lib/deploy.sh MUST be wrapped with `remote_mac_exec` or `remote_mac_sudo` (so they route via SSH in remote mode)
- Linux-only commands (`dkms`, `apt-get`, `efibootmgr`, `systemctl`) MUST NOT appear in prepare-deployment.sh main flow (runs on macOS)
- Every external command must be checked: which platform runs it? Is it available there?
- In DEPLOY_MODE=remote, macOS commands run on TARGET_HOST via SSH — verify all deployment phases (disk, bless, detect, deploy, revert) correctly route commands

### 2.13.3 Flag Syntax Platform Differences

Some commands use different flag syntax across platforms:

| Command | macOS syntax | Linux syntax | Where to check |
|---------|-------------|-------------|----------------|
| `stat` | `stat -f%z` | `stat -c%s` | detect.sh, build-iso.sh |
| `dd bs=` | `bs=1m` (lowercase) | `bs=1M` (uppercase also works) | Any dd usage |
| `sed -i` | `sed -i ''` (BSD) | `sed -i` (GNU) | autoinstall.sh |
| `date` | BSD date | GNU date | Any date usage |

**Audit:** For each command that differs across platforms, verify the script runs on the correct platform version.

---

## PHASE 2.14: ACTION SINGLE-EXECUTION GUARANTEE

This section verifies that every destructive or significant action executes exactly ONCE per user invocation, regardless of which flow path is taken. This covers any pattern where an action could execute multiple times: a function that both collects and executes being called from a context that also executes, a function being called from both the callee and the caller, or overlapping flow paths that reach the same action through different code branches.

### 2.14.1 Function Scope Classification

**Every function in the project must be classified into one of these categories:**

| Category | Behavior | Return value |
|----------|----------|-------------|
| **Collect-only** | Gathers user input, sets variables | 0=success, 1=cancel; side effects: variable assignments |
| **Execute-only** | Performs an action using previously-set variables | 0=success, non-zero=failure; side effects: system changes |
| **Collect-and-execute** | Gathers input AND performs the action | 0=success, 1=cancel; side effects: variable assignments + system changes |

**Audit methodology:**
1. For every function that interacts with the user (calls tui_*), classify it
2. For every function that performs system changes (calls diskutil, deploy, etc.), classify it
3. If a function is "collect-and-execute", trace ALL its callers:
   - Does the caller also execute the same action after the function returns?
   - If yes → **double execution**
   - Verify: the caller's post-call code is compatible with what the callee already did

### 2.14.2 Cross-Path Execution Audit

When multiple flow paths lead to the same action, verify that each path executes the action exactly once.

**Audit methodology:**
1. List all actions that have significant side effects (deployment, disk partitioning, APFS resize, kernel update, macOS erase)
2. For each action, trace ALL code paths that lead to it
3. For each path, count the number of times the action is invoked
4. If any path invokes the action more than once → **double execution bug**

**Trace template for each destructive action:**
```
Action: [function_name]
Side effects: [disk changes, system modifications, network changes]
Paths that lead to this action:
  - [Path name]: [entry point] → [intermediate calls] → [action function]
  - [Path name]: [entry point] → [intermediate calls] → [action function]
  - [Path name]: [entry point] → [intermediate calls] → [action function]
For each path: count invocations of the action function. Must be exactly 1.
For each path: verify no caller re-invokes the action after the callee returns.
```

### 2.14.3 Variable State After Function Return

When a "collect-and-execute" function sets global variables AND performs an action, the caller may re-execute using those same variables. Verify:

- After a function sets DEPLOY_METHOD/STORAGE_LAYOUT/NETWORK_TYPE and runs deployment, the caller does NOT re-run deployment using those variables
- State variables (journal, _ESP_CREATED, _APFS_RESIZED) correctly reflect the already-executed action
- If the caller checks these state variables before re-executing, the check prevents the double execution
- If no such guard exists, this is a double-execution vulnerability

### 2.14.4 Agent Mode Isolation

Agent mode should have an independent execution path that does NOT overlap with interactive flows.

**Verify:**
- Agent mode does NOT call any "collect" functions (tui_menu, tui_confirm, etc.) — values come from CLI flags and deploy.conf
- Agent mode does NOT trigger first-run flow
- Agent mode calls execute-only functions directly, not through collect-and-execute wrappers
- Running both `--agent --method 1` and interactive mode in separate invocations produces the same result (same deploy function called, same side effects)

---

## Phase 7: Self-Improvement and Coverage Gap Analysis

This section documents meta-findings from the review process itself — patterns in how the review was conducted, what was missed, and how to improve subsequent cycles.

### 7.1 Subagent Usage and Delegation Patterns

**Finding:** During this review cycle, subagents were used for parallel exploration (Phase 1.1.1-1.1.3 TUI/logging audits and Phase 1.2 eval/security audit). The results were mixed:

- **Structured grep-based searches worked well.** When the prompt specified exact grep patterns (`grep -n "Proceed\?" lib/tui.sh`), the subagent produced useful results.
- **Broad analysis tasks produced verbose but shallow output.** When the prompt asked for "comprehensive analysis" without specifying exact patterns, the subagent produced lengthy reasoning but often restated the prompt rather than providing actionable findings.
- **Direct tool usage was more efficient for targeted checks.** For specific, known patterns (eval audit, /dev/tty audit, EXIT trap check), running grep directly was faster and more reliable than delegating.

**Improved subagent pattern for future cycles:**

1. **Use subagents for breadth, not depth.** Fire 5+ parallel explore agents each searching for ONE specific pattern (e.g., one per bug class from §0.6), not one agent asking "analyze everything."
2. **Specify exact search methodology in the prompt.** Instead of "audit X", say: "Run grep -n 'PATTERN' on FILE. For each match, check Y and Z. Report file:line with severity."
3. **Cross-reference subagent results before trusting them.** The TUI raw-fallback audit agent initially reported incorrect guard patterns. Direct verification of a sample caught this error.
4. **Prefer direct tools for known-pattern checks.** If you already know what to search for (from a checklist), run grep yourself. Reserve subagents for discovery tasks where you don't know the pattern.

### 7.2 Review Coverage Assessment

**Phases completed this cycle:**
- Phase 0: Full (0.1-0.6, all gates passed)
- Phase 1.1-1.3: Full (syntax, structure, TUI audits, logging audit, variable scope)
- Phase 1.4: Partial (control flow patterns checked, `|| true` audit, retry logic)
- Phase 1.5: Targeted (eval sites, sed -i, `|| true`, specific line-by-line on key functions)
- Phase 1.6: YAML validation passed, schema valid
- Phase 2: Unit tests run (83 pass), agent mode basic flow tested
- Phase 5: Dry-run execution tested, --help verified

**Phases NOT completed this cycle:**
- Phase 1.7: Systematic execution path walkthrough (only specific paths traced, not exhaustive)
- Phase 2.1-2.16: Most functional behavior tests not executed (requires macOS target)
- Phase 3: Integration testing (requires Mac Pro hardware)
- Phase 4: Best practices review (partially covered by Phase 1 findings)
- Phase 5.5: VM integration test (deferred)
- Phase 6: Refactoring (not started)

**New bug classes discovered this cycle:**

| Bug Class | Abstract Pattern | Custom Check |
|-----------|-----------------|--------------|
| Eval-with-user-input | `eval` is used with a string containing user-controllable input (filenames, config values) without proper quoting or sanitization | Audit all `eval` calls: verify the expanded string does not incorporate unsanitized external input; prefer global-variable patterns over `eval` for return values |
| Command substitution with TUI | TUI result-returning functions are called inside `$(...)` which creates a subshell that breaks dialog/whiptail on macOS (hangs) and mixes stdout channels | Grep for `$(tui_menu`, `$(tui_input`, etc. — all result-returning TUI functions must use `_TUI_RESULT` global, never stdout capture |
| Dry-run journal skip | In dry-run mode, phase-tracking journal entries are not recorded, so journal-based skip-on-resume logic cannot work after dry-run | Verify dry-run paths either record journal phases with a dry-run marker or explicitly document that dry-run state is not resumable |

### 7.3 Findings Summary for This Cycle

**P1 Findings (Critical):**

1. **P1-001: `$(eval "tui_menu ... $menu_args")` in prompt_ssh_key_selection (prepare-deployment.sh:563)**
   - Uses command substitution with tui_menu — can hang on macOS when dialog backend is active
   - Uses `eval` with `$menu_args` containing SSH key filenames (user-controllable from `~/.ssh/*.pub`)
   - All other TUI calls in prepare-deployment.sh correctly use `_TUI_RESULT` pattern
   - Fix: Replace `$(eval "tui_menu ... $menu_args")` with direct `tui_menu` call using `_TUI_RESULT` pattern

**P2 Findings (Major):**

1. **P2-001: ESP_NAME/ESP_SIZE redundant defaults**
   - `ESP_NAME` and `ESP_SIZE` declared `readonly` in prepare-deployment.sh but also have `:=` defaults in disk.sh, bless.sh, revert.sh
   - Harmless when sourced from main (readonly already set) but redundant and confusing

2. **P2-002: build-iso.sh eval with BOOT_PARAMS**
   - `eval "xorriso -as mkisofs $BOOT_PARAMS ..."` on line 200 of build-iso.sh
   - Injection check on lines 196-198 guards against metacharacters but regex could be more comprehensive

**P3 Findings (Minor):**

1. **P3-001: `die()` shadow in build-iso.sh** — intentional isolation, not a collision
2. **P3-002: `log()` shadows macOS system `log` command** — minor, all project code uses `log_*` functions
3. **P3-003: journal_set eval with set-enumerated variables** — key validated, minor concern

**Tests Status:**
- `bash -n`: All 16 lib/*.sh + prepare-deployment.sh PASS
- `shellcheck --severity=error`: All individual scripts PASS (main script timed out at warning level)
- Unit tests: 83/83 PASS (config:34, dryrun:24, retry:10, rollback:8, verify:7)
- Node.js syntax: PASS
- YAML validation: PASS