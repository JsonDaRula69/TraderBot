"""End-to-end tests for the isolated Phase 3 QA evidence runner."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class _BenchmarkEvidence(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True, strict=True)

    sample_count: int
    median_ms: float
    p95_ms: float


class _Evidence(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True, strict=True)

    passed: bool
    cross_agent_successful_reads: int
    benchmark: _BenchmarkEvidence
    qa_root: str


def test_phase3_qa_emits_passing_evidence_and_removes_uuid_root() -> None:
    script = Path(__file__).parents[1] / "scripts" / "phase3-qa.py"
    parent_dir = tempfile.gettempdir()
    with tempfile.TemporaryDirectory(prefix="traderbot-phase3-test-", dir=parent_dir) as parent:
        data_root = Path(parent)
        evidence_path = data_root / "evidence.json"

        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--data-root",
                str(data_root),
                "--json-output",
                str(evidence_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )

        assert result.returncode == 0, result.stderr
        payload = evidence_path.read_text(encoding="utf-8")
        _ = json.loads(payload)
        evidence = _Evidence.model_validate_json(payload)
        assert evidence.passed is True
        assert evidence.cross_agent_successful_reads == 0
        assert evidence.benchmark.sample_count == 1000
        assert evidence.benchmark.median_ms < 10
        assert evidence.benchmark.p95_ms < 10
        assert not Path(evidence.qa_root).exists()


def test_phase3_qa_rejects_data_root_outside_tmp() -> None:
    script = Path(__file__).parents[1] / "scripts" / "phase3-qa.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--data-root",
            str(Path(__file__).parents[1]),
            "--json-output",
            str(Path(tempfile.gettempdir()) / "traderbot-phase3-rejected.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode != 0
    assert "must resolve under" in result.stderr
