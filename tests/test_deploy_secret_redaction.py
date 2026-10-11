"""Secret display and exception-chain redaction regressions for deploy."""

from __future__ import annotations

import logging
import secrets
import traceback
from io import StringIO

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from traderbot.deploy.phase45_runtime import Phase45Adapter
from traderbot.deploy.secret_step import (
    KalshiSecretPair,
    SecretReconciliationError,
    SecretsSelection,
    provision_kalshi_secrets,
)
from traderbot.deploy.wizard_contracts import WizardRequest
from traderbot.secrets.store import SecretsStore


class _SensitiveBackendFault(RuntimeError):
    pass


class _SensitiveDeployStore:
    def __init__(self, sensitive: SecretStr) -> None:
        self._sensitive: SecretStr = sensitive

    def get(self, service: str, key: str, namespace: str = "global") -> str | None:
        del service, key, namespace
        return None

    def set(
        self,
        service: str,
        key: str,
        value: str,
        namespace: str = "global",
    ) -> None:
        del service, key, value, namespace
        raise _SensitiveBackendFault(self._sensitive.get_secret_value())


class _LocalBackend:
    def __init__(self, sensitive: SecretStr | None = None) -> None:
        self._sensitive: SecretStr | None = sensitive

    def get(self, *, service: str, key: str, namespace: str) -> str | None:
        del service, key, namespace
        return None

    def set(self, *, service: str, key: str, value: str, namespace: str) -> None:
        del service, key, value, namespace
        if self._sensitive is not None:
            raise _SensitiveBackendFault(self._sensitive.get_secret_value())

    def delete(self, *, service: str, key: str, namespace: str) -> None:
        del service, key, namespace

    def get_namespace(self, namespace: str) -> dict[str, str]:
        del namespace
        return {}


def _pair() -> KalshiSecretPair:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    return KalshiSecretPair.from_plain(secrets.token_urlsafe(), pem)


def test_secret_pair_redacts_every_display_surface(caplog: pytest.LogCaptureFixture) -> None:
    # Given: a runtime-generated Kalshi pair.
    pair = _pair()
    values = (pair.api_key.get_secret_value(), pair.private_key_pem.get_secret_value())

    # When: ordinary debug, serialization, exception, and logging surfaces render it.
    caplog.set_level(logging.INFO)
    logging.getLogger(__name__).info("pair=%s", pair)
    rendered = (repr(pair), str(pair), pair.model_dump_json(), str(pair.model_dump()), caplog.text)

    # Then: neither secret value appears on any surface.
    assert all(value not in surface for value in values for surface in rendered)


def test_backend_sensitive_fault_is_absent_from_error_chain_trace_log_and_result() -> None:
    # Given: a backend fault whose message contains one generated protected value.
    pair = _pair()
    sensitive = pair.api_key
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger(f"{__name__}.isolated-sensitive-chain")
    logger.handlers = [handler]
    logger.propagate = False

    # When: provisioning sanitizes the backend fault and the error is rendered everywhere.
    with pytest.raises(SecretReconciliationError) as raised:
        _ = provision_kalshi_secrets(
            _SensitiveDeployStore(sensitive),
            lambda: pair,
            backend="local-encrypted",
        )
    error = raised.value
    logger.error(
        "sanitized provisioning failure",
        exc_info=(type(error), error, error.__traceback__),
    )
    adapter = Phase45Adapter(
        SecretsSelection(
            store=SecretsStore(local_store=_LocalBackend(sensitive)),
            backend="local-encrypted",
            fallback_store=SecretsStore(local_store=_LocalBackend()),
        ),
        lambda: pair,
    )
    result = adapter.provision_secrets(
        WizardRequest.model_validate({"categories": ["weather"], "mode": "backtest"})
    )
    rendered = (
        str(error),
        repr(error),
        repr(error.__cause__),
        repr(error.__context__),
        "".join(traceback.format_exception(error)),
        stream.getvalue(),
        result.model_dump_json(),
    )

    # Then: the sanitized error is disconnected and every observable surface is clean.
    protected = sensitive.get_secret_value()
    leak_count = sum(protected in surface for surface in rendered)
    assert leak_count == 0
    assert error.__cause__ is None
    assert error.__context__ is None
    assert error.__suppress_context__ is True
    assert error.written_secret_names == ()
    assert error.pending_secret_names == ("kalshi_api_key", "kalshi_private_key_pem")
