"""TraderBot command-line interface.

Provides the always-on daemon entry point (DD-016) and service lifecycle
commands (DD-022): ``traderbot daemon`` runs the daemon, and
``traderbot service install|uninstall|status`` manages the platform
service. The deploy command runs Phase 4 wizard steps 1 through 3; backfill
and verification remain reserved for later plan items.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from traderbot.daemon import main as daemon_main
from traderbot.deploy.wizard_command import execute_deploy
from traderbot.kalshi.models import MarketCategory
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


class _DeployArguments(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)

    config: Path | None = None
    json_output: bool = False


def _parse_market_category(value: str) -> MarketCategory:
    try:
        return MarketCategory(value)
    except ValueError as exc:
        msg = f"invalid category: {value!r}"
        raise argparse.ArgumentTypeError(msg) from exc


def _cmd_daemon(args: argparse.Namespace) -> int:
    forwarded = [
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--environment",
        args.environment,
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
    disable_and_stop_service()
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
    profile = create_category_profile(args.name, args.mode, args.categories)
    print(profile.model_dump_json())
    return _EXIT_OK


def _cmd_auth_check(_args: argparse.Namespace) -> int:
    print('{"status":"error","error":"no token"}')
    return _EXIT_ERROR


def _cmd_deploy(args: argparse.Namespace) -> int:
    parsed = _DeployArguments.model_validate(vars(args))
    return execute_deploy(parsed.config, parsed.json_output)


def _cmd_backfill(_args: argparse.Namespace) -> int:
    print("backfill: not yet implemented")
    return _EXIT_OK


def _cmd_verify(_args: argparse.Namespace) -> int:
    print("verify: not yet implemented")
    return _EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="traderbot",
        description="TraderBot daemon and service management.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    daemon = subparsers.add_parser("daemon", help="Run the always-on TraderBot daemon")
    daemon.add_argument("--host", default="127.0.0.1", help="bind host (loopback only)")
    daemon.add_argument("--port", type=int, default=8765, help="bind port")
    daemon.add_argument(
        "--environment",
        default="production",
        choices=["production", "demo"],
        help="Kalshi environment",
    )

    service = subparsers.add_parser("service", help="Manage the daemon service")
    service_sub = service.add_subparsers(dest="action", required=True)
    service_sub.add_parser("install", help="Install the daemon service")
    service_sub.add_parser("uninstall", help="Uninstall the daemon service")
    service_sub.add_parser("status", help="Report daemon service status")

    profile = subparsers.add_parser("profile", help="Manage trading profiles")
    profile_sub = profile.add_subparsers(dest="action", required=True)
    profile_create = profile_sub.add_parser("create", help="Create a category profile")
    profile_create.add_argument("name")
    profile_create.add_argument(
        "--mode",
        default="backtest",
        choices=["backtest", "paper", "live"],
    )
    profile_create.add_argument(
        "--categories",
        nargs="+",
        required=True,
        type=_parse_market_category,
        metavar="CATEGORY",
    )

    auth = subparsers.add_parser("auth", help="Check profile authentication")
    auth_sub = auth.add_subparsers(dest="action", required=True)
    auth_check = auth_sub.add_parser("check", help="Check the active profile token")
    auth_check.add_argument("--json", action="store_true", dest="json_output")

    deploy = subparsers.add_parser("deploy", help="Deploy TraderBot steps 1-3")
    deploy.add_argument("--config", type=Path, help="prompt-free deploy JSON path")
    deploy.add_argument("--json", action="store_true", dest="json_output")
    subparsers.add_parser("backfill", help="Backfill data (not yet implemented)")
    subparsers.add_parser("verify", help="Verify deployment (not yet implemented)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the traderbot CLI, returning the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "daemon":
        return _cmd_daemon(args)
    if args.command == "service":
        if args.action == "install":
            return _cmd_service_install(args)
        if args.action == "uninstall":
            return _cmd_service_uninstall(args)
        if args.action == "status":
            return _cmd_service_status(args)
    if args.command == "profile" and args.action == "create":
        return _cmd_profile_create(args)
    if args.command == "auth" and args.action == "check":
        return _cmd_auth_check(args)
    if args.command in {"deploy", "backfill", "verify"}:
        os.environ["TRADERBOT_USE_HARDCODED_AUTH"] = "0"
        if args.command == "deploy":
            return _cmd_deploy(args)
        if args.command == "backfill":
            return _cmd_backfill(args)
        if args.command == "verify":
            return _cmd_verify(args)

    parser.error(f"unknown command: {args.command}")
    return _EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
