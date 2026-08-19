"""Runtime adapter for deploy wizard steps 4-5."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import final

from infisical_sdk.infisical_requests import InfisicalError
from requests import RequestException

from traderbot.db.chroma_store import ChromaOwnershipError
from traderbot.db.migrations import MigrationError
from traderbot.db.pool import (
    ConnectionPoolClosedError,
    ConnectionPoolTimeoutError,
    CrossThreadAccessError,
)
from traderbot.db.security import ChromaBackendError, InvalidChromaRootError
from traderbot.deploy.database_step import (
    DatabaseCleanupError,
    DatabaseProvisionError,
    provision_deploy_databases,
)
from traderbot.deploy.secret_step import (
    EnvironmentSecretInput,
    KalshiSecretPair,
    MissingSecretEnvironmentError,
    SecretInputRequiredError,
    SecretPairApprovalError,
    SecretPairValidationError,
    SecretReconciliationError,
    SecretsSelection,
    kalshi_secret_names,
    provision_kalshi_secrets,
)
from traderbot.deploy.wizard_contracts import Phase45Result, WizardRequest
from traderbot.paths import get_data_dir
from traderbot.secrets.local_encrypted import SecretIntegrityError


@final
class Phase45Adapter:
    def __init__(
        self,
        selection: SecretsSelection,
        hidden_reader: Callable[[], KalshiSecretPair] | None,
        data_root: Path | None = None,
    ) -> None:
        self._selection: SecretsSelection = selection
        self._hidden_reader: Callable[[], KalshiSecretPair] | None = hidden_reader
        self._data_root: Path = get_data_dir() if data_root is None else data_root

    def provision_secrets(self, request: WizardRequest) -> Phase45Result:
        if (
            request.kalshi_api_key_env is not None
            and request.kalshi_private_key_pem_env is not None
        ):
            reader = EnvironmentSecretInput(
                request.kalshi_api_key_env,
                request.kalshi_private_key_pem_env,
            ).read
        elif self._hidden_reader is not None:
            reader = self._hidden_reader
        else:
            reader = self._missing_input
        replacement: KalshiSecretPair | None = None

        def read_once() -> KalshiSecretPair:
            nonlocal replacement
            if replacement is None:
                replacement = reader()
            return replacement

        try:
            report = provision_kalshi_secrets(
                self._selection.store,
                read_once,
                backend=self._selection.backend,
                approvals=request.secret_approvals,
                environment=request.kalshi_environment,
            )
        except MissingSecretEnvironmentError as exc:
            return Phase45Result.failed(str(exc))
        except SecretPairApprovalError as exc:
            return Phase45Result.failed(str(exc))
        except SecretReconciliationError as exc:
            if self._selection.backend == "local-encrypted":
                return Phase45Result.failed(str(exc))
            return self._fallback_after_remote_failure(request, read_once, exc)
        except (
            InfisicalError,
            OSError,
            RequestException,
            SecretInputRequiredError,
            SecretIntegrityError,
            SecretPairValidationError,
        ) as exc:
            if self._selection.backend == "infisical" and isinstance(
                exc,
                (InfisicalError, OSError, RequestException),
            ):
                boundary = SecretReconciliationError(
                    written_secret_names=(),
                    pending_secret_names=kalshi_secret_names(request.kalshi_environment),
                )
                return self._fallback_after_remote_failure(request, read_once, boundary)
            return Phase45Result.failed("Kalshi secret validation or storage failed")
        return Phase45Result.completed(f"Kalshi secrets {report.status}; backend={report.backend}")

    def provision_databases(self, request: WizardRequest) -> Phase45Result:
        try:
            report = provision_deploy_databases(
                request.categories,
                request.mode,
                self._data_root,
            )
        except ChromaOwnershipError as exc:
            return Phase45Result.failed(str(exc))
        except DatabaseCleanupError:
            return Phase45Result.failed("database or Chroma cleanup failed")
        except (
            ChromaBackendError,
            ConnectionPoolClosedError,
            ConnectionPoolTimeoutError,
            CrossThreadAccessError,
            DatabaseProvisionError,
            InvalidChromaRootError,
            MigrationError,
            OSError,
            sqlite3.Error,
        ):
            return Phase45Result.failed("database or Chroma provisioning failed")
        message = f"{len(report.decision_paths)} category databases ready; "
        message += f"SysAdmin sees {report.sysadmin_visible_databases}; "
        manifest = ",".join(report.shared_collection_manifest)
        message += f"Chroma manifest={manifest}; collections remain lazy"
        return Phase45Result.completed(message)

    def _fallback_after_remote_failure(
        self,
        request: WizardRequest,
        read_once: Callable[[], KalshiSecretPair],
        remote: SecretReconciliationError,
    ) -> Phase45Result:
        try:
            report = provision_kalshi_secrets(
                self._selection.fallback_store,
                read_once,
                backend="local-encrypted",
                approvals=request.secret_approvals,
                environment=request.kalshi_environment,
            )
        except (
            MissingSecretEnvironmentError,
            OSError,
            SecretIntegrityError,
            SecretInputRequiredError,
            SecretPairApprovalError,
            SecretPairValidationError,
            SecretReconciliationError,
        ):
            return Phase45Result.failed(f"remote {remote}; local encrypted fallback failed")
        return Phase45Result.completed(
            f"remote {remote}; local fallback {report.status}; backend=local-encrypted"
        )

    @staticmethod
    def _missing_input() -> KalshiSecretPair:
        raise SecretInputRequiredError


__all__ = ["Phase45Adapter"]
