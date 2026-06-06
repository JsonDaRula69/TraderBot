# Error Reporting Contract — Installer Suite

**Version**: 1.0  
**Last updated**: 2026-06-06  
**Scope**: `install/traderbot-installer.sh`, `install/Install-TraderBot.ps1`, `install/traderbot-update.py`, `src/traderbot/cli/__init__.py` (uninstall path)

---

## 1. Contract Requirements

All installer scripts MUST adhere to the requirements below. Implementations may differ across languages (bash, PowerShell, Python) but the observable contract is the same.

### 1.1 Log File Path

| Field | Value |
|---|---|
| Directory | `$HOME/.traderbot/logs/` |
| Filename | `install-{YYYYMMDD-HHMMSS}.log` |
| Creation | At script start, before any significant operation |
| Location | The directory MUST be created (`mkdir -p`) before the first log write |

### 1.2 Exit Codes

| Code | Meaning | When to Use |
|---|---|---|
| `0` | Success | Normal completion, help display, early skip (non-interactive) |
| `1` | Generic error | Unspecified failure, catch-all for unexpected errors |
| `2` | Config/validation error | Invalid user input, bad API key format, missing required env vars |
| `3` | Dependency error | Missing required tool (Python 3.12, git, docker, openclaw), failed install of a dependency |
| `4` | Network error | Failed download, git clone failure, HTTP timeout, API unreachable |
| `130` | Interrupted (SIGINT) | User pressed Ctrl+C |
| `143` | Terminated (SIGTERM) | Process received SIGTERM |

### 1.3 User-Visible Error Format

All user-facing error output MUST:

- Be directed to **stderr** (not stdout)
- Start with the prefix `[ERROR] ` (literal text, uppercase, space after bracket)
- Warnings use `[WARN] ` prefix
- Informational messages use no prefix or `[INFO] ` prefix

```
[ERROR] Python 3.12 is required but not found.
[ERROR] git pull failed for branch 'main'.
[WARN]  Docker is installed but the daemon is not running.
```

### 1.4 Log File Format

Every log line MUST follow this format:

```
[{timestamp}] [{level}] {message}
```

Where:
- `timestamp` = `YYYY-MM-DD HH:MM:SS` in local time (24-hour)
- `level` = one of `INFO`, `WARN`, `ERROR`
- `message` = free-text error or status description

Example:
```
[2026-06-06 14:30:01] [INFO] Installer started. Log: /home/user/.traderbot/logs/install-20260606-143001.log
[2026-06-06 14:30:02] [ERROR] Python 3.12 is required but not found.
```

### 1.5 Mandatory Error Behaviors

Every code path that exits with a non-zero code MUST:

1. **Log the error to the log file** via the contract-compliant log function *before* exiting.
2. **Use the appropriate semantic exit code** (1–4) rather than bare `exit 1`.
3. **Emit a user-visible error message** to stderr in `[ERROR] format` at the same time as logging it.

### 1.6 Forbidden Patterns

- ❌ `except Exception: pass` without logging — silent swallows are forbidden at module boundaries.
- ❌ `exit 1` without first calling `_log_error()` (or equivalent) to write to the log file.
- ❌ `print()` or `echo` for error messages directed to stdout — errors MUST go to stderr.
- ❌ Mixing `print()` and `logger.info()` for the same class of messages within a single script.
- ❌ Returning 0 unconditionally when errors may have occurred.

---

## 2. Audit: Bash Installer (`install/traderbot-installer.sh`)

### 2.1 What It Does Right

- **Log infrastructure exists**: `_log()`, `_log_info()`, `_log_warn()`, `_log_error()` defined at lines 16–29.
- **Log path is correct**: `$HOME/.traderbot/logs/install-$(date +%Y%m%d-%H%M%S).log` (line 13).
- **Log format matches contract**: `[{timestamp}] [{level}] {message}` (line 21).
- **Log dir is created**: `mkdir -p "$TRADERBOT_LOG_DIR"` (line 14).
- **Startup logged**: `_log_info "Installer started. Log: $TRADERBOT_INSTALL_LOG"` (line 38).
- **Signal handlers**: `exit 130` (SIGINT) and `exit 143` (SIGTERM) — these match the contract's signal exit codes.
- **`exit 0` on normal paths**: `--help`, `--uninstall`, `--update` all return 0 correctly.

### 2.2 Gaps

| # | Gap | Severity | Details |
|---|---|---|---|
| G1 | `_log_error()` virtually unused | **High** | `_log_error` is called only ~2 times (lines 38 for info, 1932 for profile create). The ~60+ error paths use bare `echo "Error: ..." >&2` instead. |
| G2 | No file logging before exit 1 | **High** | All 20+ `exit 1` calls (lines 464, 481, 496, 518, 560, 565, 594, 610, 639, 647, 667, 683, 716, 878, 882, 970, 1165, 1753, 2119, 2124) exit without calling `_log_error()` first. The log file never records the failure. |
| G3 | All errors use exit code 1 | **Medium** | No semantic exit codes. Config errors (bad API key), dependency errors (missing Python 3.12), and network errors (git clone failure) all return `exit 1`. Should use 2, 3, or 4 respectively. |
| G4 | User-visible format inconsistent | **Medium** | Uses bare `echo "Error: ..." >&2` prefix rather than `[ERROR] ...`. The contract requires the `[ERROR] ` prefix. |
| G5 | `_log_warn()` rarely used | **Low** | ~15 warning paths use bare `echo "Warning: ..." >&2` instead of `_log_warn()`. |
| G6 | `install_traderbot` and `update_services` functions use `|| exit 1` in compound commands | **Low** | Lines like `pip install -e . 2>&1 || { echo "Error: ..."; exit 1; }` — the exit code is always 1 regardless of what `pip` returned. |

### 2.3 Summary

The bash installer has the **log infrastructure** fully defined and compliant with the contract, but it is **never wired into the error paths**. The gap is not design — it is adoption. Every `exit 1` needs a preceding `_log_error()` call and a semantically correct exit code.

---

## 3. Audit: PowerShell Installer (`install/Install-TraderBot.ps1`)

### 3.1 What It Does Right

- **Help displays** with `exit 0` (line 61).
- **Fatal errors use `exit 1`** — all 7 fatal exit paths (lines 90, 449, 517, 556, 590, 601, 623, 1157) exit with code 1.
- **`Write-Error`** used for fatal user-facing messages (lines 89, 448, 516, 555, 589, 600, 621, 1156).
- **Warnings use `Write-Host -ForegroundColor Yellow`** for visibility.
- **`$ErrorActionPreference = "Stop"`** at line 32 ensures unhandled errors halt execution.

### 3.2 Gaps

| # | Gap | Severity | Details |
|---|---|---|---|
| G7 | **No log file at all** | **High** | There is no log file path defined, no `$TRADERBOT_LOG_DIR`, no file I/O for logging. Zero persistence of errors or operations. |
| G8 | **No semantic exit codes** | **Medium** | All 7 fatal exits use `exit 1`. Should use 2 (config), 3 (dependency), or 4 (network) where applicable. |
| G9 | **User-visible format non-compliant** | **Medium** | Uses `Write-Error "message"` which PowerShell renders as red text but does NOT include the `[ERROR] ` prefix. Also, `Write-Error` writes to the error stream but PowerShell's formatting adds its own decoration (red, `Write-Error:` prefix). |
| G10 | **`exit 0` on non-fatal skip** | **Low** | Line 1197: `exit 0` when user declines to continue without OpenClaw. This should probably be `exit 0` (user chose to abort, not an error) — acceptable. |
| G11 | **No log directory creation** | **High** | `$CONFIG_DIR` (`~/.traderbot`) is created at line 651 (`New-Item -ItemType Directory -Path $CONFIG_DIR -Force`), but no log subdirectory is ever created under it. |

### 3.3 Summary

The PowerShell installer has **no logging infrastructure at all**. It needs a complete `Write-Log` function, a log file path, directory creation at startup, and `Write-Log` calls before every `exit 1`. This is the most gap-ridden of the three installers.

---

## 4. Audit: Python Update Script (`install/traderbot-update.py`)

### 4.1 What It Does Right

- **`sys.exit(main())`** at line 288 — the entry point exits with main's return value.
- **Logging module configured**: `logging.basicConfig(...)` at line 22.
- **`logger.warning()`** used for non-fatal errors (line 64: self-update failure).
- **`logger.info()`** used for status messages throughout.
- **No bare except:pass** — the few exceptions caught (lines 63, 191, 246) either log a warning or handle gracefully.

### 4.2 Gaps

| # | Gap | Severity | Details |
|---|---|---|---|
| G12 | **Always returns 0** | **High** | `main()` at line 283 has `return 0` unconditionally. Even if `_git_pull`, `_pip_install`, or any sub-step fails, the script reports success. The subprocess calls within (e.g., `_run()`, `subprocess.run()`) do not check return codes and propagate to the caller. |
| G13 | **No file logging** | **High** | `logging.basicConfig(level=logging.INFO, format="%(message)s")` writes to stdout only. There is no `FileHandler` writing to `~/.traderbot/logs/`. Log messages are lost when the terminal scrolls. |
| G14 | **Log format is non-compliant** | **Medium** | Uses `format="%(message)s"` — no timestamp, no level prefix. Contract requires `[{timestamp}] [{level}] {message}` format. |
| G15 | **Mixed print() and logger.info()** | **Medium** | Lines 232–234, 238, 250, 252, 255, 261, etc. use `print()` for user-facing progress messages, while lines 43, 59, 64, 98, 222 use `logger.info()`. The two are inconsistent in format and destination. |
| G16 | **Subprocess failures are silent** | **Medium** | `_run()` (line 40) calls `subprocess.run()` and logs the command, but does not check `result.returncode`. Failures in `_git_pull`, `_pip_install`, `_rebuild_sandbox_image`, `_configure_openclaw_sandbox`, and `_reregister_cron_jobs` are silently ignored. |
| G17 | **No semantic exit codes** | **Low** | Even if `main()` returned non-zero, there are no codes for config errors (2), dep errors (3), or network errors (4). |

### 4.3 Summary

The Python update script is the most polished in terms of exception hygiene (no bare `except: pass`), but it has a fatal design flaw: it always exits 0 and never writes to a file. Every sub-step failure is silently swallowed.

---

## 5. Audit: CLI Uninstall (`src/traderbot/cli/__init__.py`)

### 5.1 What It Does Right

- **User confirmation prompts** via `typer.confirm()` for destructive operations.
- **`console.print()` with rich formatting** for clear user feedback.
- **Exit code path**: the `uninstall` command does not explicitly exit with a code — it falls through to `app()` which exits 0 on success.

### 5.2 Gaps

| # | Gap | Severity | Details |
|---|---|---|---|
| G18 | **Bare except Exception: pass (8 instances)** | **High** | Lines 334, 350, 369, 452, 513, 531, 543, 562 all use `except Exception: pass`. These silently swallow failures in pip uninstall, symlink removal, cron job listing, file cleanup, Docker container/image operations, and temp file cleanup. The Docker and cron job paths are particularly concerning — failures there mean residual state. |
| G19 | **No file logging** | **Medium** | The uninstall function uses `console.print()` for user output but writes nothing to `~/.traderbot/logs/`. There is no record of what was uninstalled or what failed. |
| G20 | **No semantic exit code on failure** | **Low** | If `shutil.rmtree()` fails or a critical subprocess returns non-zero, the function continues and reports success. It should return `typer.Exit(1)` on critical failures. |

### 5.3 Summary

The CLI uninstall has the most severe anti-pattern: 8 bare `except Exception: pass` blocks that hide failures in Docker cleanup, cron removal, and file operations. This violates the "no silent swallows" rule from AGENTS.md and the contract's forbidden patterns.

---

## 6. Compliance Matrix

| Requirement | Bash Installer | PS Installer | Python Update | CLI Uninstall |
|---|---|---|---|---|
| Log file at `~/.traderbot/logs/install-*.log` | ✅ Defined | ❌ Missing | ❌ Missing | ❌ Missing |
| Log format `[{ts}] [{level}] {msg}` | ✅ Implemented | ❌ Missing | ❌ Plain format | ❌ Missing |
| Log dir created before first write | ✅ Line 14 | ❌ Missing | ❌ Missing | ❌ Missing |
| `[ERROR]` prefix to stderr | ❌ Uses bare `Error:` | ❌ Uses `Write-Error` | ❌ Uses `print()` | ❌ Uses `console.print("[red]")` |
| Semantic exit codes (0–4, 130, 143) | ❌ All exit 1 | ❌ All exit 1 | ❌ Always exit 0 | ❌ No explicit exit |
| Log before non-zero exit | ❌ Never done | ❌ No log file exists | ❌ Always exit 0 | ❌ No log file exists |
| No bare `except: pass` | ❌ N/A (bash) | ❌ N/A (powershell) | ✅ Clean | ❌ **8 instances** |
| Signal handling (130/143) | ✅ Lines 46–47 | ❌ No trap | ❌ No signal handler | ❌ No signal handler |

---

## 7. Recommendations

### 7.1 Bash Installer (High Priority)

1. Replace all 20+ `echo "Error: ..." >&2` patterns with `_log_error "..."` before each `exit`.
2. Assign semantic exit codes: config errors → `exit 2`, dependency errors → `exit 3`, network errors → `exit 4`.
3. Update `_log()` to emit `[ERROR] ` prefix to stderr instead of bare `  ` prefix (line 23).
4. Replace `|| exit 1` compound commands with explicit `_log_error + exit N` blocks.

### 7.2 PowerShell Installer (High Priority)

1. Add a `$TRADERBOT_LOG_DIR` and `$TRADERBOT_INSTALL_LOG` constant at the top of the script.
2. Add a `Write-Log` function matching the contract log format with `Add-Content` to the log file.
3. Call `Write-Log -Level ERROR` before every `exit 1`.
4. Add `[ERROR]` prefix to all `Write-Error` calls, or switch to a custom error function.
5. Assign semantic exit codes: `exit 2` for config, `exit 3` for dependencies, `exit 4` for network.

### 7.3 Python Update Script (Medium Priority)

1. Add a `FileHandler` to the logger that writes to `~/.traderbot/logs/install-{timestamp}.log`.
2. Change log format to `"[{asctime}] [{levelname}] {message}"` with `datefmt="%Y-%m-%d %H:%M:%S"`.
3. Replace all `print()` calls with `logger.info()` or a dedicated `_echo()` wrapper that logs + prints.
4. Check `result.returncode` in `_run()` and propagate failures up through `main()`.
5. Return non-zero exit codes from `main()`: `return 1` for generic, `return 3` for pip/git failure.

### 7.4 CLI Uninstall (High Priority)

1. Replace all `except Exception: pass` with at minimum `logger.warning(...)`. For Docker/cron operations, consider `logger.error(...)` and track failures for the final summary.
2. Add file logging to `~/.traderbot/logs/uninstall-{timestamp}.log` at the start of the uninstall command.
3. Return `typer.Exit(1)` if critical operations (data removal, service removal) fail.
