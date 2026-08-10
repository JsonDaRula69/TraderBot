"""TraderBot command-line interface (Phase 2).

Provides the always-on daemon entry point (DD-016) and service lifecycle
commands (DD-022): ``traderbot daemon`` runs the daemon, and
``traderbot service install|uninstall|status`` manages the platform
service. This is deliberately minimal — the full 8-step ``traderbot deploy``
wizard is a Phase 4 concern.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from traderbot.daemon import main as daemon_main
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

    parser.error(f"unknown command: {args.command}")
    return _EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
