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
from traderbot.deploy.phase45_runtime import Phase45Adapter
from traderbot.deploy.secret_step import HiddenSecretInput, SecretsSelection, select_deploy_secrets
from traderbot.deploy.validation import SecretReconciliationApprovals
from traderbot.deploy.wizard import DeployWizard
from traderbot.deploy.wizard_contracts import DeployResult, WizardPorts, WizardRequest
from traderbot.deploy.wizard_runtime import build_wizard_ports
from traderbot.deploy.wizard_state import DeployApprovals
from traderbot.kalshi.models import MarketCategory


def _request_from_config(config: DeployConfig) -> WizardRequest:
    return WizardRequest.model_validate(
        {
            "categories": tuple(config.categories),
            "mode": config.mode,
            "sysadmin_workspace": config.sysadmin_workspace,
            "category_workspaces": config.category_workspaces,
            "approvals": config.approvals,
            "heartbeat_every": config.heartbeat_every,
            "infisical_url": config.infisical_url or "http://localhost:8080",
            "kalshi_api_key_env": config.tokens.kalshi_api_key_env,
            "kalshi_private_key_pem_env": config.tokens.kalshi_private_key_pem_env,
            "secret_approvals": config.secret_approvals,
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
        MarketCategory(value.strip().lower()) for value in raw_selection.split(",") if value.strip()
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
    reconcile_incomplete = Confirm.ask(
        "Approve filling a missing Kalshi field only when the durable field matches?",
        default=False,
        console=console,
    )
    replace_existing = Confirm.ask(
        "Approve replacing malformed or differing Kalshi fields?",
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
        secret_approvals=SecretReconciliationApprovals(
            reconcile_incomplete=reconcile_incomplete,
            replace_existing=replace_existing,
        ),
    )


def _render_result(result: DeployResult, console: Console) -> None:
    implemented_through = max(step.step for step in result.steps)
    table = Table(title=f"TraderBot Deploy Steps 1-{implemented_through}")
    table.add_column("Step")
    table.add_column("Status")
    table.add_column("Detail")
    for step in result.steps:
        table.add_row(f"{step.step}. {step.name}", step.status.value, step.message)
        for agent in step.agents:
            table.add_row(f"  {agent.agent_id}", agent.status.value, agent.message)
    console.print(table)
    if result.success:
        remaining = f"{result.remaining_steps[0]}-{result.remaining_steps[-1]}"
        message = f"Steps 1-{implemented_through} completed; full deployment remains incomplete. "
        message += f"Steps {remaining} remain."
        console.print(message)
    else:
        console.print("Full deployment remains incomplete; the implemented step prefix failed.")


def execute_deploy(
    config_path: Path | None,
    json_output: bool,
    ports: WizardPorts | None = None,
) -> int:
    """Run wizard steps 1-5 from config or explicit Rich prompts."""
    console = Console()
    owned_selection: SecretsSelection | None = None
    try:
        if config_path is None:
            if ports is None:
                selection = select_deploy_secrets("http://localhost:8080")
                owned_selection = selection
                hidden = HiddenSecretInput(
                    lambda label: Prompt.ask(label, password=True, console=console)
                )
                runtime_ports = build_wizard_ports(
                    selection.store,
                    Phase45Adapter(selection, hidden.read),
                )
            else:
                runtime_ports = ports
            request = collect_interactive_request(console, runtime_ports)
        else:
            config = DeployConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
            request = _request_from_config(config)
            if ports is None:
                selection = select_deploy_secrets(request.infisical_url)
                owned_selection = selection
                runtime_ports = build_wizard_ports(
                    selection.store,
                    Phase45Adapter(selection, None),
                )
            else:
                runtime_ports = ports
    except (OSError, ValidationError, ValueError):
        if owned_selection is not None:
            owned_selection.close()
        message = "invalid deploy config or category selection; deploy steps 1-5 require backtest, "
        message += "while paper/live require Phase 7 lifecycle setup\n"
        _ = sys.stderr.write(message)
        return 2

    try:
        result = DeployWizard(runtime_ports).run(request)
    finally:
        if owned_selection is not None:
            owned_selection.close()
    if json_output:
        _ = sys.stdout.write(result.model_dump_json(indent=2) + "\n")
    else:
        _render_result(result, console)
    return 0 if result.success else 1
