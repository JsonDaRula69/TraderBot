from __future__ import annotations

from traderbot.deploy.config import DeployConfig
from traderbot.deploy.wizard_contracts import WizardRequest
from traderbot.paths import get_data_dir


def request_from_config(config: DeployConfig) -> WizardRequest:
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
            "months_backfill": config.months_backfill,
            "collector_db": config.collector_db,
            "data_root": get_data_dir() if config.data_root is None else config.data_root,
            "daemon_mcp_url": config.daemon_mcp_url,
            "kalshi_environment": config.kalshi_environment,
        }
    )


__all__ = ["request_from_config"]
