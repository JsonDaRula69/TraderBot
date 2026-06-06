"""Profile management commands."""

from __future__ import annotations

import json as json_lib
import logging
import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from traderbot.cli.helpers import (
    _mask_token,
    _resolve_agent_path,
    _write_token_to_env,
)

logger = logging.getLogger(__name__)

profile_app = typer.Typer(
    name="profile",
    help="Manage trading profiles for multi-agent deployment.",
    rich_markup_mode="rich",
)


def _install_news_ingest_timer(agent_user, interval_minutes=30, console=None):
    from traderbot.cli.cron import _install_news_ingest_timer as _f

    return _f(agent_user, interval_minutes, console)


def _interactive_profile_create(console: Console, registry) -> None:
    """Walk user through profile creation with numbered selections."""
    from traderbot.kalshi.models import MarketCategory
    from traderbot.profiles.models import TradingProfile
    from traderbot.risk.limits import HARD_LIMITS

    console.print("\n[bold]=== TraderBot Profile Setup ===[/bold]\n")

    profile_name = ""
    while not profile_name:
        profile_name = typer.prompt("Profile name")
        if not profile_name:
            console.print("[red]Profile name cannot be empty.[/red]")

    if registry.profile_exists(profile_name):
        console.print(f"[yellow]Profile '{profile_name}' already exists.[/yellow]")
        console.print("  [1] Overwrite")
        console.print("  [2] Choose a different name")
        console.print("  [3] Cancel")
        choice = typer.prompt("Select", default="3")
        if choice == "1":
            registry.delete_profile(profile_name)
        elif choice == "2":
            profile_name = typer.prompt("New profile name")
        else:
            console.print("[dim]Cancelled.[/dim]")
            return

    console.print("\n[bold]Trading mode:[/bold]")
    console.print("  1) paper  (recommended — no real money at risk)")
    console.print("  2) live   (real money — use with caution)")
    mode_choice = typer.prompt("Choice", default="1")
    profile_mode = "live" if mode_choice == "2" else "paper"

    description = typer.prompt("Description", default=f"{profile_name} trading profile")

    console.print("\n[bold]Market categories[/bold] (comma-separated numbers, or 'a' for all):")
    cat_keys = [c.value for c in MarketCategory]
    cat_labels = [c.name.replace("_", " ").title() for c in MarketCategory]
    for i, label in enumerate(cat_labels, 1):
        console.print(f"  {i:2d}) {label}")
    console.print("   a) All categories")
    cat_input = typer.prompt("Choice", default="a")
    enabled_categories = []
    if cat_input.lower() in ("a", ""):
        enabled_categories = list(MarketCategory)
    else:
        for num in cat_input.split(","):
            num = num.strip()
            if num.isdigit() and 1 <= int(num) <= len(cat_keys):
                cat_val = cat_keys[int(num) - 1]
                try:
                    enabled_categories.append(MarketCategory(cat_val))
                except ValueError:
                    pass

    console.print("\n[bold]Risk Parameters[/bold] (press Enter for defaults):")

    risk_mult_str = typer.prompt("  Risk multiplier (0-1)", default="1.0")
    risk_multiplier = float(risk_mult_str) if risk_mult_str else 1.0

    max_pos_str = typer.prompt(
        "  Max position per market %", default=str(HARD_LIMITS["max_position_per_market_pct"])
    )
    max_position_pct = (
        float(max_pos_str) if max_pos_str else HARD_LIMITS["max_position_per_market_pct"]
    )

    max_dl_str = typer.prompt("  Max daily loss %", default=str(HARD_LIMITS["max_daily_loss_pct"]))
    max_daily_loss_pct = float(max_dl_str) if max_dl_str else HARD_LIMITS["max_daily_loss_pct"]

    max_dd_str = typer.prompt("  Max drawdown %", default=str(HARD_LIMITS["max_drawdown_pct"]))
    max_drawdown_pct = float(max_dd_str) if max_dd_str else HARD_LIMITS["max_drawdown_pct"]

    max_op_str = typer.prompt(
        "  Max open positions", default=str(HARD_LIMITS["max_open_positions"])
    )
    max_open_positions = int(max_op_str) if max_op_str else int(HARD_LIMITS["max_open_positions"])

    min_liq_str = typer.prompt(
        "  Min liquidity", default=str(HARD_LIMITS["min_liquidity_threshold"])
    )
    min_liquidity = int(min_liq_str) if min_liq_str else int(HARD_LIMITS["min_liquidity_threshold"])

    min_edge_str = typer.prompt("  Min edge %", default=str(HARD_LIMITS["min_edge_pct"]))
    min_edge_pct = float(min_edge_str) if min_edge_str else HARD_LIMITS["min_edge_pct"]

    initial_bal_str = typer.prompt("  Initial balance ($)", default="100")
    initial_balance_cents = int(float(initial_bal_str) * 100) if initial_bal_str else 10000

    profile_data = {
        "name": profile_name,
        "mode": profile_mode,
        "description": description,
        "enabled_categories": enabled_categories,
        "risk_multiplier": risk_multiplier,
        "max_position_per_market_pct": max_position_pct,
        "max_daily_loss_pct": max_daily_loss_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "max_open_positions": max_open_positions,
        "min_liquidity_threshold": min_liquidity,
        "min_edge_pct": min_edge_pct,
        "initial_balance_cents": initial_balance_cents,
    }

    try:
        profile = TradingProfile(**profile_data)
        registry.create_profile(profile)
        console.print(f"\n[green]✓[/green] Created profile '{profile_name}' in {profile_mode} mode")
        if profile_mode == "paper":
            console.print(f"  Initial balance: ${initial_balance_cents / 100:.2f}")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


def _interactive_profile_select(profiles: list[str], console: Console) -> str | None:
    from traderbot.profiles.registry import ProfileRegistry

    registry = ProfileRegistry()
    console.print("\n[bold]Select a profile:[/bold]")
    for i, p_name in enumerate(profiles, 1):
        profile = registry.get_profile(p_name)
        desc = f" — {profile.description}" if profile and profile.description else ""
        mode = f" [{profile.mode}]" if profile else ""
        console.print(f"  {i}. {p_name}{mode}{desc}")

    try:
        choice = typer.prompt("Enter number", type=int)
    except (ValueError, KeyboardInterrupt):
        return None

    if choice < 1 or choice > len(profiles):
        console.print("[red]Invalid selection[/red]")
        return None

    return profiles[choice - 1]


def _interactive_profile_action(name: str, console: Console, registry) -> None:
    profile = registry.get_profile(name)
    if profile is None:
        console.print(f"[red]Error:[/red] Profile '{name}' not found")
        raise typer.Exit(1)

    console.print(f"\n[bold]Profile: {name}[/bold] ({profile.mode})")
    console.print(f"  Description:    {profile.description}")
    console.print(
        f"  Categories:     {', '.join(str(c.value) for c in profile.enabled_categories) if profile.enabled_categories else 'all'}"
    )
    console.print(f"  Risk multiplier:{profile.risk_multiplier:.1%}")
    console.print(f"  Max position:   {profile.max_position_per_market_pct:.1%}")
    console.print(f"  Max daily loss:  {profile.max_daily_loss_pct:.1%}")
    console.print(f"  Max drawdown:    {profile.max_drawdown_pct:.1%}")
    console.print(f"  Max open pos:   {profile.max_open_positions}")
    console.print(f"  Min liquidity:   {profile.min_liquidity_threshold}")
    console.print(f"  Min edge:        {profile.min_edge_pct:.1%}")

    console.print("\n[bold]Actions:[/bold]")
    console.print("  1. Edit profile")
    console.print("  2. Delete profile")
    console.print("  3. Assign agent")
    console.print("  4. Exit")

    try:
        action = typer.prompt("Choose action", type=int)
    except (ValueError, KeyboardInterrupt):
        return

    if action == 1:
        _interactive_edit_profile(name, profile, console, registry)
    elif action == 2:
        _interactive_delete_profile(name, console, registry)
    elif action == 3:
        _interactive_assign_agent(name, console, registry)


def _interactive_edit_profile(name: str, profile, console: Console, registry) -> None:
    from traderbot.kalshi.models import MarketCategory

    update_kwargs: dict = {}

    console.print(f"\n[bold]Editing profile '{name}'[/bold] (press Enter to keep current value)")

    new_mode = typer.prompt(f"  Mode [{profile.mode}]", default="", show_default=False)
    if new_mode:
        if new_mode not in ("paper", "live"):
            console.print("[red]Error:[/red] mode must be 'paper' or 'live'")
            return
        update_kwargs["mode"] = new_mode

    new_desc = typer.prompt("  Description", default=profile.description)
    if new_desc != profile.description:
        update_kwargs["description"] = new_desc

    current_cats = (
        ", ".join(str(c.value) for c in profile.enabled_categories)
        if profile.enabled_categories
        else ""
    )
    new_cats = typer.prompt(
        f"  Categories [{current_cats or 'all'}]", default="", show_default=False
    )
    if new_cats:
        try:
            update_kwargs["enabled_categories"] = [
                MarketCategory(cat.strip().lower()) for cat in new_cats.split(",")
            ]
        except ValueError as e:
            console.print(f"[red]Error:[/red] Invalid category: {e}")
            return

    new_rm = typer.prompt(
        f"  Risk multiplier [{profile.risk_multiplier}]", default="", show_default=False
    )
    if new_rm:
        try:
            update_kwargs["risk_multiplier"] = float(new_rm)
        except ValueError:
            console.print("[red]Invalid number[/red]")
            return

    new_mp = typer.prompt(
        f"  Max position per market % [{profile.max_position_per_market_pct}]",
        default="",
        show_default=False,
    )
    if new_mp:
        try:
            update_kwargs["max_position_per_market_pct"] = float(new_mp)
        except ValueError:
            console.print("[red]Invalid number[/red]")
            return

    new_ml = typer.prompt(
        f"  Max daily loss % [{profile.max_daily_loss_pct}]", default="", show_default=False
    )
    if new_ml:
        try:
            update_kwargs["max_daily_loss_pct"] = float(new_ml)
        except ValueError:
            console.print("[red]Invalid number[/red]")
            return

    new_md = typer.prompt(
        f"  Max drawdown % [{profile.max_drawdown_pct}]", default="", show_default=False
    )
    if new_md:
        try:
            update_kwargs["max_drawdown_pct"] = float(new_md)
        except ValueError:
            console.print("[red]Invalid number[/red]")
            return

    new_op = typer.prompt(
        f"  Max open positions [{profile.max_open_positions}]", default="", show_default=False
    )
    if new_op:
        try:
            update_kwargs["max_open_positions"] = int(new_op)
        except ValueError:
            console.print("[red]Invalid number[/red]")
            return

    new_lq = typer.prompt(
        f"  Min liquidity threshold [{profile.min_liquidity_threshold}]",
        default="",
        show_default=False,
    )
    if new_lq:
        try:
            update_kwargs["min_liquidity_threshold"] = int(new_lq)
        except ValueError:
            console.print("[red]Invalid number[/red]")
            return

    new_edge = typer.prompt(
        f"  Min edge % [{profile.min_edge_pct}]", default="", show_default=False
    )
    if new_edge:
        try:
            update_kwargs["min_edge_pct"] = float(new_edge)
        except ValueError:
            console.print("[red]Invalid number[/red]")
            return

    if not update_kwargs:
        console.print("[yellow]No changes made[/yellow]")
        return

    try:
        registry.update_profile(name, **update_kwargs)
        console.print(f"[green]✓[/green] Updated profile '{name}'")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")


def _interactive_delete_profile(name: str, console: Console, registry) -> None:
    confirm = typer.prompt(f"Delete profile '{name}'? Type 'yes' to confirm")
    if confirm.lower() != "yes":
        console.print("[yellow]Cancelled[/yellow]")
        return

    try:
        registry.delete_profile(name)
        console.print(f"[green]✓[/green] Deleted profile '{name}'")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")


def _interactive_assign_agent(name: str, console: Console, registry) -> None:
    from traderbot.profiles.discovery import discover_agents
    from traderbot.profiles.injection import propagate_workspace_files
    from traderbot.profiles.tokens import TokenAlreadyAssignedError, assign_token, generate_token

    agents = discover_agents()
    if not agents:
        console.print(
            "[yellow]No agents found. Run 'traderbot profile discover-agents' to scan.[/yellow]"
        )
        return

    console.print("\n[bold]Select an agent:[/bold]")
    for i, agent in enumerate(agents, 1):
        console.print(f"  {i}. {agent['name']} ({agent['agent_id']}) — {agent['path']}")

    try:
        choice = typer.prompt("Select agent number", type=int)
    except (ValueError, KeyboardInterrupt):
        return

    if choice < 1 or choice > len(agents):
        console.print("[red]Invalid selection[/red]")
        return

    agent = agents[choice - 1]
    agent_id = agent["agent_id"]

    console.print("\n[bold]Workspace file mode:[/bold]")
    console.print(
        "  1. Merge — backup existing files, then merge TraderBot templates (recommended)"
    )
    console.print("  2. Overwrite — replace workspace files with TraderBot templates")

    try:
        ws_choice = typer.prompt("Select mode", default="1")
    except (ValueError, KeyboardInterrupt):
        return

    overwrite = ws_choice == "2"

    try:
        token = generate_token()
        assign_token(name, agent_id, token)
        console.print(f"[green]✓[/green] Assigned token to profile '{name}' for agent '{agent_id}'")
        _write_token_to_env(token, console)

        agent_path = _resolve_agent_path(agent_id)
        if agent_path and agent_path.exists():
            propagate_workspace_files(registry.get_profile(name), agent_path, overwrite=overwrite)
            mode = "overwritten" if overwrite else "merged"
            console.print(f"[green]✓[/green] Workspace files {mode} into {agent_id}/")
        else:
            logger.info(
                "Agent workspace not found for '%s' — token assigned to .env only", agent_id
            )
    except TokenAlreadyAssignedError:
        console.print(f"[yellow]Profile '{name}' already has a token assigned.[/yellow]")
        console.print(
            "Use [bold]traderbot profile revoke[/bold] first, or re-run with [bold]--force[/bold] to reassign."
        )
        raise typer.Exit(1) from None


def _do_assign(
    profile_name: str,
    agent_id: str,
    overwrite: bool = False,
    force: bool = False,
    console: Console | None = None,
    script_output: bool = False,
) -> None:
    from traderbot.profiles.injection import propagate_workspace_files
    from traderbot.profiles.registry import ProfileRegistry
    from traderbot.profiles.tokens import TokenAlreadyAssignedError, assign_token, generate_token

    if console is None:
        console = Console()

    registry = ProfileRegistry()

    if not registry.profile_exists(profile_name):
        console.print(f"[red]Error:[/red] Profile '{profile_name}' not found")
        raise typer.Exit(1)

    profile = registry.get_profile(profile_name)

    try:
        token = generate_token()
        assign_token(profile_name, agent_id, token, force=force)
        console.print(
            f"[green]✓[/green] Assigned token to profile '{profile_name}' for agent '{agent_id}'"
        )

        _write_token_to_env(token, console)

        if script_output:
            console.print(f"Token: [bold]{_mask_token(token)}[/bold]")

        try:
            agent_path = _resolve_agent_path(agent_id)
            if not agent_path or not agent_path.exists():
                logger.info("Agent workspace not found for '%s' — token in .env only", agent_id)
            else:
                propagate_workspace_files(profile, agent_path, overwrite=overwrite)
                mode = "overwritten" if overwrite else "merged"
                console.print(f"[green]✓[/green] Workspace files {mode} into {agent_id}/")

                try:
                    from traderbot.profiles.openclaw_config import (
                        enable_session_memory_hook,
                        ensure_agent_bootstrap_hook,
                    )

                    enable_session_memory_hook()
                    ensure_agent_bootstrap_hook()
                    console.print("[green]✓[/green] OpenClaw features configured (hooks)")

                    try:
                        news_result = _install_news_ingest_timer(
                            agent_user=agent_id,
                            console=console,
                        )
                        if news_result.get("registered"):
                            console.print("[green]✓[/green] News ingestion timer installed")
                    except Exception as ni_err:
                        logger.warning("News ingest timer install failed: %s", ni_err)
                        console.print(
                            "[yellow]Warning:[/yellow] News ingestion timer could not be installed "
                            f"({ni_err})"
                        )
                except Exception as oc_err:
                    logger.warning("OpenClaw feature setup failed: %s", oc_err)
                    console.print(
                        "[yellow]Warning:[/yellow] OpenClaw features partially configured: "
                        f"{oc_err}"
                    )
        except FileNotFoundError:
            logger.info("Agent workspace not found — token in .env only")
        except Exception as e:
            logger.warning("Failed to propagate workspace files: %s", e)
    except TokenAlreadyAssignedError:
        console.print(f"[yellow]Profile '{profile_name}' already has a token assigned.[/yellow]")
        console.print(
            "Use [bold]traderbot profile revoke[/bold] first, or re-run with [bold]--force[/bold] to reassign."
        )
        raise typer.Exit(1) from None


def _interactive_assign(console: Console, registry, overwrite: bool = False) -> None:
    from traderbot.profiles.discovery import discover_agents

    profiles = registry.list_profiles()
    if not profiles:
        console.print(
            "[yellow]No profiles found.[/yellow] Create one with: traderbot profile create"
        )
        return

    console.print("\n[bold]Select a profile:[/bold]")
    for i, p_name in enumerate(profiles, 1):
        profile = registry.get_profile(p_name)
        mode = f" [{profile.mode}]" if profile else ""
        desc = f" — {profile.description}" if profile and profile.description else ""
        console.print(f"  {i}. {p_name}{mode}{desc}")

    try:
        choice = typer.prompt("Enter number", type=int)
    except (ValueError, KeyboardInterrupt):
        return

    if choice < 1 or choice > len(profiles):
        console.print("[red]Invalid selection[/red]")
        return

    profile_name = profiles[choice - 1]

    agents = discover_agents()
    if not agents:
        console.print(
            "[yellow]No agents found. Run 'traderbot profile discover-agents' to scan.[/yellow]"
        )
        console.print(
            f"\n[dim]To assign manually: traderbot profile assign {profile_name} <agent_id>[/dim]"
        )
        return

    console.print("\n[bold]Select an agent:[/bold]")
    for i, agent in enumerate(agents, 1):
        console.print(f"  {i}. {agent['name']} ({agent['agent_id']}) — {agent['path']}")

    try:
        agent_choice = typer.prompt("Enter number", type=int)
    except (ValueError, KeyboardInterrupt):
        return

    if agent_choice < 1 or agent_choice > len(agents):
        console.print("[red]Invalid selection[/red]")
        return

    agent = agents[agent_choice - 1]
    agent_id = agent["agent_id"]

    console.print("\n[bold]Workspace file mode:[/bold]")
    console.print(
        "  1. Merge — backup existing files, then merge TraderBot templates (recommended)"
    )
    console.print("  2. Overwrite — replace workspace files with TraderBot templates")

    try:
        ws_choice = typer.prompt("Select mode", default="1")
    except (ValueError, KeyboardInterrupt):
        return

    overwrite_flag = ws_choice == "2"
    _do_assign(profile_name, agent_id, overwrite=overwrite_flag, console=console)


def _apply_profile_update(
    name: str,
    mode: str | None,
    description: str | None,
    categories: str | None,
    risk_multiplier: float | None,
    max_position_pct: float | None,
    max_daily_loss_pct: float | None,
    max_drawdown_pct: float | None,
    max_open_positions: int | None,
    min_liquidity: int | None,
    min_edge_pct: float | None,
    initial_balance_cents: int | None = None,
    console: Console = None,
    registry=None,
) -> None:
    from traderbot.kalshi.models import MarketCategory

    if not registry.profile_exists(name):
        console.print(f"[red]Error:[/red] Profile '{name}' not found")
        raise typer.Exit(1)

    update_kwargs: dict = {}

    if mode is not None:
        if mode not in ("paper", "live"):
            console.print("[red]Error:[/red] mode must be 'paper' or 'live'")
            raise typer.Exit(1)
        update_kwargs["mode"] = mode

    if description is not None:
        update_kwargs["description"] = description

    if categories is not None:
        try:
            update_kwargs["enabled_categories"] = [
                MarketCategory(cat.strip().lower()) for cat in categories.split(",")
            ]
        except ValueError as e:
            console.print(f"[red]Error:[/red] Invalid category: {e}")
            raise typer.Exit(1) from None
        update_kwargs["mode"] = mode

    if description is not None:
        update_kwargs["description"] = description

    if categories is not None:
        try:
            update_kwargs["enabled_categories"] = [
                MarketCategory(cat.strip().lower()) for cat in categories.split(",")
            ]
        except ValueError as e:
            console.print(f"[red]Error:[/red] Invalid category: {e}")
            raise typer.Exit(1) from None

    if risk_multiplier is not None:
        update_kwargs["risk_multiplier"] = risk_multiplier

    if max_position_pct is not None:
        update_kwargs["max_position_per_market_pct"] = max_position_pct

    if max_daily_loss_pct is not None:
        update_kwargs["max_daily_loss_pct"] = max_daily_loss_pct

    if max_drawdown_pct is not None:
        update_kwargs["max_drawdown_pct"] = max_drawdown_pct

    if max_open_positions is not None:
        update_kwargs["max_open_positions"] = max_open_positions

    if min_liquidity is not None:
        update_kwargs["min_liquidity_threshold"] = min_liquidity

    if min_edge_pct is not None:
        update_kwargs["min_edge_pct"] = min_edge_pct

    if initial_balance_cents is not None:
        update_kwargs["initial_balance_cents"] = initial_balance_cents

    if not update_kwargs:
        console.print("[yellow]Warning:[/yellow] No fields to update")
        return

    try:
        registry.update_profile(name, **update_kwargs)
        console.print(f"[green]✓[/green] Updated profile '{name}'")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


@profile_app.command("create")
def profile_create(
    name: Annotated[
        str | None, typer.Argument(help="Profile name (omit for interactive mode)")
    ] = None,
    mode: Annotated[str | None, typer.Option(help="Trading mode: paper or live")] = None,
    description: Annotated[str | None, typer.Option(help="Profile description")] = None,
    categories: Annotated[
        str | None, typer.Option(help="Comma-separated market categories")
    ] = None,
    risk_multiplier: Annotated[float | None, typer.Option(help="Risk multiplier (0-1)")] = None,
    max_position_pct: Annotated[
        float | None, typer.Option(help="Max position per market %")
    ] = None,
    max_daily_loss_pct: Annotated[float | None, typer.Option(help="Max daily loss %")] = None,
    max_drawdown_pct: Annotated[float | None, typer.Option(help="Max drawdown %")] = None,
    max_open_positions: Annotated[int | None, typer.Option(help="Max open positions")] = None,
    min_liquidity: Annotated[int | None, typer.Option(help="Min liquidity threshold")] = None,
    min_edge_pct: Annotated[float | None, typer.Option(help="Min edge %")] = None,
    initial_balance_cents: Annotated[
        int | None,
        typer.Option(help="Initial balance in cents for paper trading (default: 10000 = $100)"),
    ] = None,
) -> None:
    """Create a new trading profile. Interactive if no name given; uses flags if name provided."""
    from traderbot.kalshi.models import MarketCategory
    from traderbot.profiles.models import TradingProfile
    from traderbot.profiles.registry import ProfileRegistry
    from traderbot.risk.limits import HARD_LIMITS

    console = Console()
    registry = ProfileRegistry()

    if name is None and sys.stdin.isatty():
        _interactive_profile_create(console, registry)
        return

    has_flags = any(
        v is not None
        for v in [
            mode,
            description,
            categories,
            risk_multiplier,
            max_position_pct,
            max_daily_loss_pct,
            max_drawdown_pct,
            max_open_positions,
            min_liquidity,
            min_edge_pct,
            initial_balance_cents,
        ]
    )

    if name is None:
        console.print("[dim]Use: traderbot profile create <name> [options][/dim]")
        console.print("[dim]Or run without arguments for interactive mode.[/dim]")
        raise typer.Exit(0)

    profile_mode = mode or "paper"
    if profile_mode not in ("paper", "live"):
        console.print("[red]Error:[/red] mode must be 'paper' or 'live'")
        raise typer.Exit(1)

    enabled_categories = []
    if categories:
        try:
            enabled_categories = [
                MarketCategory(cat.strip().lower()) for cat in categories.split(",")
            ]
        except ValueError as e:
            console.print(f"[red]Error:[/red] Invalid category: {e}")
            raise typer.Exit(1) from None

    profile_data = {
        "name": name,
        "mode": profile_mode,
        "description": description or f"{name} trading profile",
        "enabled_categories": enabled_categories,
        "risk_multiplier": risk_multiplier or 1.0,
        "max_position_per_market_pct": max_position_pct
        or HARD_LIMITS["max_position_per_market_pct"],
        "max_daily_loss_pct": max_daily_loss_pct or HARD_LIMITS["max_daily_loss_pct"],
        "max_drawdown_pct": max_drawdown_pct or HARD_LIMITS["max_drawdown_pct"],
        "max_open_positions": max_open_positions or int(HARD_LIMITS["max_open_positions"]),
        "min_liquidity_threshold": min_liquidity or int(HARD_LIMITS["min_liquidity_threshold"]),
        "min_edge_pct": min_edge_pct or HARD_LIMITS["min_edge_pct"],
    }

    try:
        profile = TradingProfile(**profile_data)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None

    if registry.profile_exists(name):
        console.print(f"[yellow]Profile '{name}' already exists.[/yellow]")
        console.print("  [1] Overwrite the existing profile")
        console.print("  [2] Choose a different name")
        console.print("  [3] Cancel")
        choice = typer.prompt("  Select an option", default="3")
        if choice == "1":
            registry.delete_profile(name)
            registry.create_profile(profile)
            console.print(f"[green]✓[/green] Overwrote profile '{name}' in {profile_mode} mode")
        elif choice == "2":
            new_name = typer.prompt("  New profile name")
            profile_data["name"] = new_name
            try:
                profile = TradingProfile(**profile_data)
                registry.create_profile(profile)
                console.print(
                    f"[green]✓[/green] Created profile '{new_name}' in {profile_mode} mode"
                )
            except ValueError as e:
                console.print(f"[red]Error:[/red] {e}")
                raise typer.Exit(1) from None
        else:
            console.print("[dim]Cancelled.[/dim]")
        return

    registry.create_profile(profile)
    console.print(f"[green]✓[/green] Created profile '{name}' in {profile_mode} mode")


@profile_app.command("list")
def profile_list(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """List all trading profiles."""
    from traderbot.profiles.registry import ProfileRegistry

    console = Console()
    registry = ProfileRegistry()
    profile_names = registry.list_profiles()

    if not profile_names:
        if not json_output:
            console.print("[yellow]No profiles found[/yellow]")
        else:
            print("[]")
        return

    if json_output:
        profiles = []
        for name in profile_names:
            profile = registry.get_profile(name)
            if profile:
                profiles.append(profile.model_dump(mode="json"))
        print(json_lib.dumps(profiles, indent=2))
    else:
        table = Table(title="Trading Profiles")
        table.add_column("Name", style="cyan")
        table.add_column("Mode", style="magenta")
        table.add_column("Description")
        table.add_column("Risk Multiplier", justify="right")

        for name in profile_names:
            profile = registry.get_profile(name)
            if profile:
                table.add_row(
                    profile.name,
                    profile.mode,
                    profile.description,
                    f"{profile.risk_multiplier:.2f}",
                )

        console.print(table)


@profile_app.command("show")
def profile_show(
    name: str,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Show details for a specific profile."""
    from traderbot.profiles.registry import ProfileRegistry

    console = Console()
    registry = ProfileRegistry()
    profile = registry.get_profile(name)

    if profile is None:
        console.print(f"[red]Error:[/red] Profile '{name}' not found")
        raise typer.Exit(1)

    if json_output:
        print(json_lib.dumps(profile.model_dump(mode="json"), indent=2))
    else:
        console.print(f"\n[bold cyan]Profile: {profile.name}[/bold cyan]")
        console.print(f"Mode: {profile.mode}")
        console.print(f"Description: {profile.description}")
        console.print("\n[bold]Risk Parameters:[/bold]")
        console.print(f"  Risk Multiplier: {profile.risk_multiplier}")
        console.print(f"  Max Position per Market: {profile.max_position_per_market_pct}%")
        console.print(f"  Max Daily Loss: {profile.max_daily_loss_pct}%")
        console.print(f"  Max Drawdown: {profile.max_drawdown_pct}%")
        console.print(f"  Max Open Positions: {profile.max_open_positions}")
        console.print(f"  Min Liquidity: {profile.min_liquidity_threshold}")
        console.print(f"  Min Edge: {profile.min_edge_pct}%")
        if profile.initial_balance_cents:
            console.print(f"  Initial Balance: ${profile.initial_balance_cents / 100:.2f}")
        if profile.enabled_categories:
            console.print(
                f"\n[bold]Enabled Categories:[/bold] {', '.join(c.value for c in profile.enabled_categories)}"
            )
        else:
            console.print("\n[bold]Enabled Categories:[/bold] All")


@profile_app.command("delete")
def profile_delete(
    name: str,
    keep_data: Annotated[bool, typer.Option(help="Keep data directories")] = True,
) -> None:
    """Delete a trading profile."""
    from traderbot.profiles.registry import ProfileRegistry

    console = Console()
    registry = ProfileRegistry()

    if not registry.profile_exists(name):
        console.print(f"[yellow]Warning:[/yellow] Profile '{name}' does not exist")
        return

    registry.delete_profile(name, keep_data=keep_data)
    console.print(f"[green]✓[/green] Deleted profile '{name}'")

    if not keep_data:
        console.print("[yellow]Note:[/yellow] Data directories were also deleted")


@profile_app.command("assign")
def profile_assign(
    profile_name: Annotated[str | None, typer.Argument(help="Profile name")] = None,
    agent_id: Annotated[str | None, typer.Argument(help="Agent ID or name")] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Auto-apply all workspace templates without prompting"),
    ] = False,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Overwrite workspace files instead of merging")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Reassign token even if profile already has one")
    ] = False,
) -> None:
    """Assign a token to an agent for profile access.

    Called without arguments, enters interactive mode: select a profile, then an agent, then choose merge or overwrite.
    Called with profile_name and agent_id, applies directly (non-interactive with --yes).
    """
    from traderbot.profiles.injection_strategies import set_skip_prompts
    from traderbot.profiles.registry import ProfileRegistry

    if yes:
        set_skip_prompts(True)

    console = Console()
    registry = ProfileRegistry()

    if profile_name is None or agent_id is None:
        if not sys.stdin.isatty():
            console.print(
                "[red]Error:[/red] profile_name and agent_id required in non-interactive mode"
            )
            raise typer.Exit(1)
        _interactive_assign(console, registry, overwrite=overwrite)
        return

    _do_assign(
        profile_name, agent_id, overwrite=overwrite, force=force, console=console, script_output=yes
    )


@profile_app.command("sync-env")
def profile_sync_env(
    profile_name: Annotated[str, typer.Argument(help="Profile name whose token to sync to .env")],
) -> None:
    """Sync a profile's token from the registry to .env.

    Resolves the current valid token for the given profile from the encrypted
    token registry, then writes it as TRADERBOT_PROFILE_TOKEN in ~/.traderbot/.env.
    Useful when the .env token has gone stale (expired or out of sync with
    the registry).
    """
    from traderbot.profiles.tokens import sync_env_token

    console = Console()
    token = sync_env_token(profile_name)

    if token is None:
        from traderbot.profiles.registry import ProfileRegistry

        registry = ProfileRegistry()
        if not registry.profile_exists(profile_name):
            console.print(f"[red]Error:[/red] Profile '{profile_name}' not found")
        else:
            console.print(
                f"[red]Error:[/red] No valid token for profile '{profile_name}'. "
                "Re-assign with: traderbot profile assign "
                f"{profile_name} <agent> --force"
            )
        raise typer.Exit(1)

    console.print(f"[green]✓[/green] Synced token for profile '{profile_name}' to .env")
    console.print(f"  Token: {_mask_token(token)}")


@profile_app.command("revoke")
def profile_revoke(
    profile_name: Annotated[str, typer.Argument(help="Profile name")],
) -> None:
    """Revoke a token assigned to a profile."""
    from traderbot.profiles.tokens import get_profile_token, resolve_token, revoke_token

    console = Console()

    token = get_profile_token(profile_name)
    if token is None:
        console.print(f"[yellow]Warning:[/yellow] No token assigned to profile '{profile_name}'")
        return

    resolved = resolve_token(token)
    agent_id = resolved[1] if resolved else None

    revoke_token(token)
    console.print(f"[green]✓[/green] Revoked token for profile '{profile_name}'")


@profile_app.command("get-token")
def profile_get_token(
    profile_name: Annotated[str, typer.Argument(help="Profile name")],
) -> None:
    """Output the raw token for a profile (for service installation)."""
    from traderbot.profiles.tokens import get_profile_token

    token = get_profile_token(profile_name)
    if token is None:
        raise typer.Exit(1)
    print(token)


@profile_app.command("assignments")
def profile_assignments(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """List all token assignments."""
    from traderbot.profiles.tokens import list_assignments

    console = Console()
    assignments = list_assignments()

    if not assignments:
        if not json_output:
            console.print("[yellow]No token assignments found[/yellow]")
        else:
            print("[]")
        return

    if json_output:
        masked_assignments = [{**a, "token": _mask_token(a["token"])} for a in assignments]
        print(json_lib.dumps(masked_assignments, indent=2))
    else:
        table = Table(title="Token Assignments")
        table.add_column("Profile", style="cyan")
        table.add_column("Agent ID", style="magenta")
        table.add_column("Token", style="yellow")
        table.add_column("Created At")

        for assignment in assignments:
            table.add_row(
                assignment["profile"],
                assignment["agent"],
                _mask_token(assignment["token"]),
                assignment["created_at"],
            )

        console.print(table)


@profile_app.command("update")
def profile_update(
    name: Annotated[str | None, typer.Argument(help="Profile name to update")] = None,
    mode: Annotated[str | None, typer.Option(help="Trading mode: paper or live")] = None,
    description: Annotated[str | None, typer.Option(help="Profile description")] = None,
    categories: Annotated[
        str | None, typer.Option(help="Comma-separated market categories")
    ] = None,
    risk_multiplier: Annotated[float | None, typer.Option(help="Risk multiplier (0-1)")] = None,
    max_position_pct: Annotated[
        float | None, typer.Option(help="Max position per market %")
    ] = None,
    max_daily_loss_pct: Annotated[float | None, typer.Option(help="Max daily loss %")] = None,
    max_drawdown_pct: Annotated[float | None, typer.Option(help="Max drawdown %")] = None,
    max_open_positions: Annotated[int | None, typer.Option(help="Max open positions")] = None,
    min_liquidity: Annotated[int | None, typer.Option(help="Min liquidity threshold")] = None,
    min_edge_pct: Annotated[float | None, typer.Option(help="Min edge %")] = None,
    initial_balance_cents: Annotated[
        int | None,
        typer.Option(help="Initial balance in cents for paper trading (default: 10000 = $100)"),
    ] = None,
) -> None:
    """Update specific fields of an existing profile.

    Called without a name, enters interactive mode: select a profile, then choose
    to edit, delete, or assign an agent to it. Called with a name and flags, applies
    the flags directly (non-interactive).
    """
    from traderbot.profiles.registry import ProfileRegistry

    console = Console()
    registry = ProfileRegistry()

    has_flags = any(
        v is not None
        for v in [
            mode,
            description,
            categories,
            risk_multiplier,
            max_position_pct,
            max_daily_loss_pct,
            max_drawdown_pct,
            max_open_positions,
            min_liquidity,
            min_edge_pct,
            initial_balance_cents,
        ]
    )

    if name is None:
        profiles = registry.list_profiles()
        if not profiles:
            console.print(
                "[yellow]No profiles found.[/yellow] Create one with: traderbot profile create <name>"
            )
            raise typer.Exit(0)

        if not has_flags and sys.stdin.isatty():
            name = _interactive_profile_select(profiles, console)
            if name is None:
                raise typer.Exit(0)
            _interactive_profile_action(name, console, registry)
            return

        console.print("[bold]Available profiles:[/bold]")
        for p_name in profiles:
            console.print(f"  • {p_name}")
        console.print(
            "\n[dim]Use: traderbot profile update <name> [options] to update a profile[/dim]"
        )
        raise typer.Exit(0)

    _apply_profile_update(
        name,
        mode,
        description,
        categories,
        risk_multiplier,
        max_position_pct,
        max_daily_loss_pct,
        max_drawdown_pct,
        max_open_positions,
        min_liquidity,
        min_edge_pct,
        initial_balance_cents=initial_balance_cents,
        console=console,
        registry=registry,
    )


@profile_app.command("discover-agents")
def profile_discover_agents(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Scan OpenClaw workspaces for available agents."""
    from traderbot.profiles.discovery import discover_agents

    console = Console()
    agents = discover_agents()

    if not agents:
        if not json_output:
            console.print("[yellow]No agents found in .openclaw/workspace[/yellow]")
        else:
            print("[]")
        return

    if json_output:
        print(json_lib.dumps(agents, indent=2))
    else:
        table = Table(title="Discovered Agents")
        table.add_column("Agent ID", style="cyan")
        table.add_column("Name", style="magenta")
        table.add_column("Path", style="yellow")

        for agent in agents:
            table.add_row(
                agent["agent_id"],
                agent["name"],
                agent["path"],
            )

        console.print(table)


@profile_app.command("auth")
def profile_auth(
    profile_name: str,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Show configured credentials for a profile (from environment variables)."""
    from traderbot.profiles.auth import ProfileAuthStore
    from traderbot.profiles.registry import ProfileRegistry

    console = Console()
    registry = ProfileRegistry()

    profile = registry.get_profile(profile_name)
    if profile is None:
        console.print(f"[red]Error:[/red] Profile '{profile_name}' not found")
        raise typer.Exit(1)

    auth_store = ProfileAuthStore(profile)
    known_services = ["kalshi", "voyage", "newsapi", "twitter", "reddit"]
    found_services: list[str] = []
    for svc in known_services:
        if auth_store.has_credentials(svc):
            found_services.append(svc)

    if not found_services:
        if not json_output:
            console.print(
                f"[yellow]No credentials configured for profile '{profile_name}'[/yellow]"
            )
        else:
            print("[]")
        return

    if json_output:
        creds_list = []
        for svc in found_services:
            creds = auth_store.get_credentials(svc)
            if creds:
                creds_list.append(
                    {
                        "service": svc,
                        "key": _mask_token(creds[0]),
                    }
                )
        print(json_lib.dumps(creds_list, indent=2))
    else:
        table = Table(title=f"Credentials for Profile '{profile_name}'")
        table.add_column("Service", style="cyan")
        table.add_column("Key", style="yellow")

        for svc in found_services:
            creds = auth_store.get_credentials(svc)
            if creds:
                masked_key = creds[0][:8] + "..." if len(creds[0]) > 8 else "***"
                table.add_row(svc, masked_key)

        console.print(table)


@profile_app.command("reset")
def profile_reset(
    name: Annotated[str | None, typer.Argument(help="Profile name to reset")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompts")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Reset a paper profile's balance without losing trade history.

    Sets the initial balance to a new value while preserving all
    position records, settlement history, and audit logs.

    Use this when stale positions or accumulated losses have made
    the portfolio balance unrepresentative of actual performance.
    """
    from traderbot.paper import compute_paper_balance
    from traderbot.profiles.registry import ProfileRegistry

    console = Console()
    registry = ProfileRegistry()

    profiles = registry.list_profiles()
    if not profiles:
        console.print(
            "[red]Error:[/red] No profiles found. Create one with: traderbot profile create <name>"
        )
        raise typer.Exit(1)

    if name is None:
        if not sys.stdin.isatty():
            console.print("[red]Error:[/red] Profile name required in non-interactive mode")
            raise typer.Exit(1)
        choice = _interactive_profile_select(profiles, console)
        if not choice:
            raise typer.Exit(0)
        name = choice
    elif name not in profiles:
        console.print(f"[red]Error:[/red] Profile '{name}' not found")
        raise typer.Exit(1)

    profile = registry.get_profile(name)
    if not profile or not profile.paper_mode:
        console.print(
            f"[red]Error:[/red] Profile '{name}' is not paper mode — "
            "only paper profiles can be reset"
        )
        raise typer.Exit(1)

    pb = compute_paper_balance(profile)

    if json_output:
        import json as _j

        current: dict = {
            "name": name,
            "initial_balance_cents": profile.initial_balance_cents,
        }
        if pb:
            current["remaining_cents"] = pb.remaining_cents
            current["open_positions"] = pb.open_position_count
            current["cost_at_risk_cents"] = pb.cost_at_risk_cents
        _j.dump(current, sys.stdout, default=str)
        return

    console.print(f"\n[bold]Profile:[/bold] {name}")
    if profile.initial_balance_cents:
        console.print(f"  Current initial balance: ${profile.initial_balance_cents / 100:.2f}")
    else:
        console.print("  Current initial balance: not set")

    if pb:
        console.print(f"  Current remaining cash:  ${pb.remaining_cents / 100:.2f}")
        console.print(f"  Open positions:          {pb.open_position_count}")
        console.print(f"  Cost at risk:            ${pb.cost_at_risk_cents / 100:.2f}")
        console.print(f"  Total settled P&L:       ${pb.net_pnl_cents / 100:.2f}")
    else:
        console.print("[yellow]  No active balance data found[/yellow]")

    console.print()
    console.print("[bold]What this does:[/bold]")
    console.print("  - Resets the starting balance to a new value")
    console.print("  - All trade history, positions, and settlements preserved")
    console.print("  - P&L calculation uses the new starting balance")
    console.print("  - Open positions remain in the database")
    console.print()

    if not yes:
        default_val = str((profile.initial_balance_cents or 10000) // 100)
        result = typer.prompt(
            "Enter new starting balance in dollars (e.g. 100, 500, 2000)",
            default=default_val,
        )
        if not result:
            console.print("[yellow]Reset cancelled.[/yellow]")
            raise typer.Exit(0)

        try:
            new_balance_dollars = float(result)
            if new_balance_dollars <= 0:
                console.print("[red]Error:[/red] Starting balance must be positive")
                raise typer.Exit(1)
        except ValueError:
            console.print(f"[red]Error:[/red] Invalid number: '{result}'")
            raise typer.Exit(1)

        new_balance_cents = int(new_balance_dollars * 100)

        if pb and pb.cost_at_risk_cents > new_balance_cents:
            deficit = (new_balance_cents - pb.cost_at_risk_cents) // 100
            console.print(
                f"[yellow]Warning:[/yellow] New balance ${new_balance_dollars:.2f} is less "
                f"than cost at risk (${pb.cost_at_risk_cents / 100:.2f}). "
                f"Remaining cash after open positions: ${deficit}."
            )
            confirm2 = typer.prompt("Type 'yes' to confirm", default="")
            if confirm2 != "yes":
                console.print("[yellow]Reset cancelled.[/yellow]")
                raise typer.Exit(0)

        confirm = typer.prompt(
            f"Reset '{name}' from ${profile.initial_balance_cents / 100:.2f} "
            f"to ${new_balance_dollars:.2f}",
            default="no",
        )
        if confirm != "yes":
            console.print("[yellow]Reset cancelled.[/yellow]")
            raise typer.Exit(0)
    else:
        new_balance_cents = profile.initial_balance_cents or 10000

    registry.update_profile(name, initial_balance_cents=new_balance_cents)

    console.print(f"\n[green]✓[/green] Profile '{name}' reset to ${new_balance_cents / 100:.2f}")
    console.print("  Trade history, positions, and settlements preserved.")
    console.print("  Run 'traderbot profile show <name>' to verify.\n")
