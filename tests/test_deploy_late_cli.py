from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.deploy_wizard_fakes import FakeEnvironment, FakePhase45, FakePhase678
from traderbot.deploy.wizard_command import execute_deploy
from traderbot.deploy.wizard_contracts import DeployResult
from traderbot.deploy.wizard_late_steps import PHASE5_SANDBOX_ENV


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
                    "sandbox_apply": True,
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: complete typed late-step fakes, config mode, and the apply lane on.
    monkeypatch.setenv(PHASE5_SANDBOX_ENV, "1")
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=FakePhase678())

    # When: deploy renders machine output.
    code = execute_deploy(_config(tmp_path), True, environment.ports())

    # Then: one deploy envelope embeds the late typed results with no nested streams.
    captured = capsys.readouterr()
    payload = DeployResult.model_validate_json(captured.out)
    assert code == 0
    assert len(captured.out.splitlines()) == 1
    assert captured.err == ""
    assert payload.steps[5].backfill is not None
    assert payload.steps[5].backfill.status == "complete"
    assert payload.steps[6].action == "docker_sandbox_applied"
    assert payload.steps[6].sandbox_report is not None
    assert len(payload.steps[6].sandbox_report.plan) == 10
    assert payload.steps[7].verification is not None
    assert payload.steps[7].verification.overall == "ok"


def test_human_output_uses_stderr_and_prints_sandbox_summary_once(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: complete typed late-step fakes, human mode, and the apply lane on.
    monkeypatch.setenv(PHASE5_SANDBOX_ENV, "1")
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=FakePhase678())

    # When: deploy renders the Rich flow.
    code = execute_deploy(_config(tmp_path), False, environment.ports())

    # Then: headings and both shared reports are ordered on stderr, with the
    # docker-sandbox image summary printed exactly once between them.
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == ""
    assert captured.err.count("Docker sandbox image traderbot-sandbox:") == 1
    assert captured.err.index("TraderBot Deploy Steps 1-8") < captured.err.index(
        "TraderBot Backfill"
    )
    assert captured.err.index("TraderBot Backfill") < captured.err.index(
        "Docker sandbox image traderbot-sandbox:"
    )
    assert captured.err.index("Docker sandbox image") < captured.err.index("TraderBot Verification")


def test_human_output_names_the_opt_in_env_var_when_the_lane_is_off(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the apply lane opt-in was never set.
    monkeypatch.delenv(PHASE5_SANDBOX_ENV, raising=False)
    late = FakePhase678()
    environment = FakeEnvironment(phase45=FakePhase45(), phase678=late)
    late.openclaw = environment.openclaw

    # When: deploy renders the Rich flow.
    code = execute_deploy(_config(tmp_path), False, environment.ports())

    # Then: step 7 records the typed opt-in skip, zero config writes happen,
    # the notice names the dedicated env var, and the deployment reports
    # incomplete (steps 7-8 skipped).
    captured = capsys.readouterr()
    assert code != 0
    assert captured.err.count(f"{PHASE5_SANDBOX_ENV}=1") >= 1
    assert environment.openclaw.config_events == []
    assert environment.openclaw.config == {"main": {}, "weather": {}}
