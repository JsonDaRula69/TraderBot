from __future__ import annotations

import os
from dataclasses import dataclass

from pydantic import SecretStr, ValidationError

from traderbot.deploy.verify_models import ProbeResult, TokenProbe, VerificationRequest
from traderbot.deploy.wizard_state import ResolvedAgent
from traderbot.deploy.wizard_transaction import profile_for
from traderbot.secrets.store import ProfileTokenPayload, SecretsStore


@dataclass(frozen=True, slots=True)
class TokenVerifier:
    request: VerificationRequest
    store: SecretsStore

    def inspect(self) -> TokenProbe:
        selected = (
            ResolvedAgent(
                "main",
                None,
                self.request.sysadmin_workspace or self.request.data_root,
                True,
            ),
            *(
                ResolvedAgent(
                    category.value,
                    category,
                    self.request.category_workspaces.get(category, self.request.data_root),
                    True,
                )
                for category in self.request.categories
            ),
        )
        daemon_token: SecretStr | None = None
        for agent in selected:
            profile = profile_for(agent)
            raw = self.store.get(agent.agent_id, "token", namespace="tokens")
            if raw is None:
                return TokenProbe(
                    result=ProbeResult.failed("token_missing", "A selected token is missing"),
                    token=None,
                )
            try:
                payload = ProfileTokenPayload.model_validate_json(raw)
            except ValidationError:
                return TokenProbe(
                    result=ProbeResult.failed("token_malformed", "A selected token is malformed"),
                    token=None,
                )
            expected_categories = [item.value for item in profile.enabled_categories]
            valid = (
                payload.profile == profile.name
                and payload.agent_id == agent.agent_id
                and payload.categories == expected_categories
                and payload.permissions == profile.permissions
                and bool(payload.token)
            )
            if not valid:
                return TokenProbe(
                    result=ProbeResult.failed("token_contract_mismatch", "Token metadata differs"),
                    token=None,
                )
            if daemon_token is None:
                daemon_token = SecretStr(payload.token)
        return TokenProbe(result=ProbeResult.passed("tokens_exact"), token=daemon_token)


def auth_mode() -> ProbeResult:
    if os.environ.get("TRADERBOT_USE_HARDCODED_AUTH") != "0":
        return ProbeResult.failed("hardcoded_auth_enabled", "Real authentication is required")
    return ProbeResult.passed("real_auth_enabled")


__all__ = ["TokenVerifier", "auth_mode"]
