from __future__ import annotations

from tests.deploy_wizard_fakes import FakePhase678
from traderbot.deploy.phase45_runtime import Phase45Adapter
from traderbot.deploy.secret_step import select_deploy_secrets
from traderbot.deploy.wizard_contracts import WizardPorts
from traderbot.deploy.wizard_runtime import build_wizard_ports


class Provider:
    def build(self) -> WizardPorts:
        selection = select_deploy_secrets("http://localhost:8080")
        ports = build_wizard_ports(selection.store, Phase45Adapter(selection, None))
        return WizardPorts(
            ports.openclaw,
            ports.tokens,
            ports.injector,
            ports.phase45,
            FakePhase678(),
        )


provider = Provider()
