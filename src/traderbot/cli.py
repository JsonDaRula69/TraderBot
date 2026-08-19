"""TraderBot command-line interface.

Provides the always-on daemon entry point (DD-016) and service lifecycle
commands (DD-022): ``traderbot daemon`` runs the daemon, and
``traderbot service install|uninstall|status`` manages the platform
service. The deploy command runs Phase 4 wizard steps 1 through 3; backfill
and verification remain reserved for later plan items.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from traderbot.daemon import main as daemon_main
from traderbot.deploy.backfill_command import BackfillCommandOptions, execute_backfill
from traderbot.deploy.wizard_command import execute_deploy
from traderbot.kalshi.client import KALSHI_ENVIRONMENTS, Environment
from traderbot.kalshi.order_models import MarketCategory
from traderbot.profiles.generic import create_category_profile
from traderbot.services.deploy import (
    deploy_service,
    detect_service_manager,
    disable_and_stop_service,
    enable_and_start_service,
    remove_service,
    service_status,
)

_EXIT_OK = 0
_EXIT_ERROR = 1
_EXIT_INVALID = 2


class _DeployArguments(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)

    config: Path | None = None
    json_output: bool = False


class _BackfillArguments(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)

    months: int
    environment: Environment
    collector_db: Path | None = None
    json_output: bool = False


class _DaemonArguments(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)

    host: str
    port: int
    environment: Environment


class _ProfileArguments(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)

    name: str
    mode: str
    categories: tuple[MarketCategory, ...]


class _VerifyArguments(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)

    categories: tuple[MarketCategory, ...] | None = None
    mode: str
    environment: Environment
    data_root: Path | None = None
    infisical_url: str
    daemon_mcp_url: str
    timeout: float
    json_output: bool


class _CommandArguments(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)

    command: str
    action: str | None = None


def _parse_market_category(value: str) -> MarketCategory:
    try:
        return MarketCategory(value)
    except ValueError as exc:
        msg = f"invalid category: {value!r}"
        raise argparse.ArgumentTypeError(msg) from exc


def _cmd_daemon(args: argparse.Namespace) -> int:
    parsed = _DaemonArguments.model_validate(vars(args))
    forwarded = [
        "--host",
        parsed.host,
        "--port",
        str(parsed.port),
        "--environment",
        parsed.environment,
    ]
    daemon_main(forwarded)
    return _EXIT_OK


def _cmd_service_install(_args: argparse.Namespace) -> int:
    try:
        destination = deploy_service()
        started = enable_and_start_service()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_ERROR
    print(f"Installed daemon service: {destination}")
    print("Service started." if started else "Service enabled but not active yet.")
    return _EXIT_OK


def _cmd_service_uninstall(_args: argparse.Namespace) -> int:
    _ = disable_and_stop_service()
    if not remove_service():
        print("No daemon service file present; nothing to uninstall.", file=sys.stderr)
        return _EXIT_ERROR
    print("Uninstalled daemon service.")
    return _EXIT_OK


def _cmd_service_status(_args: argparse.Namespace) -> int:
    manager = detect_service_manager()
    print(f"Service manager: {manager}")
    print(f"Service status: {service_status()}")
    return _EXIT_OK


def _cmd_profile_create(args: argparse.Namespace) -> int:
    parsed = _ProfileArguments.model_validate(vars(args))
    profile = create_category_profile(parsed.name, parsed.mode, parsed.categories)
    print(profile.model_dump_json())
    return _EXIT_OK


def _cmd_auth_check(_args: argparse.Namespace) -> int:
    print('{"status":"error","error":"no token"}')
    return _EXIT_ERROR


def _cmd_deploy(args: argparse.Namespace) -> int:
    parsed = _DeployArguments.model_validate(vars(args))
    return execute_deploy(parsed.config, parsed.json_output)


def _cmd_backfill(args: argparse.Namespace) -> int:
    parsed = _BackfillArguments.model_validate(vars(args))
    options = BackfillCommandOptions.model_validate(
        {
            "months": parsed.months,
            "environment": parsed.environment,
            "collector_db": parsed.collector_db,
            "json_output": parsed.json_output,
        }
    )
    return execute_backfill(options)


def _cmd_verify(args: argparse.Namespace) -> int:
    from traderbot.deploy.verify_command import (
        VerificationCommandOptions,
        execute_verification,
    )

    parsed = _VerifyArguments.model_validate(vars(args))
    return execute_verification(
        VerificationCommandOptions.model_validate(
            {
                "categories": parsed.categories or (),
                "mode": parsed.mode,
                "environment": parsed.environment,
                "data_root": parsed.data_root,
                "infisical_origin": parsed.infisical_url,
                "daemon_mcp_url": parsed.daemon_mcp_url,
                "timeout_seconds": parsed.timeout,
                "json_output": parsed.json_output,
            }
        )
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="traderbot",
        description="TraderBot daemon and service management.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    daemon = subparsers.add_parser("daemon", help="Run the always-on TraderBot daemon")
    _ = daemon.add_argument("--host", default="127.0.0.1", help="bind host (loopback only)")
    _ = daemon.add_argument("--port", type=int, default=8765, help="bind port")
    _ = daemon.add_argument(
        "--environment",
        default="production",
        choices=KALSHI_ENVIRONMENTS,
        help="Kalshi environment",
    )

    service = subparsers.add_parser("service", help="Manage the daemon service")
    service_sub = service.add_subparsers(dest="action", required=True)
    _ = service_sub.add_parser("install", help="Install the daemon service")
    _ = service_sub.add_parser("uninstall", help="Uninstall the daemon service")
    _ = service_sub.add_parser("status", help="Report daemon service status")

    profile = subparsers.add_parser("profile", help="Manage trading profiles")
    profile_sub = profile.add_subparsers(dest="action", required=True)
    profile_create = profile_sub.add_parser("create", help="Create a category profile")
    _ = profile_create.add_argument("name")
    _ = profile_create.add_argument(
        "--mode",
        default="backtest",
        choices=["backtest", "paper", "live"],
    )
    _ = profile_create.add_argument(
        "--categories",
        nargs="+",
        required=True,
        type=_parse_market_category,
        metavar="CATEGORY",
    )

    auth = subparsers.add_parser("auth", help="Check profile authentication")
    auth_sub = auth.add_subparsers(dest="action", required=True)
    auth_check = auth_sub.add_parser("check", help="Check the active profile token")
    _ = auth_check.add_argument("--json", action="store_true", dest="json_output")

    deploy = subparsers.add_parser("deploy", help="Deploy TraderBot steps 1-5")
    _ = deploy.add_argument("--config", type=Path, help="prompt-free deploy JSON path")
    _ = deploy.add_argument("--json", action="store_true", dest="json_output")
    backfill = subparsers.add_parser("backfill", help="Import weather and fetch Kalshi history")
    _ = backfill.add_argument("--months", type=int, default=6, help="calendar months to backfill")
    _ = backfill.add_argument(
        "--environment",
        default="production",
        choices=KALSHI_ENVIRONMENTS,
        help="Kalshi environment (default: production)",
    )
    _ = backfill.add_argument("--collector-db", type=Path, help="legacy collector SQLite path")
    _ = backfill.add_argument("--json", action="store_true", dest="json_output")
    verify = subparsers.add_parser("verify", help="Verify the deployed TraderBot system")
    _ = verify.add_argument("--categories", nargs="+", type=_parse_market_category)
    _ = verify.add_argument("--mode", choices=["backtest", "paper", "live"], default="backtest")
    _ = verify.add_argument(
        "--environment",
        default="production",
        choices=KALSHI_ENVIRONMENTS,
        help="Kalshi environment (default: production)",
    )
    _ = verify.add_argument("--data-root", type=Path)
    _ = verify.add_argument("--infisical-url", default="http://localhost:8080")
    _ = verify.add_argument("--daemon-mcp-url", default="http://127.0.0.1:8765/mcp")
    _ = verify.add_argument("--timeout", type=float, default=3.0)
    _ = verify.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the traderbot CLI, returning the process exit code."""
    parser = _build_parser()
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if "--json" in arguments:
        with contextlib.redirect_stderr(io.StringIO()):
            try:
                args = parser.parse_args(arguments)
            except SystemExit as error:
                if error.code != 2:
                    raise
                _ = sys.stdout.write(json.dumps({"error": "invalid_request"}) + "\n")
                return _EXIT_INVALID
    else:
        args = parser.parse_args(arguments)

    command = _CommandArguments.model_validate(vars(args))
    if command.command == "daemon":
        return _cmd_daemon(args)
    if command.command == "service":
        if command.action == "install":
            return _cmd_service_install(args)
        if command.action == "uninstall":
            return _cmd_service_uninstall(args)
        if command.action == "status":
            return _cmd_service_status(args)
    if command.command == "profile" and command.action == "create":
        return _cmd_profile_create(args)
    if command.command == "auth" and command.action == "check":
        return _cmd_auth_check(args)
    if command.command in {"deploy", "backfill", "verify"}:
        os.environ["TRADERBOT_USE_HARDCODED_AUTH"] = "0"
        if command.command == "deploy":
            return _cmd_deploy(args)
        if command.command == "backfill":
            return _cmd_backfill(args)
        return _cmd_verify(args)

    parser.error(f"unknown command: {command.command}")


if __name__ == "__main__":
    sys.exit(main())
