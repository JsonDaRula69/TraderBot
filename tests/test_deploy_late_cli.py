from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.deploy_wizard_fakes import FakeEnvironment, FakePhase45, FakePhase678
from traderbot.deploy.wizard_command import execute_deploy
from traderbot.deploy.wizard_contracts import DeployResult
from traderbot.deploy.wizard_late_steps import STUB_MESSAGE


def _config(tmp_path: Path) -> Path:
    path = tmp_path / "deploy.json"
    _ = path.write_text(
        json.dumps(
            {
                "categories": ["weather"],
                "mode": "backtest",
                "category_workspaces": {"weather": str(tmp_path / "weather")},
                "approvals": {
                    "install_openclaw": False,
                    "setup_openclaw": False,
                    "create_agents": True,
                    "heartbeat_change": False,
                },
                "heartbeat_every": "preserve",
                "data_root": str(tmp_path / "data"),
            }
        ),
        encoding="utf-8",
    )
    return path


def test_complete_json_is_one_line_without_stderr(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: complete typed late-step fakes and config mode.
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=FakePhase678())

    # When: deploy renders machine output.
    code = execute_deploy(_config(tmp_path), True, environment.ports())

    # Then: one deploy envelope embeds both typed results with no nested streams.
    captured = capsys.readouterr()
    payload = DeployResult.model_validate_json(captured.out)
    assert code == 0
    assert len(captured.out.splitlines()) == 1
    assert captured.err == ""
    assert payload.steps[5].backfill is not None
    assert payload.steps[5].backfill.status == "complete"
    assert payload.steps[7].verification is not None
    assert payload.steps[7].verification.overall == "ok"


def test_human_output_uses_stderr_and_prints_stub_once(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: complete typed late-step fakes and human mode.
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=FakePhase678())

    # When: deploy renders the Rich flow.
    code = execute_deploy(_config(tmp_path), False, environment.ports())

    # Then: headings, both shared reports, and the exact stub are ordered on stderr.
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == ""
    assert captured.err.count(STUB_MESSAGE) == 1
    assert captured.err.index("TraderBot Deploy Steps 1-8") < captured.err.index(
        "TraderBot Backfill"
    )
    assert captured.err.index("TraderBot Backfill") < captured.err.index(STUB_MESSAGE)
    assert captured.err.index(STUB_MESSAGE) < captured.err.index("TraderBot Verification")
