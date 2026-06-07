"""CLI entry point — imports all sub-apps and registers them on the main typer app."""

import json as json_lib
import logging
import shutil
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from traderbot.cli.admin import register_commands as register_admin
from traderbot.cli.auth import auth_app
from traderbot.cli.data import data_app
from traderbot.cli.helpers import (
    _LAUNCHCTL,
    _SUDO,
    _SYSTEMCTL,
    _check_updates_on_startup,
    app,
)
from traderbot.cli.market import register_commands as register_market
from traderbot.cli.news import register_commands as register_news
from traderbot.cli.profile import profile_app
from traderbot.cli.sandbox import sandbox_app
from traderbot.cli.trade import register_commands as register_trade
from traderbot.cli.ws import ws_app

logger = logging.getLogger(__name__)

# Lazy import for modules that may fail to compile — the update command
# must remain reachable even if one of these modules is broken, so that
# a stale deployment can self-heal via git pull + reinstall.
_cron_app = None


def _get_cron_app():
    """Lazy-import cron_app to keep the update command reachable."""
    global _cron_app
    if _cron_app is None:
        try:
            from traderbot.cli.cron import cron_app

            _cron_app = cron_app
        except Exception as exc:
            logger.warning("Failed to import cron_app (update may be needed): %s", exc)
            return None
    return _cron_app


# Register sub-apps
app.add_typer(auth_app, name="auth")
# cron_app is registered inline below
app.add_typer(sandbox_app, name="sandbox")
app.add_typer(profile_app, name="profile")
app.add_typer(data_app, name="data")

# Register flat commands
register_trade(app)
register_market(app)
register_news(app)
register_admin(app)
app.add_typer(ws_app, name="ws")

# Register experiment sub-app (imported from experiment module)
try:
    from traderbot.experiment.cli import experiment_app

    app.add_typer(experiment_app, name="experiment")
except Exception as exc:
    logger.debug("Failed to import experiment_app: %s", exc)

# Register cron_app after initializing the app to keep update reachable
_ca = _get_cron_app()
if _ca is not None:
    app.add_typer(_ca, name="cron")


@app.command()
def update(
    dev: Annotated[
        bool, typer.Option("--dev", help="Update from dev branch instead of main")
    ] = False,
    check: Annotated[
        bool, typer.Option("--check", help="Check for update only, do not apply")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Pull and apply even if versions match")
    ] = False,
) -> None:
    """Check for and apply updates. Defaults to check+apply; use --check to check only."""
    from traderbot.update_config import UpdateConfig
    from traderbot.updater import apply_update, check_for_updates, get_current_version

    console = Console()
    config = UpdateConfig.load()
    current = get_current_version()

    if check and not force:
        result = check_for_updates(
            force=True, check_interval_minutes=config.check_interval_minutes, dev=dev
        )
        if result:
            if dev:
                console.print(f"[yellow]Dev branch update available: {result['latest']}[/yellow]")
            else:
                console.print(
                    f"[yellow]Update available: v{result['current']} → v{result['latest']}[/yellow]"
                )
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

    result = check_for_updates(
        force=True, check_interval_minutes=config.check_interval_minutes, dev=dev
    )
    if result:
        branch_label = "dev" if dev else "main"
        console.print(
            f"[yellow]Update available: v{result['current']} → v{result['latest']}[/yellow]"
        )
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
    check_interval_minutes: Annotated[
        int | None, typer.Option(help="Check interval in minutes")
    ] = None,
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
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON for machine consumption"),
    ] = False,
) -> None:
    """Uninstall TraderBot — interactively prompts for each removal category."""
    import platform
    import subprocess as _sp

    from traderbot.paths import get_data_dir, list_all_data_paths

    console = Console()
    data_dir = get_data_dir()
    repo_dir = Path.home() / "traderbot"
    removed: list[str] = []

    remove_data = False
    remove_repo = False

    # Step 1: Stop and remove system services
    if json_output:
        removed_services = []
        if platform.system() == "Darwin":
            daemon_dir = Path("/Library/LaunchDaemons")
            if daemon_dir.exists():
                for plist in daemon_dir.glob("com.traderbot.*.plist"):
                    label = plist.stem
                    _sp.run([_SUDO, _LAUNCHCTL, "bootout", f"system/{label}"], capture_output=True)
                    result = _sp.run([_SUDO, "rm", "-f", str(plist)], capture_output=True)
                    if result.returncode == 0:
                        removed_services.append(str(plist))
        elif platform.system() == "Linux":
            service_dir = Path("/etc/systemd/system")
            if service_dir.exists():
                for svc in list(service_dir.glob("traderbot-*@*.service")) + list(
                    service_dir.glob("traderbot-*@*.timer")
                ):
                    unit = svc.name
                    _sp.run([_SUDO, _SYSTEMCTL, "stop", unit], capture_output=True)
                    _sp.run([_SUDO, _SYSTEMCTL, "disable", unit], capture_output=True)
                    _sp.run([_SUDO, "rm", "-f", str(svc)], capture_output=True)
                    removed_services.append(str(svc))
                for wants_dir in [
                    Path("/etc/systemd/system/multi-user.target.wants"),
                    Path("/etc/systemd/system/timers.target.wants"),
                ]:
                    for link in wants_dir.glob("traderbot-*"):
                        if link.is_symlink():
                            _sp.run([_SUDO, "rm", "-f", str(link)], capture_output=True)
                            removed_services.append(str(link))
                _sp.run([_SUDO, _SYSTEMCTL, "daemon-reload"], capture_output=True)
            # User-level systemd services (OpenClaw gateway)
            user_svc_dir = Path.home() / ".config" / "systemd" / "user"
            if user_svc_dir.exists():
                for svc in list(user_svc_dir.glob("openclaw-*gateway*")) + list(
                    user_svc_dir.glob("traderbot-*")
                ):
                    unit = svc.name
                    _sp.run([_SYSTEMCTL, "--user", "stop", unit], capture_output=True)
                    _sp.run([_SYSTEMCTL, "--user", "disable", unit], capture_output=True)
                    _sp.run(["rm", "-f", str(svc)], capture_output=True)
                    removed_services.append(str(svc))
        removed.extend(removed_services)
    else:
        removed_services: list[str] = []
        if platform.system() == "Darwin":
            daemon_dir = Path("/Library/LaunchDaemons")
            if daemon_dir.exists():
                plists = list(daemon_dir.glob("com.traderbot.*.plist"))
                if plists:
                    console.print("[bold]Step 1a: Remove launch daemons[/bold]")
                    for plist in plists:
                        label = plist.stem
                        _sp.run(
                            [_SUDO, _LAUNCHCTL, "bootout", f"system/{label}"], capture_output=True
                        )
                        result = _sp.run([_SUDO, "rm", "-f", str(plist)], capture_output=True)
                        if result.returncode == 0:
                            console.print(f"  Removed: {label}")
                            removed_services.append(str(plist))
        elif platform.system() == "Linux":
            service_dir = Path("/etc/systemd/system")
            if service_dir.exists():
                unit_files = list(service_dir.glob("traderbot-*@*.service")) + list(
                    service_dir.glob("traderbot-*@*.timer")
                )
                if unit_files:
                    console.print("[bold]Step 1a: Remove systemd services and timers[/bold]")
                    for svc in unit_files:
                        unit = svc.name
                        _sp.run([_SUDO, _SYSTEMCTL, "stop", unit], capture_output=True)
                        _sp.run([_SUDO, _SYSTEMCTL, "disable", unit], capture_output=True)
                        _sp.run([_SUDO, "rm", "-f", str(svc)], capture_output=True)
                        console.print(f"  Removed: {unit}")
                        removed_services.append(str(svc))
                for wants_dir in [
                    Path("/etc/systemd/system/multi-user.target.wants"),
                    Path("/etc/systemd/system/timers.target.wants"),
                ]:
                    for link in wants_dir.glob("traderbot-*"):
                        if link.is_symlink():
                            _sp.run([_SUDO, "rm", "-f", str(link)], capture_output=True)
                            console.print(f"  Removed symlink: {link.name}")
                            removed_services.append(str(link))
                _sp.run([_SUDO, _SYSTEMCTL, "daemon-reload"], capture_output=True)
            # User-level systemd services (OpenClaw gateway)
            user_svc_dir = Path.home() / ".config" / "systemd" / "user"
            if user_svc_dir.exists():
                user_units = list(user_svc_dir.glob("openclaw-*gateway*")) + list(
                    user_svc_dir.glob("traderbot-*")
                )
                if user_units:
                    console.print("[bold]Step 1c: Remove user-level systemd services[/bold]")
                    for svc in user_units:
                        unit = svc.name
                        _sp.run([_SYSTEMCTL, "--user", "stop", unit], capture_output=True)
                        _sp.run([_SYSTEMCTL, "--user", "disable", unit], capture_output=True)
                        _sp.run(["rm", "-f", str(svc)], capture_output=True)
                        console.print(f"  Removed user service: {unit}")
                        removed_services.append(str(svc))
        removed.extend(removed_services)

    # User-level systemd services (OpenClaw gateway, TraderBot agent)
    if platform.system() == "Linux":
        user_svc_dir = Path.home() / ".config" / "systemd" / "user"
        if user_svc_dir.exists():
            for svc in list(user_svc_dir.glob("openclaw-*gateway*")) + list(
                user_svc_dir.glob("traderbot-*")
            ):
                unit = svc.name
                _sp.run([_SYSTEMCTL, "--user", "stop", unit], capture_output=True)
                _sp.run([_SYSTEMCTL, "--user", "disable", unit], capture_output=True)
                _sp.run(["rm", "-f", str(svc)], capture_output=True)
                console.print(f"  Removed user service: {unit}")
                removed_services.append(str(svc))
    removed.extend(removed_services)

    # Uninstall pip package if installed (not .venv local install)
    try:
        import traderbot as _tb_mod

        _tb_path = Path(_tb_mod.__file__).resolve()
        if "site-packages" in str(_tb_path):
            if json_output:
                _sp.run(
                    [sys.executable, "-m", "pip", "uninstall", "traderbot", "-y"],
                    capture_output=True,
                    timeout=30,
                )
                removed.append("pip:traderbot")
            else:
                if typer.confirm("  Uninstall pip package 'traderbot'?", default=True):
                    _sp.run(
                        [sys.executable, "-m", "pip", "uninstall", "traderbot", "-y"],
                        capture_output=True,
                        timeout=30,
                    )
                    console.print("  Uninstalled pip package: traderbot")
                    removed.append("pip:traderbot")
    except Exception as exc:
        logger.warning("pip uninstall failed: %s", exc)

    _sl_usrs = [Path("/usr/local/bin/traderbot"), Path.home() / ".local/bin/traderbot"]
    for _sl in _sl_usrs:
        if _sl.is_symlink() or _sl.exists():
            try:
                cmd = (
                    [_SUDO, "rm", "-f", str(_sl)]
                    if str(_sl).startswith("/usr/local")
                    else ["rm", "-f", str(_sl)]
                )
                _sp.run(cmd, capture_output=True)
                removed.append(str(_sl))
                if not json_output:
                    console.print(f"  Removed symlink: {_sl}")
            except Exception as exc:
                logger.warning("Failed to remove symlink %s: %s", _sl, exc)

    if not json_output:
        console.print("[bold]Remove OpenClaw cron jobs[/bold]")
    cron_removed = []
    try:
        cron_output = _sp.run(
            ["openclaw", "cron", "list", "--json"], capture_output=True, text=True, timeout=10
        )
        if cron_output.returncode == 0:
            import json as _cjson

            cron_jobs = _cjson.loads(cron_output.stdout)
            for job in cron_jobs if isinstance(cron_jobs, list) else cron_jobs.get("jobs", []):
                jid = job.get("id") if isinstance(job, dict) else None
                if jid:
                    _sp.run(["openclaw", "cron", "remove", jid], capture_output=True, timeout=10)
                    cron_removed.append(jid)
    except Exception as exc:
        logger.warning("Cron job removal failed: %s", exc)
    if cron_removed and not json_output:
        console.print(f"  Removed {len(cron_removed)} cron jobs")

    # Step 2: Remove user data (~/.traderbot/)
    if data_dir.exists():
        if json_output:
            remove_data = True
        else:
            console.print("\n[bold]Step 2: Remove user data[/bold]")
            console.print(f"[dim]Data directory: {data_dir}[/dim]")
            console.print(
                "[dim]This will delete all credentials (API keys, PEM keys), ChromaDB (market data, news, signals), "
                "profile tokens, logs, and cached data.[/dim]"
            )
            remove_data = typer.confirm("  Remove all user data?", default=False)

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
            console.print(
                "[dim]This will permanently delete the source code and virtual environment.[/dim]"
            )
            answer = typer.confirm("  Remove repository?", default=False)
            if answer:
                remove_repo = True

    if remove_repo and repo_dir.exists():
        shutil.rmtree(repo_dir)
        removed.append(str(repo_dir))
        if not json_output:
            console.print(f"  Removed repo: {repo_dir}")

    _shell_files = [Path.home() / ".bashrc", Path.home() / ".profile"]
    for _sf in _shell_files:
        if _sf.exists():
            try:
                content = _sf.read_text()
                if ".local/bin" in content:
                    cleaned = "\n".join(
                        line for line in content.splitlines() if ".local/bin" not in line
                    )
                    _sf.write_text(cleaned + "\n")
                    removed.append(f"{_sf}:local-bin-path")
                    if not json_output:
                        console.print(f"  Cleaned PATH addition: {_sf}")
            except Exception as exc:
                logger.warning("Failed to remove PATH addition from %s: %s", _sf, exc)

    openclaw_dir = Path.home() / ".openclaw"
    if openclaw_dir.exists():
        remove_oc = False
        if json_output:
            remove_oc = True
        else:
            remove_oc = typer.confirm(
                "  Remove OpenClaw config, cron jobs, agents, workspace (~/.openclaw)?",
                default=False,
            )
        if remove_oc:
            _sp.run(
                ["openclaw", "uninstall", "--state", "--workspace", "--yes", "--non-interactive"],
                capture_output=True,
                timeout=30,
            )
            shutil.rmtree(openclaw_dir, ignore_errors=True)
            removed.append(str(openclaw_dir))
            if not json_output:
                console.print(f"  Removed OpenClaw state: {openclaw_dir}")

    npm_pkg = shutil.which("openclaw")
    if npm_pkg and "npm-global" in str(npm_pkg):
        remove_npm = False
        if json_output:
            remove_npm = True
        else:
            remove_npm = typer.confirm(
                "  Remove OpenClaw npm package? (npm uninstall -g openclaw)", default=False
            )
        if remove_npm:
            # Stop gateway before removing the binary
            _sp.run(["openclaw", "gateway", "stop"], capture_output=True, timeout=30)
            _sp.run(["npm", "uninstall", "-g", "openclaw"], capture_output=True, timeout=30)
            if not json_output:
                console.print("  Removed OpenClaw npm package")
            removed.append("npm:openclaw")

    _sbx_name = "traderbot-sandbox:bookworm-slim"
    try:
        _containers = _sp.run(
            ["docker", "ps", "-aq", "--filter", "name=openclaw-sbx"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if _containers.stdout.strip():
            _remove_cont = True
            if not json_output:
                _remove_cont = typer.confirm(
                    "  Remove orphaned OpenClaw sandbox containers?", default=False
                )
            if _remove_cont:
                for _cid in _containers.stdout.strip().splitlines():
                    _sp.run(["docker", "rm", "-f", _cid], capture_output=True, timeout=15)
                removed.append("docker:openclaw-sbx-containers")
                if not json_output:
                    console.print("  Removed orphaned sandbox containers")
    except Exception as exc:
        logger.warning("Docker container removal failed: %s", exc)

    try:
        _img_res = _sp.run(
            ["docker", "images", "-q", _sbx_name], capture_output=True, text=True, timeout=10
        )
        if _img_res.stdout.strip():
            _remove_img = True
            if not json_output:
                _remove_img = typer.confirm(
                    f"  Remove Docker sandbox image ({_sbx_name})?", default=False
                )
            if _remove_img:
                _sp.run(["docker", "rmi", "-f", _sbx_name], capture_output=True, timeout=30)
                removed.append(f"docker:{_sbx_name}")
                if not json_output:
                    console.print(f"  Removed Docker image: {_sbx_name}")
    except Exception as exc:
        logger.warning("Docker image removal failed for %s: %s", _sbx_name, exc)

    # Prune Docker build cache (accumulates from repeated sandbox builds)
    try:
        _cache_res = _sp.run(
            ["docker", "builder", "prune", "--all", "--force"], capture_output=True, timeout=60
        )
        if _cache_res.returncode == 0:
            removed.append("docker:build-cache")
            if not json_output:
                console.print("  Pruned Docker build cache")
    except Exception as exc:
        logger.warning("Docker build cache prune failed: %s", exc)

    log_dir = data_dir / "logs"
    if log_dir.exists():
        if not json_output:
            console.print("[bold]Cleaning up install logs[/bold]")
        for f in log_dir.glob("install-*"):
            f.unlink()
            if not json_output:
                console.print(f"  Removed log: {f.name}")
            removed.append(str(f))

    tmp_cleaned = []
    try:
        for p in Path("/tmp").glob("traderbot-news-ingest@*"):
            if p.exists():
                p.unlink()
                tmp_cleaned.append(str(p))
    except Exception as exc:
        logger.warning("Temp file cleanup failed: %s", exc)

    if tmp_cleaned:
        removed.extend(tmp_cleaned)
        if not json_output:
            for t in tmp_cleaned:
                print(f"  Cleaned: {t}")

    if json_output:
        json_lib.dump(
            {"removed": removed, "data_removed": remove_data, "repo_removed": remove_repo},
            sys.stdout,
            default=str,
        )
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
