from __future__ import annotations

import sys
from pathlib import Path

from pydantic import ValidationError
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from traderbot.deploy.config import DeployConfig
from traderbot.deploy.wizard import DeployResult, DeployWizard, WizardPorts, WizardRequest
from traderbot.deploy.wizard_runtime import build_wizard_ports
from traderbot.kalshi.models import MarketCategory
from traderbot.secrets.resolver import build_secrets_store


def _request_from_config(config: DeployConfig) -> WizardRequest:
    home = Path.home()
    sysadmin_workspace = config.sysadmin_workspace or home / ".openclaw" / "workspace"
    derived_workspaces = {
        category: config.category_workspaces.get(
            category,
            home / ".openclaw" / f"workspace-{category.value}",
        )
        for category in config.categories
    }
    category_workspaces = derived_workspaces | config.category_workspaces
    return WizardRequest.model_validate(
        {
            "categories": tuple(config.categories),
            "mode": config.mode,
            "sysadmin_workspace": sysadmin_workspace,
            "category_workspaces": category_workspaces,
        }
    )


def collect_interactive_request(console: Console) -> WizardRequest:
    """Collect explicit category and workspace choices through Rich."""
    table = Table(title="TraderBot Market Categories")
    table.add_column("Category")
    table.add_column("Agent ID")
    for category in MarketCategory:
        table.add_row(category.value.replace("_", " ").title(), category.value)
    console.print(table)

    raw_selection = Prompt.ask(
        "Select one or more agent IDs (comma-separated)",
        console=console,
    )
    selected = tuple(
        MarketCategory(value.strip().lower())
        for value in raw_selection.split(",")
        if value.strip()
    )
    sysadmin_workspace = Path(
        Prompt.ask(
            "SysAdmin main-agent workspace",
            default=str(Path.home() / ".openclaw" / "workspace"),
            console=console,
        )
    )
    category_workspaces = {
        category: Path(
            Prompt.ask(
                f"Workspace for {category.value}",
                default=str(Path.home() / ".openclaw" / f"workspace-{category.value}"),
                console=console,
            )
        )
        for category in MarketCategory
        if category in selected
    }
    return WizardRequest(
        categories=selected,
        mode="backtest",
        sysadmin_workspace=sysadmin_workspace,
        category_workspaces=category_workspaces,
    )


def _render_result(result: DeployResult, console: Console) -> None:
    table = Table(title="TraderBot Deploy Steps 1-3")
    table.add_column("Step")
    table.add_column("Status")
    table.add_column("Detail")
    for step in result.steps:
        table.add_row(f"{step.step}. {step.name}", step.status.value, step.message)
        for agent in step.agents:
            table.add_row(f"  {agent.agent_id}", agent.status.value, agent.message)
    console.print(table)
    if result.success:
        console.print("Steps 1-3 completed; full deployment remains incomplete. Steps 4-8 remain.")
    else:
        console.print("Full deployment remains incomplete; steps 1-3 did not complete.")


def execute_deploy(
    config_path: Path | None,
    json_output: bool,
    ports: WizardPorts | None = None,
) -> int:
    """Run wizard steps 1-3 from config or explicit Rich prompts."""
    console = Console()
    try:
        if config_path is None:
            request = collect_interactive_request(console)
        else:
            config = DeployConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
            request = _request_from_config(config)
    except (OSError, ValidationError, ValueError):
        message = "invalid deploy config or category selection; steps 1-3 require backtest, "
        message += "while paper/live require Phase 7 lifecycle setup\n"
        _ = sys.stderr.write(message)
        return 2

    runtime_ports = ports or build_wizard_ports(build_secrets_store())
    result = DeployWizard(runtime_ports).run(request)
    if json_output:
        _ = sys.stdout.write(result.model_dump_json(indent=2) + "\n")
    else:
        _render_result(result, console)
    return 0 if result.success else 1
