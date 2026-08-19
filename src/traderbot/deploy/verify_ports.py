"""Provide production dependency ports for deployment verification."""

from __future__ import annotations

from collections.abc import Callable
from typing import final, override

import httpx
from anyio import to_thread
from pydantic import SecretStr

from traderbot.deploy.secret_step import (
    KalshiSecretPair,
    SecretPairValidationError,
    validate_kalshi_secret_pair,
)
from traderbot.deploy.verify import VerificationPorts
from traderbot.deploy.verify_models import (
    CheckId,
    CheckStatus,
    ProbeResult,
    TokenProbe,
    VerificationRequest,
)
from traderbot.deploy.verify_openclaw import OpenClawVerifier
from traderbot.deploy.verify_runtime import daemon_runtime, service_status
from traderbot.deploy.verify_storage import chroma_offline, decisions_databases, global_database
from traderbot.deploy.verify_tokens import TokenVerifier, auth_mode
from traderbot.kalshi.client import KalshiClient
from traderbot.kalshi.errors import KalshiError
from traderbot.secrets.resolver import (
    SecretsBackendName,
    build_secrets_store_selection,
    close_secrets_store,
)
from traderbot.secrets.store import SecretsStore


@final
class ProductionVerificationPorts(VerificationPorts):
    __slots__ = ("_backend", "_openclaw", "_runtime", "_store", "request")

    def __init__(self, request: VerificationRequest) -> None:
        self.request = request
        self._openclaw = OpenClawVerifier(self.request)
        self._store: SecretsStore | None = None
        self._backend: SecretsBackendName | None = None
        self._runtime: ProbeResult | None = None

    def _selection(self) -> tuple[SecretsStore, SecretsBackendName]:
        if self._store is None or self._backend is None:
            self._store, self._backend = build_secrets_store_selection(
                self.request.infisical_origin
            )
        return self._store, self._backend

    @override
    async def tokens(self) -> TokenProbe:
        store, _ = self._selection()
        return TokenVerifier(self.request, store).inspect()

    @override
    async def probe(self, check_id: CheckId, token: SecretStr | None = None) -> ProbeResult:
        if check_id is CheckId.GATEWAY:
            return await self._sync(self._openclaw.gateway)
        if check_id is CheckId.AGENTS_WORKSPACES:
            return await self._sync(self._openclaw.agents)
        if check_id is CheckId.CRON:
            return await self._sync(self._openclaw.cron)
        if check_id is CheckId.HEARTBEAT:
            return await self._sync(self._openclaw.heartbeat)
        if check_id is CheckId.AUTH_MODE:
            return auth_mode()
        if check_id is CheckId.KALSHI:
            return await self._kalshi()
        if check_id is CheckId.DB_GLOBAL:
            return await self._sync(lambda: global_database(self.request))
        if check_id is CheckId.DB_DECISIONS:
            return await self._sync(lambda: decisions_databases(self.request))
        if check_id is CheckId.DAEMON_SERVICE:
            return await self._sync(service_status)
        if check_id is CheckId.DAEMON_RUNTIME:
            if token is None:
                return ProbeResult.failed("token_unavailable", "Runtime token unavailable")
            self._runtime = await daemon_runtime(self.request, token)
            return self._runtime
        if check_id is CheckId.CHROMA:
            if self._runtime is not None and self._runtime.status is CheckStatus.PASS:
                return ProbeResult.passed("chroma_daemon_owned")
            return await self._sync(lambda: chroma_offline(self.request))
        if check_id is CheckId.INFISICAL:
            return await self._infisical()
        return ProbeResult.failed("invalid_graph_call", "Token graph call is invalid")

    async def _sync(self, function: Callable[[], ProbeResult]) -> ProbeResult:
        return await to_thread.run_sync(function)

    async def _kalshi(self) -> ProbeResult:
        store, _ = self._selection()
        api_key = store.get("kalshi", "api_key")
        private_key = store.get("kalshi", "private_key_pem")
        if api_key is None or private_key is None:
            return ProbeResult.failed("kalshi_credentials_missing", "Kalshi credentials missing")
        try:
            pair = validate_kalshi_secret_pair(KalshiSecretPair.from_plain(api_key, private_key))
            client = KalshiClient(
                api_key=pair.api_key.get_secret_value(),
                private_key_pem=pair.private_key_pem.get_secret_value(),
                environment=self.request.kalshi_environment,
                max_retries=0,
            )
            try:
                _ = await client.get_balance(timeout=self.request.timeout_seconds)
            finally:
                await client.close()
        except (KalshiError, OSError, SecretPairValidationError, TimeoutError):
            return ProbeResult.failed("kalshi_auth_failed", "Kalshi authentication failed")
        return ProbeResult.passed("kalshi_auth_valid")

    async def _infisical(self) -> ProbeResult:
        _, backend = self._selection()
        if backend == "local-encrypted":
            return ProbeResult.degraded("encrypted_fallback", "Encrypted fallback is active")
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                response = await client.get(
                    f"{self.request.infisical_origin}/api/status",
                    timeout=self.request.timeout_seconds,
                )
        except httpx.RequestError:
            return ProbeResult.failed("infisical_unreachable", "Infisical status is unavailable")
        if response.status_code != 200:
            return ProbeResult.failed("infisical_unhealthy", "Infisical status is unhealthy")
        return ProbeResult.passed("infisical_primary")

    def close(self) -> None:
        if self._store is not None:
            close_secrets_store(self._store)
            self._store = None
            self._backend = None

    def set_runtime_result(self, result: ProbeResult) -> None:
        self._runtime = result


__all__ = ["ProductionVerificationPorts"]
