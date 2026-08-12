from __future__ import annotations

import logging
import sys
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError
from pydantic_core import PydanticCustomError
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from traderbot.deploy.backfill_collector import prepare_collector_source
from traderbot.deploy.backfill_collector_types import PreparedCollector
from traderbot.deploy.backfill_reporter import RichReporter as BackfillRichReporter
from traderbot.deploy.config import DeployConfig
from traderbot.deploy.deploy_state import DeployStateError, load_deploy_state, validate_data_root
from traderbot.deploy.openclaw_models import AgentInventory
from traderbot.deploy.phase45_runtime import Phase45Adapter
from traderbot.deploy.phase678_runtime import Phase678Adapter
from traderbot.deploy.secret_step import HiddenSecretInput, select_deploy_secrets
from traderbot.deploy.validation import SecretReconciliationApprovals
from traderbot.deploy.verify_reporter import RichReporter as VerificationRichReporter
from traderbot.deploy.wizard import DeployWizard
from traderbot.deploy.wizard_contracts import DeployResult, WizardPorts, WizardRequest
from traderbot.deploy.wizard_late_steps import STUB_MESSAGE
from traderbot.deploy.wizard_request import request_from_config
from traderbot.deploy.wizard_runtime import build_wizard_ports
from traderbot.deploy.wizard_state import DeployApprovals
from traderbot.kalshi.order_models import MarketCategory


@dataclass(frozen=True, slots=True)
class _PreparedDeploy:
    request: WizardRequest
    ports: WizardPorts
    resources: ExitStack


def _prepare_deploy(
    config_path: Path | None,
    ports: WizardPorts | None,
    console: Console,
) -> _PreparedDeploy:
    resources = ExitStack()
    if config_path is None:
        if ports is not None:
            request = collect_interactive_request(console, ports)
            return _PreparedDeploy(request, ports, resources)
        selection = select_deploy_secrets("http://localhost:8080")
        _ = resources.callback(selection.close)
        hidden = HiddenSecretInput(lambda label: Prompt.ask(label, password=True, console=console))
        runtime_ports = build_wizard_ports(
            selection.store,
            Phase45Adapter(selection, hidden.read),
        )
        runtime_ports = WizardPorts(
            openclaw=runtime_ports.openclaw,
            tokens=runtime_ports.tokens,
            injector=runtime_ports.injector,
            phase45=runtime_ports.phase45,
            phase678=Phase678Adapter(),
        )
        request = collect_interactive_request(console, runtime_ports)
        return _PreparedDeploy(request, runtime_ports, resources)
    config = DeployConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
    request = request_from_config(config)
    _ = validate_data_root(request.data_root)
    prepared_state = load_deploy_state(request.data_root)
    prepared_collector: PreparedCollector | None = None
    if request.collector_db is not None:
        prepared_collector = resources.enter_context(prepare_collector_source(request.collector_db))
    if ports is not None:
        return _PreparedDeploy(request, ports, resources)
    selection = select_deploy_secrets(request.infisical_url)
    _ = resources.callback(selection.close)
    runtime_ports = build_wizard_ports(
        selection.store,
        Phase45Adapter(selection, None, request.data_root),
    )
    runtime_ports = WizardPorts(
        openclaw=runtime_ports.openclaw,
        tokens=runtime_ports.tokens,
        injector=runtime_ports.injector,
        phase45=runtime_ports.phase45,
        phase678=Phase678Adapter(prepared_collector, prepared_state),
    )
    return _PreparedDeploy(request, runtime_ports, resources)


def collect_interactive_request(console: Console, ports: WizardPorts) -> WizardRequest:
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
    for step in result.steps:
        if step.backfill is not None:
            BackfillRichReporter(console).render(step.backfill)
        if step.step == 7:
            console.print(STUB_MESSAGE, soft_wrap=True)
        if step.verification is not None:
            VerificationRichReporter(console).render(step.verification)
    if result.deployment_complete:
        console.print("All eight deploy steps completed.")
    elif result.success:
        remaining = f"{result.remaining_steps[0]}-{result.remaining_steps[-1]}"
        prefix = f"Steps 1-{implemented_through} completed; full deployment remains incomplete."
        console.print(f"{prefix} Steps {remaining} remain.")
    else:
        console.print("Full deployment remains incomplete; the implemented step prefix failed.")


def execute_deploy(
    config_path: Path | None,
    json_output: bool,
    ports: WizardPorts | None = None,
) -> int:
    """Run wizard steps 1-5 from config or explicit Rich prompts."""
    previous_logging_level = logging.root.manager.disable
    if json_output:
        logging.disable(logging.CRITICAL)
    try:
        return _execute_deploy(config_path, json_output, ports)
    finally:
        logging.disable(previous_logging_level)


def _execute_deploy(
    config_path: Path | None,
    json_output: bool,
    ports: WizardPorts | None,
) -> int:
    console = Console(stderr=True)
    try:
        prepared = _prepare_deploy(config_path, ports, console)
    except (DeployStateError, OSError, ValidationError, ValueError) as exc:
        message = "invalid deploy config or category selection; deploy steps 1-5 require backtest, "
        message += "while paper/live require Phase 7 lifecycle setup\n"
        if json_output:
            _ = sys.stdout.write('{"error":"invalid_request"}\n')
        else:
            _ = sys.stderr.write(message if not str(exc) else f"{message.strip()}: {exc}\n")
        return 2
    try:
        with prepared.resources:
            result = DeployWizard(prepared.ports).run(prepared.request)
    except (OSError, RuntimeError, ValidationError, ValueError):
        if json_output:
            _ = sys.stdout.write('{"error":"runtime_failure"}\n')
        else:
            _ = sys.stderr.write("Deploy runtime or cleanup failed\n")
        return 1
    if json_output:
        _ = sys.stdout.write(result.model_dump_json() + "\n")
    else:
        try:
            _render_result(result, console)
        except (OSError, RuntimeError, ValueError):
            _ = sys.stderr.write("Deploy reporting failed\n")
            return 1
    if not result.input_valid:
        return 2
    return 0 if result.success else 1
