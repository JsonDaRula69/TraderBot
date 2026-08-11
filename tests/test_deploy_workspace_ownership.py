from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.deploy_safety_fakes import SafetyEnvironment
from traderbot.deploy.wizard import DeployWizard, WizardRequest
from traderbot.kalshi.models import MarketCategory


def test_samefile_alias_across_agent_ids_fails_global_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: distinct lexical roots that the filesystem identifies as one directory
    main = tmp_path / "main"
    weather = tmp_path / "weather"
    main.mkdir()
    weather.mkdir()
    original = os.path.samefile

    def samefile(left: str | os.PathLike[str], right: str | os.PathLike[str]) -> bool:
        if {Path(left), Path(right)} == {main, weather}:
            return True
        return original(left, right)

    monkeypatch.setattr(os.path, "samefile", samefile)
    environment = SafetyEnvironment({"main": main, "weather": weather})

    # When: all configured workspace identities are compared
    result = DeployWizard(environment.ports()).run(
        WizardRequest(categories=(MarketCategory.WEATHER,), mode="backtest")
    )

    # Then: alias ownership fails before any selected mutation
    assert result.success is False
    assert environment.mutations == ()
