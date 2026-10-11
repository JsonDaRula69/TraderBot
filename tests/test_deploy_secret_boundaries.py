"""Public config and request boundary regressions for deploy secrets."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from traderbot.deploy.config import DeployConfig
from traderbot.deploy.wizard_contracts import WizardRequest
from traderbot.kalshi.models import MarketCategory


@pytest.mark.parametrize(
    ("api_environment", "pem_environment", "origin"),
    [
        ("ONLY_ONE", None, "http://localhost:8080"),
        ("bad-name", "VALID_NAME", "http://localhost:8080"),
        (None, None, "https://remote.example"),
    ],
)
def test_wizard_request_independently_rejects_unsafe_secret_boundaries(
    api_environment: str | None,
    pem_environment: str | None,
    origin: str,
) -> None:
    # Given/When/Then: direct public request parsing rejects config-bypass inputs.
    with pytest.raises(ValidationError):
        _ = WizardRequest(
            categories=(MarketCategory.WEATHER,),
            mode="backtest",
            kalshi_api_key_env=api_environment,
            kalshi_private_key_pem_env=pem_environment,
            infisical_url=origin,
        )


def test_config_replacement_approval_requires_complete_references(tmp_path: Path) -> None:
    # Given: replacement approval without a source pair.
    payload = {
        "categories": ["weather"],
        "mode": "backtest",
        "category_workspaces": {"weather": str(tmp_path / "weather")},
        "approvals": {
            "install_openclaw": False,
            "setup_openclaw": False,
            "create_agents": False,
            "heartbeat_change": False,
        },
        "heartbeat_every": "preserve",
        "secret_approvals": {"replace_existing": True},
    }

    # When/Then: the noninteractive boundary rejects unusable approval state.
    with pytest.raises(ValidationError):
        _ = DeployConfig.model_validate(payload)
