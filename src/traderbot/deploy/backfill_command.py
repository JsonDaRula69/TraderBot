from __future__ import annotations

import sys
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, Literal, Protocol

import anyio
from pydantic import BaseModel, ConfigDict, ValidationError

from traderbot.db.pool import SQLiteConnectionPool
from traderbot.deploy.backfill import BackfillRequest, run_backfill
from traderbot.deploy.backfill_models import BackfillFailure, BackfillResult
from traderbot.deploy.backfill_ports import (
    BackfillDependencies,
    BackfillRuntime,
    KalshiHistoryPort,
    NullProgress,
)
from traderbot.deploy.backfill_reporter import JsonReporter, RichReporter
from traderbot.deploy.secret_step import (
    KalshiSecretPair,
    SecretPairValidationError,
    validate_kalshi_secret_pair,
)
from traderbot.kalshi.client import ConfigurationError, KalshiClient
from traderbot.paths import get_db_path
from traderbot.secrets.resolver import build_secrets_store_selection, close_secrets_store
from traderbot.secrets.store import SecretsStore


class BackfillCommandOptions(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True, extra="forbid", frozen=True)

    months: int
    collector_db: Path | None = None
    json_output: bool = False
    target_db: Path | None = None


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class ManagedKalshiHistoryPort(KalshiHistoryPort, Protocol):
    async def close(self) -> None: ...


def _build_store() -> SecretsStore:
    store, _backend = build_secrets_store_selection()
    return store


def _build_client(
    pair: KalshiSecretPair,
    environment: Literal["production", "demo"],
) -> ManagedKalshiHistoryPort:
    return KalshiClient(
        api_key=pair.api_key.get_secret_value(),
        private_key_pem=pair.private_key_pem.get_secret_value(),
        environment=environment,
    )


@dataclass(frozen=True, slots=True)
class BackfillRuntimeFactories:
    store: Callable[[], SecretsStore] = _build_store
    client: Callable[
        [KalshiSecretPair, Literal["production", "demo"]],
        ManagedKalshiHistoryPort,
    ] = _build_client
    pool: Callable[[], SQLiteConnectionPool] = SQLiteConnectionPool


@dataclass(frozen=True, slots=True)
class OwnedBackfillDependencies:
    default_collector_path: Path
    clock: SystemClock = SystemClock()
    factories: BackfillRuntimeFactories = BackfillRuntimeFactories()

    def now(self) -> datetime:
        return self.clock.now()

    @asynccontextmanager
    async def open_runtime(
        self,
        environment: Literal["production", "demo"] = "production",
    ) -> AsyncGenerator[BackfillRuntime, None]:
        store: SecretsStore | None = None
        client: ManagedKalshiHistoryPort | None = None
        pool: SQLiteConnectionPool | None = None
        try:
            store = self.factories.store()
            pair = _credentials(store)
            client = self.factories.client(pair, environment)
            pool = self.factories.pool()
            yield BackfillRuntime(client=client, pool=pool, progress=NullProgress())
        finally:
            try:
                if client is not None:
                    await client.close()
            finally:
                try:
                    if pool is not None:
                        pool.shutdown()
                finally:
                    if store is not None:
                        close_secrets_store(store)


def _invalid(code: str) -> BackfillResult:
    return BackfillResult(
        status="invalid_input",
        failures=(BackfillFailure(code=code, detail="backfill configuration is invalid"),),
    )


def _credentials(store: SecretsStore) -> KalshiSecretPair:
    api_key = store.get("kalshi", "api_key")
    private_key = store.get("kalshi", "private_key_pem")
    if api_key is None or private_key is None:
        raise SecretPairValidationError("complete stored credential pair is required")
    return validate_kalshi_secret_pair(KalshiSecretPair.from_plain(api_key, private_key))


async def _run_owned(options: BackfillCommandOptions) -> BackfillResult:
    try:
        request = BackfillRequest(
            months=options.months,
            target_db=get_db_path() if options.target_db is None else options.target_db,
            collector_db=options.collector_db,
        )
        dependencies = OwnedBackfillDependencies(
            default_collector_path=Path.home() / ".data-collector" / "collector.db"
        )
        return await run_backfill(request, dependencies)
    except (ConfigurationError, SecretPairValidationError, ValidationError):
        return _invalid("invalid_credentials_or_request")


async def _run_injected(
    options: BackfillCommandOptions, dependencies: BackfillDependencies
) -> BackfillResult:
    try:
        request = BackfillRequest(
            months=options.months,
            target_db=get_db_path() if options.target_db is None else options.target_db,
            collector_db=options.collector_db,
        )
    except ValidationError:
        return _invalid("invalid_request")
    return await run_backfill(request, dependencies)


def _runtime_failure() -> BackfillResult:
    return BackfillResult(
        status="failure",
        failures=(
            BackfillFailure(code="runtime_failure", detail="backfill runtime failed safely"),
        ),
    )


def _fallback_render(result: BackfillResult, *, json_output: bool) -> None:
    if json_output:
        _ = sys.stdout.write(result.model_dump_json() + "\n")
        return
    _ = sys.stderr.write(
        "TraderBot Backfill: failure\nFailure: runtime_failure: backfill runtime failed safely\n"
    )


def _exit_code(result: BackfillResult) -> int:
    codes = {"complete": 0, "partial": 1, "failure": 1, "invalid_input": 2}
    return codes[result.status]


def execute_backfill(
    options: BackfillCommandOptions,
    dependencies: BackfillDependencies | None = None,
) -> int:
    try:
        result = (
            anyio.run(_run_owned, options)
            if dependencies is None
            else anyio.run(_run_injected, options, dependencies)
        )
        reporter = JsonReporter() if options.json_output else RichReporter()
        reporter.render(result)
    except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK — outer CLI redaction
        result = _runtime_failure()
        _fallback_render(result, json_output=options.json_output)
    return _exit_code(result)


__all__ = [
    "BackfillCommandOptions",
    "BackfillRuntimeFactories",
    "OwnedBackfillDependencies",
    "SystemClock",
    "execute_backfill",
]
