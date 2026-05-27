"""CLI entry point — imports all sub-apps and registers them on the main typer app."""
from __future__ import annotations

import json as json_lib
import shutil
import subprocess as _subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from traderbot.cli.auth import auth_app
from traderbot.cli.cron import cron_app
from traderbot.cli.sandbox import sandbox_app
from traderbot.cli.profile import profile_app
from traderbot.cli.trade import register_commands as register_trade
from traderbot.cli.market import register_commands as register_market
from traderbot.cli.news import register_commands as register_news
from traderbot.cli.admin import register_commands as register_admin
from traderbot.cli.data import data_app
from traderbot.cli.helpers import (
    _LAUNCHCTL,
    _SUDO,
    _SYSTEMCTL,
    _check_updates_on_startup,
    app,
)

# Register sub-apps
app.add_typer(auth_app, name="auth")
app.add_typer(cron_app, name="cron")
app.add_typer(sandbox_app, name="sandbox")
app.add_typer(profile_app, name="profile")
app.add_typer(data_app, name="data")

# Register flat commands
register_trade(app)
register_market(app)
register_news(app)
register_admin(app)

# Register experiment sub-app (imported from experiment module)
from traderbot.experiment.cli import experiment_app  # type: ignore[import-untyped]
app.add_typer(experiment_app, name="experiment")


@app.command()
def update(
    dev: Annotated[bool, typer.Option("--dev", help="Update from dev branch instead of main")] = False,
    check: Annotated[bool, typer.Option("--check", help="Check for update only, do not apply")] = False,
    force: Annotated[bool, typer.Option("--force", help="Pull and apply even if versions match")] = False,
) -> None:
    """Check for and apply updates. Defaults to check+apply; use --check to check only."""
    from traderbot.update_config import UpdateConfig
    from traderbot.updater import apply_update, check_for_updates, get_current_version

    console = Console()
    config = UpdateConfig.load()
    current = get_current_version()

    if check and not force:
        result = check_for_updates(force=True, check_interval_minutes=config.check_interval_minutes, dev=dev)
        if result:
            if dev:
                console.print(f"[yellow]Dev branch update available: {result['latest']}[/yellow]")
            else:
                console.print(f"[yellow]Update available: v{result['current']} → v{result['latest']}[/yellow]")
            console.print(f"[dim]Release: {result['url']}[/dim]")
        else:
            console.print(f"[green]Already up to date (v{current}).[/green]")
        return

    if force:
        branch_label = "dev" if dev else "main"
        console.print(f"[bold]Forcing update from {branch_label} branch...[/bold]")
        if apply_update(dev=dev):
            console.print("[green]✓ Update applied successfully.[/green]")
        else:
            console.print("[red]✗ Update failed. Check logs for details.[/red]")
        return

    result = check_for_updates(force=True, check_interval_minutes=config.check_interval_minutes, dev=dev)
    if result:
        branch_label = "dev" if dev else "main"
        console.print(f"[yellow]Update available: v{result['current']} → v{result['latest']}[/yellow]")
        console.print(f"[bold]Applying update from {branch_label} branch...[/bold]")
        if apply_update(dev=dev):
            console.print("[green]✓ Update applied successfully.[/green]")
        else:
            console.print("[red]✗ Update failed. Check logs for details.[/red]")
    else:
        console.print(f"[green]Already up to date (v{current}).[/green]")


@app.command("update-configure")
def update_configure(
    enabled: Annotated[bool | None, typer.Option(help="Enable/disable update checking")] = None,
    check_on_startup: Annotated[bool | None, typer.Option(help="Check on startup")] = None,
    check_interval_minutes: Annotated[int | None, typer.Option(help="Check interval in minutes")] = None,
) -> None:
    """Configure update checking behavior."""
    from traderbot.update_config import UpdateConfig

    console = Console()
    config = UpdateConfig.load()

    if enabled is not None:
        config.enabled = enabled
    if check_on_startup is not None:
        config.check_on_startup = check_on_startup
    if check_interval_minutes is not None:
        config.check_interval_minutes = check_interval_minutes

    config.save()
    console.print(f"[green]Update config saved to {UpdateConfig.CONFIG_PATH}[/green]")
    console.print(config.model_dump_json(indent=2))


@app.command()
def uninstall(
    remove_data: Annotated[
        bool,
        typer.Option("--remove-data", help="Remove all profiles, databases, and user data (~/.traderbot/)"),
    ] = False,
    remove_repo: Annotated[
        bool,
        typer.Option("--remove-repo", help="Remove the TraderBot repository (~/traderbot/)"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON for machine consumption"),
    ] = False,
) -> None:
    """Uninstall TraderBot — remove services, data, and optionally the repository."""
    import platform
    import subprocess as _sp

    from traderbot.paths import get_data_dir, list_all_data_paths
    from traderbot.profiles.registry import ProfileRegistry

    console = Console()
    data_dir = get_data_dir()
    repo_dir = Path.home() / "traderbot"
    removed: list[str] = []

    # Step 1: Stop and remove system services
    if json_output:
        removed_services = []
        if platform.system() == "Darwin":
            daemon_dir = Path("/Library/LaunchDaemons")
            if daemon_dir.exists():
                for plist in daemon_dir.glob("com.traderbot.agent.*.plist"):
                    label = plist.stem
                    _sp.run([_SUDO, _LAUNCHCTL, "bootout", f"system/{label}"], capture_output=True)
                    result = _sp.run([_SUDO, "rm", "-f", str(plist)], capture_output=True)
                    if result.returncode == 0:
                        removed_services.append(str(plist))
        elif platform.system() == "Linux":
            service_dir = Path("/etc/systemd/system")
            if service_dir.exists():
                for svc in service_dir.glob("traderbot-agent@*.service"):
                    unit = svc.name
                    _sp.run([_SUDO, _SYSTEMCTL, "stop", unit], capture_output=True)
                    _sp.run([_SUDO, _SYSTEMCTL, "disable", unit], capture_output=True)
                    _sp.run([_SUDO, "rm", "-f", str(svc)], capture_output=True)
                    removed_services.append(str(svc))
        removed.extend(removed_services)
    else:
        if platform.system() == "Darwin":
            daemon_dir = Path("/Library/LaunchDaemons")
            if daemon_dir.exists():
                plists = list(daemon_dir.glob("com.traderbot.agent.*.plist"))
                if plists:
                    console.print("[bold]Step 1a: Remove launch daemons[/bold]")
                    for plist in plists:
                        label = plist.stem
                        _sp.run([_SUDO, _LAUNCHCTL, "bootout", f"system/{label}"], capture_output=True)
                        result = _sp.run([_SUDO, "rm", "-f", str(plist)], capture_output=True)
                        if result.returncode == 0:
                            console.print(f"  Removed: {label}")
                            removed.append(str(plist))
        elif platform.system() == "Linux":
            service_dir = Path("/etc/systemd/system")
            if service_dir.exists():
                services = list(service_dir.glob("traderbot-agent@*.service"))
                if services:
                    console.print("[bold]Step 1a: Remove systemd services[/bold]")
                    for svc in services:
                        unit = svc.name
                        _sp.run([_SUDO, _SYSTEMCTL, "stop", unit], capture_output=True)
                        _sp.run([_SUDO, _SYSTEMCTL, "disable", unit], capture_output=True)
                        _sp.run([_SUDO, "rm", "-f", str(svc)], capture_output=True)
                        console.print(f"  Removed: {unit}")
                        removed.append(str(svc))

    # Step 2: Remove user data
    if remove_data and data_dir.exists():
        if json_output:
            data_paths = list_all_data_paths()
            for p in data_paths:
                if p.exists():
                    if p.is_dir():
                        shutil.rmtree(p)
                    else:
                        p.unlink()
                    removed.append(str(p))
            if data_dir.exists():
                shutil.rmtree(data_dir)
                removed.append(str(data_dir))
        else:
            console.print("[bold]Step 2: Removing user data[/bold]")
            data_paths = list_all_data_paths()
            for p in data_paths:
                if not p.exists():
                    continue
                label = p.relative_to(data_dir) if p.is_relative_to(data_dir) else p
                if p.is_dir():
                    shutil.rmtree(p)
                    console.print(f"  Removed dir:  {label}")
                else:
                    p.unlink()
                    console.print(f"  Removed file: {label}")
                removed.append(str(p))
            if data_dir.exists():
                shutil.rmtree(data_dir)
                console.print(f"  Removed data dir: {data_dir}")
                removed.append(str(data_dir))

    # Step 3: Prompt about repo removal
    if not remove_repo:
        if json_output:
            pass
        elif repo_dir.exists():
            console.print(f"\n[bold]Repository:[/bold] {repo_dir}")
            console.print("[dim]This will permanently delete the source code and virtual environment.[/dim]")
            answer = typer.confirm("  Remove repository?", default=False)
            if answer:
                remove_repo = True

    if remove_repo:
        if repo_dir.exists():
            shutil.rmtree(repo_dir)
            removed.append(str(repo_dir))
            if not json_output:
                console.print(f"  Removed repo: {repo_dir}")

    # Clean up tmp
    tmp_cleaned = []
    try:
        for p in Path("/tmp").glob("traderbot-news-ingest@*"):
            if p.exists():
                p.unlink()
                tmp_cleaned.append(str(p))
    except Exception:
        pass

    if tmp_cleaned:
        removed.extend(tmp_cleaned)
        if not json_output:
            for t in tmp_cleaned:
                print(f"  Cleaned: {t}")

    if json_output:
        json_lib.dump({"removed": removed, "data_removed": remove_data, "repo_removed": remove_repo}, sys.stdout, default=str)
    else:
        if not removed:
            print("Nothing to remove — TraderBot is not installed.")
        else:
            print(f"\n✓ TraderBot uninstalled. {len(removed)} items removed.")


__all__ = ["app", "main"]


def main() -> None:
    """Entry point for the traderbot CLI."""
    _check_updates_on_startup()
    app()
