from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

from tests.deploy_cli_provider import provider
from traderbot import cli
from traderbot.deploy.wizard_command import execute_deploy


def _execute_with_test_ports(config_path: Path | None, json_output: bool) -> int:
    return execute_deploy(config_path, json_output, provider.build())


def main() -> int:
    with mock.patch.object(cli, "execute_deploy", _execute_with_test_ports):
        return cli.main()


if __name__ == "__main__":
    sys.exit(main())
