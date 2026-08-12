from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from traderbot.deploy.wizard_contracts import WizardPorts


@runtime_checkable
class DeployProvider(Protocol):
    def build(self) -> WizardPorts: ...


def injected_ports() -> WizardPorts | None:
    reference = os.environ.get("TRADERBOT_DEPLOY_PROVIDER")
    if reference is None:
        return None
    module_name, separator, attribute = reference.partition(":")
    if not separator or not module_name or not attribute:
        return None
    if attribute != "provider":
        return None
    if os.environ.get("TRADERBOT_TEST_PROVIDER_ALLOWED") != "1":
        return None
    if module_name == "tests.deploy_cli_provider":
        from tests.deploy_cli_provider import provider

        return provider.build()
    if module_name == "traderbot.deploy.installed_test_provider":
        from traderbot.deploy.installed_test_provider import provider

        return provider.build()
    return None


__all__ = ["DeployProvider", "injected_ports"]
