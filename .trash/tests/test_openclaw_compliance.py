"""Validate all OpenClaw CLI invocations in TraderBot source against Dep_Docs.

Scans the source tree for subprocess calls to ``openclaw`` (cron, config,
gateway, uninstall) and checks that every command, flag, and positional
argument matches what the OpenClaw docs define. Prevents flag-name mistakes
like ``--schedule`` instead of ``--cron``.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEP_DOCS = PROJECT_ROOT / "Dep_Docs" / "Openclaw-llms-full.txt"
SRC_DIR = PROJECT_ROOT / "src" / "traderbot"

# ---------------------------------------------------------------------------
# Parse OpenClaw docs into command signatures
# ---------------------------------------------------------------------------

# Known OpenClaw CLI commands and their valid flags from Dep_Docs
# Extracted from the authoritative doc file.
OPENCLAW_COMMANDS: dict[str, dict[str, set[str]]] = {
    "cron": {
        "add": {
            "--name",
            "--at",
            "--cron",
            "--tz",
            "--session",
            "--message",
            "--model",
            "--announce",
            "--channel",
            "--to",
            "--agent",
            "--system-event",
            "--wake",
            "--delete-after-run",
            "--light-context",
            "--thinking",
            "--no-deliver",
            "--deliver",
            "--best-effort-deliver",
        },
        "list": {"--json", "--agent"},
        "remove": set(),  # positional <jobId> only
        "edit": {
            "--name",
            "--cron",
            "--at",
            "--schedule",
            "--tz",
            "--session",
            "--message",
            "--model",
            "--announce",
            "--channel",
            "--to",
            "--agent",
            "--clear-agent",
            "--light-context",
            "--thinking",
            "--no-deliver",
            "--deliver",
            "--best-effort-deliver",
            "--no-best-effort-deliver",
        },
    },
    "config": {
        "get": {"--json"},
        "set": {"--strict-json", "--merge", "--dry-run"},
        "validate": {"--json"},
    },
    "gateway": {
        "restart": set(),
        "stop": set(),
    },
    "uninstall": {
        "--state",
        "--workspace",
        "--yes",
        "--non-interactive",
    },
    "hooks": {
        "list": {"--verbose", "--json"},
        "enable": set(),
        "disable": set(),
        "check": set(),
        "info": set(),
    },
    "agents": {
        "list": {"--bindings", "--json"},
        "add": {"--workspace", "--bind", "--non-interactive"},
        "delete": set(),
        "bind": {"--agent", "--bind"},
    },
}


def _is_openclaw_subprocess_call(node: ast.Call) -> bool:
    """Check if an ast.Call is ``subprocess.run(["openclaw", ...])``."""
    if not isinstance(node.func, ast.Attribute):
        return False
    if not isinstance(node.func.value, ast.Attribute):
        return False
    inner = node.func.value
    if getattr(inner, "attr", "") in ("run", "Popen"):
        return True
    return False


def _extract_openclaw_calls() -> list[dict]:
    """Walk source tree and extract all openclaw subprocess calls."""
    calls: list[dict] = []
    for py_file in SRC_DIR.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            # Match subprocess.run/Popen([...])
            if not _is_openclaw_subprocess_call(node):
                continue
            for arg in node.args:
                if isinstance(arg, ast.List):
                    elts = arg.elts
                    if not elts:
                        continue
                    first = elts[0]
                    if isinstance(first, ast.Constant) and "openclaw" in str(first.value):
                        parts = [e.value for e in elts if isinstance(e, ast.Constant)]
                        if len(parts) >= 2 and parts[0].lower() == "openclaw":
                            calls.append({
                                "file": str(py_file.relative_to(PROJECT_ROOT)),
                                "line": node.lineno,
                                "args": parts,
                            })
        # Also match direct calls like `_run(["openclaw", ...])`
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and hasattr(node.func, "id"):
                if node.func.id in ("_run", "run"):
                    for arg in node.args:
                        if isinstance(arg, ast.List):
                            elts = arg.elts
                            if not elts:
                                continue
                            first = elts[0]
                            if isinstance(first, ast.Constant) and "openclaw" in str(first.value):
                                parts = [e.value for e in elts if isinstance(e, ast.Constant)]
                                if len(parts) >= 2 and parts[0].lower() == "openclaw":
                                    calls.append({
                                        "file": str(py_file.relative_to(PROJECT_ROOT)),
                                        "line": node.lineno,
                                        "args": parts,
                                    })
    return calls


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOpenClawSubcommandExists:
    """Every openclaw subcommand in source must be a known command."""

    KNOWN_TOPLEVEL = {"cron", "config", "gateway", "hooks", "agents", "uninstall", "--version"}

    @pytest.fixture(scope="class")
    def openclaw_calls(self) -> list[dict]:
        return _extract_openclaw_calls()

    def test_all_subcommands_are_known(self, openclaw_calls: list[dict]) -> None:
        errors: list[str] = []
        for call in openclaw_calls:
            args = call["args"]
            if len(args) < 2:
                continue
            subcmd = args[1]
            if subcmd.startswith("-"):
                continue  # flag, not a command
            if subcmd == "--version":
                continue  # valid top-level flag
            if subcmd not in self.KNOWN_TOPLEVEL:
                errors.append(
                    f"{call['file']}:{call['line']}: unknown top-level command "
                    f"{subcmd!r} in {args}"
                )
        assert not errors, "\n".join(errors)

    def test_all_subsubcommands_are_known(self, openclaw_calls: list[dict]) -> None:
        errors: list[str] = []
        for call in openclaw_calls:
            args = call["args"]
            if len(args) < 3:
                continue
            subcmd, subsub = args[1], args[2]
            if subcmd.startswith("-") or subsub.startswith("-"):
                continue
            if subcmd not in OPENCLAW_COMMANDS:
                continue
            if subsub not in OPENCLAW_COMMANDS[subcmd]:
                errors.append(
                    f"{call['file']}:{call['line']}: unknown subcommand "
                    f"{subcmd} {subsub!r} in {args}"
                )
        assert not errors, "\n".join(errors)


class TestOpenClawFlagsAreValid:
    """Every flag passed to an openclaw command must be a known flag for that command."""

    @pytest.fixture(scope="class")
    def openclaw_calls(self) -> list[dict]:
        return _extract_openclaw_calls()

    def test_flags_match_docs(self, openclaw_calls: list[dict]) -> None:
        errors: list[str] = []
        for call in openclaw_calls:
            args = call["args"]
            if len(args) < 3:
                continue
            cmd = args[1]
            if cmd == "--version":
                continue
            subcmd = args[2] if len(args) > 2 and not args[2].startswith("-") else None

            if subcmd and cmd in OPENCLAW_COMMANDS and subcmd in OPENCLAW_COMMANDS[cmd]:
                valid_flags = OPENCLAW_COMMANDS[cmd][subcmd]
                # Collect flags from args
                flags_in_call = {a for a in args if a.startswith("--")}
                unknown = flags_in_call - valid_flags
                if unknown:
                    errors.append(
                        f"{call['file']}:{call['line']}: {cmd} {subcmd} "
                        f"uses unknown flags {unknown} in {args}"
                    )

        assert not errors, "\n".join(errors)


class TestOpenClawCronAddFlags:
    """Specifically verify cron add uses --cron (not --schedule) and --agent (not positional)."""

    @pytest.fixture(scope="class")
    def cron_add_calls(self) -> list[dict]:
        return [
            c
            for c in _extract_openclaw_calls()
            if len(c["args"]) >= 4
            and c["args"][1:3] == ["cron", "add"]
        ]

    def test_cron_add_uses_cron_flag(self, cron_add_calls: list[dict]) -> None:
        errors: list[str] = []
        for call in cron_add_calls:
            if "--schedule" in call["args"]:
                errors.append(
                    f"{call['file']}:{call['line']}: uses --schedule instead of --cron "
                    f"in {call['args']}"
                )
            if "--cron" not in call["args"]:
                errors.append(
                    f"{call['file']}:{call['line']}: missing --cron flag in {call['args']}"
                )
        assert not errors, "\n".join(errors)

    def test_cron_add_uses_agent_flag(self, cron_add_calls: list[dict]) -> None:
        errors: list[str] = []
        for call in cron_add_calls:
            has_agent = "--agent" in call["args"]
            first_non_flag = None
            for a in call["args"]:
                if not a.startswith("-") and a != "openclaw" and a not in ("cron", "add"):
                    first_non_flag = a
                    break
            if not has_agent and first_non_flag:
                errors.append(
                    f"{call['file']}:{call['line']}: passes positional "
                    f"{first_non_flag!r} instead of --agent in {call['args']}"
                )
        assert not errors, "\n".join(errors)


class TestOpenClawDocExists:
    """Dep_Docs/Openclaw-llms-full.txt must exist and contain key patterns."""

    def test_doc_exists(self) -> None:
        assert DEP_DOCS.is_file(), (
            f"OpenClaw doc not found at {DEP_DOCS}"
        )

    def test_doc_contains_cron_add(self) -> None:
        text = DEP_DOCS.read_text(encoding="utf-8")
        assert "openclaw cron add" in text, (
            "Dep_Docs missing 'openclaw cron add' examples"
        )

    def test_doc_contains_cron_flag(self) -> None:
        text = DEP_DOCS.read_text(encoding="utf-8")
        assert '--cron' in text, (
            "Dep_Docs missing --cron flag examples"
        )