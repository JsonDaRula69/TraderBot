from __future__ import annotations

import sys
from pathlib import Path

from pydantic import ValidationError
from pydantic_core import PydanticCustomError
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from traderbot.deploy.config import DeployConfig
from traderbot.deploy.openclaw_models import AgentInventory
from traderbot.deploy.wizard import DeployWizard
from traderbot.deploy.wizard_contracts import DeployResult, WizardPorts, WizardRequest
from traderbot.deploy.wizard_runtime import build_wizard_ports
from traderbot.deploy.wizard_state import DeployApprovals
from traderbot.kalshi.models import MarketCategory
from traderbot.secrets.resolver import build_secrets_store


def _request_from_config(config: DeployConfig) -> WizardRequest:
    return WizardRequest.model_validate(
        {
            "categories": tuple(config.categories),
            "mode": config.mode,
            "sysadmin_workspace": config.sysadmin_workspace,
            "category_workspaces": config.category_workspaces,
            "approvals": config.approvals,
            "heartbeat_every": config.heartbeat_every,
        }
    )


def collect_interactive_request(console: Console, ports: WizardPorts) -> WizardRequest:
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
    parsed_values = tuple(
        MarketCategory(value.strip().lower())
        for value in raw_selection.split(",")
        if value.strip()
    )
    if not parsed_values or len(set(parsed_values)) != len(parsed_values):
        raise PydanticCustomError(
            "category_selection",
            "select one or more distinct market categories",
        )
    selected = tuple(category for category in MarketCategory if category in parsed_values)
    installed = ports.openclaw.detect() is not None
    install_approved = not installed and Confirm.ask(
        "OpenClaw is absent. Approve installation?",
        default=False,
        console=console,
    )
    inventory = ports.openclaw.inventory_agents() if installed else AgentInventory([])
    if inventory is None:
        raise PydanticCustomError("agent_inventory", "OpenClaw agent inventory is unreadable")
    indexed = {agent.id: agent for agent in inventory.root}
    main = indexed.get("main")
    if main is not None:
        console.print(f"Existing main workspace: {main.workspace}")
    setup_approved = main is None and Confirm.ask(
        "OpenClaw main is absent. Approve baseline setup?",
        default=False,
        console=console,
    )
    category_workspaces: dict[MarketCategory, Path] = {}
    missing: list[MarketCategory] = []
    for category in selected:
        agent = indexed.get(category.value)
        if agent is not None:
            console.print(f"Existing {category.value} workspace: {agent.workspace}")
            continue
        proposed = Path.home() / ".openclaw" / f"workspace-{category.value}"
        workspace = Path(
            Prompt.ask(
                f"New {category.value} absolute workspace",
                default=str(proposed),
                console=console,
            )
        )
        category_workspaces[category] = workspace
        missing.append(category)
    create_approved = not missing or Confirm.ask(
        "Approve creation of only the listed missing agents at these paths?",
        default=False,
        console=console,
    )
    heartbeat_approved = Confirm.ask(
        "Approve dormant Gateway heartbeat state (0m) for main and selected agents?",
        default=False,
        console=console,
    )
    return WizardRequest(
        categories=selected,
        mode="backtest",
        sysadmin_workspace=None,
        category_workspaces=category_workspaces,
        approvals=DeployApprovals(
            install_openclaw=install_approved,
            setup_openclaw=setup_approved,
            create_agents=create_approved,
            heartbeat_change=heartbeat_approved,
        ),
        heartbeat_every="0m" if heartbeat_approved else "preserve",
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
    runtime_ports = ports or build_wizard_ports(build_secrets_store())
    try:
        if config_path is None:
            request = collect_interactive_request(console, runtime_ports)
        else:
            config = DeployConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
            request = _request_from_config(config)
    except (OSError, ValidationError, ValueError):
        message = "invalid deploy config or category selection; steps 1-3 require backtest, "
        message += "while paper/live require Phase 7 lifecycle setup\n"
        _ = sys.stderr.write(message)
        return 2

    result = DeployWizard(runtime_ports).run(request)
    if json_output:
        _ = sys.stdout.write(result.model_dump_json(indent=2) + "\n")
    else:
        _render_result(result, console)
    return 0 if result.success else 1
