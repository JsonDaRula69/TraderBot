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

_CONFIG_KEY_PATTERN: Final = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)*$")
_run = run_bounded


class _ConfigReadStatus(StrEnum):
    FOUND = "found"
    MISSING = "missing"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class _ConfigRead[ValueT: BaseModel]:
    status: _ConfigReadStatus
    value: ValueT | None = None


def _read_config[ValueT: BaseModel](key: str, model: type[ValueT]) -> _ConfigRead[ValueT]:
    result = _run(["openclaw", "config", "get", key, "--json"], timeout=30.0)
    if result is None:
        return _ConfigRead(_ConfigReadStatus.FAILED)
    if result.returncode == 0:
        try:
            return _ConfigRead(_ConfigReadStatus.FOUND, model.model_validate_json(result.stdout))
        except ValidationError:
            return _ConfigRead(_ConfigReadStatus.FAILED)
    try:
        error = ConfigGetError.model_validate_json(result.stdout)
    except ValidationError:
        return _ConfigRead(_ConfigReadStatus.FAILED)
    status = (
        _ConfigReadStatus.MISSING
        if error.error.startswith("Config path not found:")
        else _ConfigReadStatus.FAILED
    )
    return _ConfigRead(status)


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
        secret_path = (
            "plugins.entries.traderbot-token-injector.config.agentTokenMap."
            f"{agent_id}"
        )
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


def _set_config(key: str, encoded: str) -> bool:
    if not _CONFIG_KEY_PATTERN.fullmatch(key):
        return False
    validated = _run(
        [
            "openclaw", "config", "set", key, encoded, "--strict-json", "--dry-run",
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


def set_secret_ref(agent_id: str, value: SecretRefConfig) -> bool:
    prefix = "plugins.entries.traderbot-token-injector.config.agentTokenMap"
    return _set_config(
        f"{prefix}.{agent_id}",
        value.model_dump_json(),
    )
