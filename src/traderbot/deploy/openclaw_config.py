"""Inspect and mutate typed OpenClaw configuration values."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ValidationError

from traderbot.deploy.openclaw_models import (
    AgentInventory,
    AgentRuntimeConfig,
    ConfigDryRun,
    ConfigGetError,
)
from traderbot.deploy.openclaw_process import run_bounded
from traderbot.deploy.wizard_state import (
    AgentConfigState,
    OpenClawConfigSnapshot,
    SecretRefConfig,
    SecretRefState,
)

# Deployed-shape write grammar: dotted segments, each optionally suffixed with
# numeric brackets (``agents.list[0].sandbox.docker.binds``). The pinned CLI's
# parsePath accepts dot/bracket notation; this pattern is its conservative
# subset — no escapes, no empty brackets, no non-numeric indexes.
_CONFIG_KEY_PATTERN: Final = re.compile(
    r"^[A-Za-z][A-Za-z0-9_-]*(?:\[\d+\])*(?:\.[A-Za-z0-9_-]+(?:\[\d+\])*)*$"
)
# Paths the pinned CLI refuses to replace wholesale (config-cli:558-560). The
# seam fails closed on them before any subprocess call (#526 asymmetry trap).
_PROTECTED_CONFIG_PATHS: Final = frozenset(
    {"agents.list", "plugins.entries", "agents.defaults.models", "models.providers"}
)
_MISSING_PATH_PREFIX: Final = "Config path not found:"
_run = run_bounded


class _ConfigReadStatus(StrEnum):
    FOUND = "found"
    MISSING = "missing"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class _ConfigRead[ValueT: BaseModel]:
    status: _ConfigReadStatus
    value: ValueT | None = None


def _missing_path_evidence(stream: str) -> bool:
    """Detect the CLI's missing-path error on one captured stream.

    Deployed OpenClaw 2026.7.1-2 prints ``Config path not found:`` to STDERR as
    plain text with empty STDOUT; the legacy CLI printed the typed JSON error
    envelope to STDOUT. Both channels are classified so the ``agents.list``
    fallback stays reachable across CLI generations.
    """
    try:
        error = ConfigGetError.model_validate_json(stream)
    except ValidationError:
        return _MISSING_PATH_PREFIX in stream
    return error.error.startswith(_MISSING_PATH_PREFIX)


def _read_config[ValueT: BaseModel](key: str, model: type[ValueT]) -> _ConfigRead[ValueT]:
    result = _run(["openclaw", "config", "get", key, "--json"], timeout=30.0)
    if result is None:
        return _ConfigRead(_ConfigReadStatus.FAILED)
    if result.returncode == 0:
        try:
            return _ConfigRead(_ConfigReadStatus.FOUND, model.model_validate_json(result.stdout))
        except ValidationError:
            return _ConfigRead(_ConfigReadStatus.FAILED)
    if _missing_path_evidence(result.stdout) or _missing_path_evidence(result.stderr):
        return _ConfigRead(_ConfigReadStatus.MISSING)
    return _ConfigRead(_ConfigReadStatus.FAILED)


def _state(agent_id: str, path: str, value: AgentRuntimeConfig) -> AgentConfigState:
    return AgentConfigState(
        agent_id=agent_id,
        path_prefix=path,
        heartbeat_every=None if value.heartbeat is None else value.heartbeat.every,
        sandbox_mode=None if value.sandbox is None else value.sandbox.mode,
    )


def _agent_config(agent_id: str, inventory: AgentInventory) -> AgentConfigState | None:
    entries_path = f"agents.entries.{agent_id}"
    entries = _read_config(entries_path, AgentRuntimeConfig)
    if entries.status is _ConfigReadStatus.FAILED:
        return None
    if entries.status is _ConfigReadStatus.FOUND:
        return None if entries.value is None else _state(agent_id, entries_path, entries.value)
    index = next(
        (position for position, agent in enumerate(inventory.root) if agent.id == agent_id),
        None,
    )
    if index is None:
        return AgentConfigState(agent_id=agent_id, path_prefix=f"agents.entries.{agent_id}")
    list_path = f"agents.list[{index}]"
    listed = _read_config(list_path, AgentRuntimeConfig)
    if listed.status is _ConfigReadStatus.MISSING:
        return None
    if listed.status is _ConfigReadStatus.FAILED or listed.value is None:
        return None
    return _state(agent_id, list_path, listed.value) if listed.value.id == agent_id else None


def inspect_config(
    agent_ids: tuple[str, ...],
    inventory: AgentInventory,
) -> OpenClawConfigSnapshot | None:
    agents: list[AgentConfigState] = []
    secret_refs: list[SecretRefState] = []
    inventory_ids = {agent.id for agent in inventory.root}
    for agent_id in agent_ids:
        if agent_id in inventory_ids:
            agent = _agent_config(agent_id, inventory)
            if agent is None:
                return None
            agents.append(agent)
        secret_path = f"plugins.entries.traderbot-token-injector.config.agentTokenMap.{agent_id}"
        secret = _read_config(secret_path, SecretRefConfig)
        if secret.status is _ConfigReadStatus.FAILED:
            return None
        secret_refs.append(
            SecretRefState(
                agent_id=agent_id,
                ref=secret.value if secret.status is _ConfigReadStatus.FOUND else None,
            )
        )
    return OpenClawConfigSnapshot(agents=tuple(agents), secret_refs=tuple(secret_refs))


def _valid_write_key(key: str) -> bool:
    return bool(_CONFIG_KEY_PATTERN.fullmatch(key)) and key not in _PROTECTED_CONFIG_PATHS


def _set_config(key: str, encoded: str) -> bool:
    if not _valid_write_key(key):
        return False
    validated = _run(
        [
            "openclaw",
            "config",
            "set",
            key,
            encoded,
            "--strict-json",
            "--dry-run",
            "--json",
        ],
        timeout=60.0,
    )
    if validated is None or validated.returncode != 0:
        return False
    try:
        _ = ConfigDryRun.model_validate_json(validated.stdout)
    except ValidationError:
        return False
    result = _run(
        ["openclaw", "config", "set", key, encoded, "--strict-json"],
        timeout=60.0,
    )
    return result is not None and result.returncode == 0


def set_config(key: str, value: str) -> bool:
    return _set_config(key, json.dumps(value))


def set_config_json(key: str, json_value: str) -> bool:
    """Write one pre-encoded JSON value (array/object/bool) at a bracket path.

    The value string is validated as JSON, then passed to the CLI byte-exactly
    (never reformatted), so a re-read through the same seam round-trips.
    """
    try:
        json.loads(json_value)
    except json.JSONDecodeError:
        return False
    return _set_config(key, json_value)


def unset_config(key: str) -> bool:
    """Remove one config key via ``config unset``; object leaves are deleted
    entirely (the key is absent after re-read, never null), matching the pinned
    CLI's ``unsetAtPath`` semantics that D8 rollback depends on.
    """
    if not _valid_write_key(key):
        return False
    validated = _run(
        ["openclaw", "config", "unset", key, "--dry-run", "--json"],
        timeout=60.0,
    )
    if validated is None or validated.returncode != 0:
        return False
    try:
        _ = ConfigDryRun.model_validate_json(validated.stdout)
    except ValidationError:
        return False
    result = _run(["openclaw", "config", "unset", key], timeout=60.0)
    return result is not None and result.returncode == 0


def agent_config_path(agent_id: str, inventory: AgentInventory) -> str | None:
    """Resolve the write-path prefix for a configured agent from CURRENT state.

    Reuses the entries-first + ``agents.list[i]`` fallback read (`_agent_config`)
    so the returned prefix names the shape the gateway actually serves; only
    configured (inventoried) agents resolve, and any read failure closes to None.
    """
    if agent_id not in {agent.id for agent in inventory.root}:
        return None
    state = _agent_config(agent_id, inventory)
    return None if state is None else state.path_prefix


def set_secret_ref(agent_id: str, value: SecretRefConfig) -> bool:
    prefix = "plugins.entries.traderbot-token-injector.config.agentTokenMap"
    return _set_config(
        f"{prefix}.{agent_id}",
        value.model_dump_json(),
    )
