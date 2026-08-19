"""Adversarial regressions for Todo-6 secret provisioning blockers."""

from __future__ import annotations

import secrets
from typing import TypedDict, Unpack

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from traderbot.deploy.phase45_runtime import Phase45Adapter
from traderbot.deploy.secret_step import (
    KalshiSecretPair,
    SecretPairApprovalError,
    SecretReconciliationError,
    SecretsSelection,
    provision_kalshi_secrets,
)
from traderbot.deploy.wizard_contracts import StepStatus, WizardRequest
from traderbot.secrets.store import SecretsStore


class _Store:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.set_calls: list[tuple[str, str]] = []
        self.fail_on: str | None = None
        self.persist: bool = True

    def get(self, service: str, key: str, namespace: str = "global") -> str | None:
        del namespace
        return self.values.get((service, key))

    def set(
        self,
        service: str,
        key: str,
        value: str,
        namespace: str = "global",
    ) -> None:
        del namespace
        if key == self.fail_on:
            raise _InjectedBackendFault("injected non-secret backend fault")
        self.set_calls.append((service, key))
        if self.persist:
            self.values[(service, key)] = value


class _InjectedBackendFault(RuntimeError):
    pass


class _RequestUpdates(TypedDict, total=False):
    kalshi_api_key_env: str
    kalshi_private_key_pem_env: str
    secret_approvals: dict[str, bool]
    kalshi_environment: str


type _RequestPayloadValue = str | tuple[str, ...] | dict[str, bool]


def _pair() -> KalshiSecretPair:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    return KalshiSecretPair.from_plain(secrets.token_urlsafe(), pem)


def _plain(value: str | SecretStr) -> str:
    return value.get_secret_value() if isinstance(value, SecretStr) else value


def _request(**updates: Unpack[_RequestUpdates]) -> WizardRequest:
    payload: dict[str, _RequestPayloadValue] = {
        "categories": ("weather",),
        "mode": "backtest",
        "approvals": {
            "install_openclaw": False,
            "setup_openclaw": False,
            "create_agents": False,
            "heartbeat_change": False,
        },
    }
    if "kalshi_api_key_env" in updates:
        payload["kalshi_api_key_env"] = updates["kalshi_api_key_env"]
    if "kalshi_private_key_pem_env" in updates:
        payload["kalshi_private_key_pem_env"] = updates["kalshi_private_key_pem_env"]
    if "secret_approvals" in updates:
        payload["secret_approvals"] = updates["secret_approvals"]
    if "kalshi_environment" in updates:
        payload["kalshi_environment"] = updates["kalshi_environment"]
    return WizardRequest.model_validate(payload)


def test_partial_existing_pair_requires_explicit_reconciliation() -> None:
    # Given: only one canonical field is durable.
    pair = _pair()
    store = _Store()
    store.values[("kalshi", "api_key")] = _plain(pair.api_key)

    # When/Then: provisioning fails closed and writes nothing without approval.
    with pytest.raises(RuntimeError):
        _ = provision_kalshi_secrets(store, lambda: pair, backend="local-encrypted")
    assert store.set_calls == []


def test_matching_partial_pair_writes_only_missing_field_on_every_rerun() -> None:
    # Given: explicit reconciliation and one matching durable field.
    pair = _pair()
    store = _Store()
    store.values[("kalshi", "api_key")] = _plain(pair.api_key)
    request = _request(
        kalshi_api_key_env="KEY_REF",
        kalshi_private_key_pem_env="PEM_REF",
        secret_approvals={"reconcile_incomplete": True},
    )

    # When: provisioning and a forward rerun use the same replacement pair.
    _ = provision_kalshi_secrets(
        store,
        lambda: pair,
        backend="local-encrypted",
        approvals=request.secret_approvals,
    )
    _ = provision_kalshi_secrets(
        store,
        lambda: pytest.fail("durable pair must be reused"),
        backend="local-encrypted",
        approvals=request.secret_approvals,
    )

    # Then: only the missing canonical field is written once.
    assert store.set_calls == [("kalshi", "private_key_pem")]


@pytest.mark.parametrize("failed_key", ["api_key", "private_key_pem"])
def test_write_fault_reports_verified_written_and_pending_names(failed_key: str) -> None:
    # Given: a backend fault at either canonical write boundary.
    pair = _pair()
    store = _Store()
    store.fail_on = failed_key

    # When: provisioning re-reads durable state after the fault.
    with pytest.raises(SecretReconciliationError) as raised:
        _ = provision_kalshi_secrets(store, lambda: pair, backend="local-encrypted")

    # Then: names reflect only fields proven durable and contain no values.
    expected_written = () if failed_key == "api_key" else ("kalshi_api_key",)
    assert raised.value.written_secret_names == expected_written
    assert set(raised.value.written_secret_names + raised.value.pending_secret_names) == {
        "kalshi_api_key",
        "kalshi_private_key_pem",
    }
    assert _plain(pair.api_key) not in str(raised.value)
    assert _plain(pair.private_key_pem) not in str(raised.value)


def test_noop_backend_cannot_report_created() -> None:
    # Given: a backend acknowledges writes but persists nothing.
    store = _Store()
    store.persist = False

    # When/Then: post-read verification reports both canonical fields pending.
    with pytest.raises(SecretReconciliationError) as raised:
        _ = provision_kalshi_secrets(store, _pair, backend="local-encrypted")
    assert raised.value.written_secret_names == ()
    assert raised.value.pending_secret_names == (
        "kalshi_api_key",
        "kalshi_private_key_pem",
    )


def test_malformed_existing_pair_requires_replacement_and_post_verifies() -> None:
    # Given: a malformed durable pair and a valid explicit replacement.
    pair = _pair()
    store = _Store()
    store.values[("kalshi", "api_key")] = secrets.token_urlsafe()
    store.values[("kalshi", "private_key_pem")] = "malformed-non-secret-input"

    # When/Then: no approval fails closed, while replacement rewrites and verifies both fields.
    with pytest.raises(SecretPairApprovalError):
        _ = provision_kalshi_secrets(store, lambda: pair, backend="local-encrypted")
    request = _request(
        kalshi_api_key_env="KEY_REF",
        kalshi_private_key_pem_env="PEM_REF",
        secret_approvals={"replace_existing": True},
    )
    report = provision_kalshi_secrets(
        store,
        lambda: pair,
        backend="local-encrypted",
        approvals=request.secret_approvals,
    )
    assert report.status == "replaced"
    assert store.values[("kalshi", "api_key")] == _plain(pair.api_key)
    assert store.values[("kalshi", "private_key_pem")] == _plain(pair.private_key_pem)


def test_partial_mismatch_requires_separate_replacement_approval() -> None:
    # Given: reconciliation approval but a durable field differing from the supplied pair.
    pair = _pair()
    store = _Store()
    store.values[("kalshi", "api_key")] = secrets.token_urlsafe()
    request = _request(
        kalshi_api_key_env="KEY_REF",
        kalshi_private_key_pem_env="PEM_REF",
        secret_approvals={"reconcile_incomplete": True},
    )

    # When/Then: the distinct replacement authority is still required.
    with pytest.raises(SecretPairApprovalError):
        _ = provision_kalshi_secrets(
            store,
            lambda: pair,
            backend="local-encrypted",
            approvals=request.secret_approvals,
        )
    assert store.set_calls == []


def test_demo_partial_write_reports_demo_reconciliation_names() -> None:
    # Given: a backend that fails only on the second demo write.
    pair = _pair()
    store = _Store()
    store.fail_on = "private_key_pem"

    # When: demo provisioning hits the partial write.
    with pytest.raises(SecretReconciliationError) as raised:
        _ = provision_kalshi_secrets(
            store,
            lambda: pair,
            backend="local-encrypted",
            environment="demo",
        )

    # Then: the boundary names the demo namespace and never the production one.
    assert raised.value.written_secret_names == ("kalshi_demo_api_key",)
    assert raised.value.pending_secret_names == ("kalshi_demo_private_key_pem",)
    assert store.set_calls == [("kalshi_demo", "api_key")]
    assert _plain(pair.api_key) not in str(raised.value)
    assert _plain(pair.private_key_pem) not in str(raised.value)


def test_demo_malformed_pair_requires_replacement_without_production_fallback() -> None:
    # Given: a valid production pair and a malformed demo pair.
    production = _pair()
    demo = _pair()
    store = _Store()
    store.values[("kalshi", "api_key")] = _plain(production.api_key)
    store.values[("kalshi", "private_key_pem")] = _plain(production.private_key_pem)
    store.values[("kalshi_demo", "api_key")] = "malformed-demo-key"
    store.values[("kalshi_demo", "private_key_pem")] = "malformed-demo-pem"

    # When/Then: no approval fails closed on the demo pair alone.
    with pytest.raises(SecretPairApprovalError):
        _ = provision_kalshi_secrets(
            store,
            lambda: demo,
            backend="local-encrypted",
            environment="demo",
        )
    assert store.set_calls == []

    # When: replacement is approved, only the demo namespace is rewritten.
    request = _request(
        kalshi_api_key_env="KEY_REF",
        kalshi_private_key_pem_env="PEM_REF",
        secret_approvals={"replace_existing": True},
        kalshi_environment="demo",
    )
    report = provision_kalshi_secrets(
        store,
        lambda: demo,
        backend="local-encrypted",
        approvals=request.secret_approvals,
        environment="demo",
    )
    assert report.status == "replaced"
    assert store.values[("kalshi_demo", "api_key")] == _plain(demo.api_key)
    assert store.values[("kalshi_demo", "private_key_pem")] == _plain(demo.private_key_pem)
    assert store.values[("kalshi", "api_key")] == _plain(production.api_key)
    assert store.values[("kalshi", "private_key_pem")] == _plain(production.private_key_pem)


def test_phase45_demo_request_provisions_only_demo_namespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a demo wizard request with environment references and a local backend.
    pair = _pair()
    backend = _LocalBackend()
    adapter = Phase45Adapter(
        SecretsSelection(
            store=SecretsStore(local_store=backend),
            backend="local-encrypted",
            fallback_store=SecretsStore(local_store=_LocalBackend()),
        ),
        None,
    )
    monkeypatch.setenv("KEY_REF", _plain(pair.api_key))
    monkeypatch.setenv("PEM_REF", _plain(pair.private_key_pem))
    request = _request(
        kalshi_api_key_env="KEY_REF",
        kalshi_private_key_pem_env="PEM_REF",
        kalshi_environment="demo",
    )

    # When: step 4 provisions secrets for the demo request.
    result = adapter.provision_secrets(request)

    # Then: only the demo namespace is written and the report names demo secrets.
    assert result.status is StepStatus.COMPLETED
    assert backend.set_calls == [
        ("kalshi_demo", "api_key"),
        ("kalshi_demo", "private_key_pem"),
    ]
    assert _plain(pair.api_key) not in result.message
    assert _plain(pair.private_key_pem) not in result.message


def test_demo_remote_failure_falls_back_to_demo_local_namespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a remote backend that fails the second write and a demo request.
    pair = _pair()
    remote_backend = _LocalBackend(fail_private_key=True)
    local_backend = _LocalBackend()
    adapter = Phase45Adapter(
        SecretsSelection(
            store=SecretsStore(local_store=remote_backend),
            backend="infisical",
            fallback_store=SecretsStore(local_store=local_backend),
        ),
        lambda: pair,
    )
    monkeypatch.setenv("KEY_REF", _plain(pair.api_key))
    monkeypatch.setenv("PEM_REF", _plain(pair.private_key_pem))
    request = _request(
        kalshi_api_key_env="KEY_REF",
        kalshi_private_key_pem_env="PEM_REF",
        secret_approvals={"reconcile_incomplete": True},
        kalshi_environment="demo",
    )

    # When: the remote write fails and the adapter falls back locally.
    result = adapter.provision_secrets(request)

    # Then: the local fallback writes the demo namespace only.
    assert result.status is StepStatus.COMPLETED
    assert "local fallback" in result.message
    assert remote_backend.set_calls == [("kalshi_demo", "api_key")]
    assert local_backend.set_calls == [
        ("kalshi_demo", "api_key"),
        ("kalshi_demo", "private_key_pem"),
    ]


class _LocalBackend:
    def __init__(self, *, fail_private_key: bool = False) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.set_calls: list[tuple[str, str]] = []
        self.fail_private_key: bool = fail_private_key

    def get(self, *, service: str, key: str, namespace: str) -> str | None:
        del namespace
        return self.values.get((service, key))

    def set(self, *, service: str, key: str, value: str, namespace: str) -> None:
        del namespace
        if key == "private_key_pem" and self.fail_private_key:
            raise _InjectedBackendFault("injected remote write fault")
        self.values[(service, key)] = value
        self.set_calls.append((service, key))

    def delete(self, *, service: str, key: str, namespace: str) -> None:
        del self.values[(service, key)]
        del namespace

    def get_namespace(self, namespace: str) -> dict[str, str]:
        del namespace
        return {}


def test_remote_partial_write_falls_back_locally_and_rerun_skips_durable_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: remote storage persists only the first field and local fallback is available.
    pair = _pair()
    remote_backend = _LocalBackend(fail_private_key=True)
    local_backend = _LocalBackend()
    remote = SecretsStore(local_store=remote_backend)
    fallback = SecretsStore(local_store=local_backend)
    adapter = Phase45Adapter(
        SecretsSelection(store=remote, backend="infisical", fallback_store=fallback),
        lambda: pair,
    )
    monkeypatch.setenv("KEY_REF", _plain(pair.api_key))
    monkeypatch.setenv("PEM_REF", _plain(pair.private_key_pem))
    request = _request(
        kalshi_api_key_env="KEY_REF",
        kalshi_private_key_pem_env="PEM_REF",
        secret_approvals={"reconcile_incomplete": True},
    )

    # When: the remote fault occurs twice with a durable first field.
    first = adapter.provision_secrets(request)
    second = adapter.provision_secrets(request)

    # Then: local fallback succeeds and the durable remote API field is never rewritten.
    assert first.status is StepStatus.COMPLETED
    assert second.status is StepStatus.COMPLETED
    assert remote_backend.set_calls == [("kalshi", "api_key")]
    assert local_backend.set_calls == [
        ("kalshi", "api_key"),
        ("kalshi", "private_key_pem"),
    ]
    rendered = first.message + second.message
    assert _plain(pair.api_key) not in rendered
    assert _plain(pair.private_key_pem) not in rendered
