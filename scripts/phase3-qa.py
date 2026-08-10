#!/usr/bin/env python3
"""Run isolated Phase 3 database and Chroma QA probes."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, TypedDict, override

if TYPE_CHECKING:
    from scripts.phase3_qa_checks import (
        BenchmarkEvidence,
        CheckEvidence,
        benchmark,
        category_delete_check,
        isolation_check,
        migration_check,
        rollback_check,
    )
else:
    from phase3_qa_checks import (
        BenchmarkEvidence,
        CheckEvidence,
        benchmark,
        category_delete_check,
        isolation_check,
        migration_check,
        rollback_check,
    )

from traderbot.db.pool import SQLiteConnectionPool

_TMP_ROOT: Final = Path("/tmp").resolve()
_QA_PREFIX: Final = "traderbot-phase3-qa-"


class Phase3Evidence(TypedDict):
    qa_root: str
    passed: bool
    cross_agent_successful_reads: int
    checks: dict[str, CheckEvidence]
    benchmark: BenchmarkEvidence


@dataclass(frozen=True, slots=True)
class Arguments:
    data_root: Path
    json_output: Path


@dataclass(frozen=True, slots=True)
class InvalidDataRootError(ValueError):
    path: Path

    @override
    def __str__(self) -> str:
        return f"--data-root must resolve under /tmp: {self.path}"


def _arguments(argv: Sequence[str] | None) -> Arguments:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--data-root", required=True)
    _ = parser.add_argument("--json-output", required=True)
    namespace = parser.parse_args(argv)
    data_root = namespace.data_root
    json_output = namespace.json_output
    if not isinstance(data_root, str) or not isinstance(json_output, str):
        parser.error("paths must be strings")
    return Arguments(Path(data_root), Path(json_output))


def _validated_parent(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_relative_to(_TMP_ROOT):
        raise InvalidDataRootError(resolved)
    return resolved


def _run(parent: Path, json_output: Path) -> Phase3Evidence:
    qa_root = parent / f"{_QA_PREFIX}{uuid.uuid4()}"
    home = qa_root / "home"
    data_root = home / ".traderbot"
    original_home = os.environ.get("HOME")
    original_userprofile = os.environ.get("USERPROFILE")
    pool = SQLiteConnectionPool()
    try:
        data_root.mkdir(parents=True)
        os.environ["HOME"] = str(home)
        os.environ["USERPROFILE"] = str(home)
        migration = migration_check(data_root)
        rollback = rollback_check(data_root)
        isolation = isolation_check(data_root, pool)
        category_delete = category_delete_check(data_root)
        benchmark_result = benchmark(data_root, pool)
        checks = {
            "migration": migration,
            "rollback": rollback,
            "isolation": isolation.check,
            "category_delete": category_delete,
        }
        evidence: Phase3Evidence = {
            "qa_root": str(qa_root),
            "passed": all(check["passed"] for check in checks.values())
            and benchmark_result["passed"],
            "cross_agent_successful_reads": isolation.cross_agent_successful_reads,
            "checks": checks,
            "benchmark": benchmark_result,
        }
        _ = json_output.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return evidence
    finally:
        pool.shutdown()
        if original_home is None:
            _ = os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = original_home
        if original_userprofile is None:
            _ = os.environ.pop("USERPROFILE", None)
        else:
            os.environ["USERPROFILE"] = original_userprofile
        shutil.rmtree(qa_root, ignore_errors=False)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the isolated QA probes and return a process exit code."""
    arguments = _arguments(argv)
    try:
        parent = _validated_parent(arguments.data_root)
    except InvalidDataRootError as error:
        print(error, file=sys.stderr)
        return 2
    evidence = _run(parent, arguments.json_output)
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
