"""Adapter state persistence for BayesianAdapter.

Versioned JSON persistence with atomic writes (temp + rename) for
crash safety and profile-aware path resolution.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

_CURRENT_VERSION = 1


class AdapterState(BaseModel):
    """Serialised BayesianAdapter state for JSON persistence."""

    model_config = ConfigDict(strict=True, extra="forbid")

    version: int = _CURRENT_VERSION
    update_timestamps: list[str] = Field(default_factory=list)
    drift_counts: dict[str, int] = Field(default_factory=dict)
    distribution_states: dict[str, Any] = Field(default_factory=dict)


class AdapterStateStore:
    """Atomic JSON persistence for BayesianAdapter state.

    Writes to a temp file in the target directory, then renames
    for crash-safe atomicity. Gracefully handles corrupt or missing files.
    """

    @staticmethod
    def save(
        update_timestamps: list[datetime],
        drift_counts: dict[str, int],
        distribution_states: dict[str, Any],
        path: Path,
    ) -> None:
        """Persist adapter state to disk via atomic write."""
        state = AdapterState(
            version=_CURRENT_VERSION,
            update_timestamps=[ts.isoformat() for ts in update_timestamps],
            drift_counts=drift_counts,
            distribution_states=distribution_states,
        )

        path.parent.mkdir(parents=True, exist_ok=True)
        payload = state.model_dump_json(indent=2)

        fd, tmp_path = tempfile.mkstemp(
            suffix=".tmp",
            prefix=".adaptation_state_",
            dir=str(path.parent),
        )
        try:
            os.write(fd, payload.encode("utf-8"))
            os.close(fd)
            os.rename(tmp_path, str(path))
        except BaseException:
            with contextlib.suppress(OSError):
                os.close(fd)
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

    @staticmethod
    def load(path: Path) -> AdapterState | None:
        """Load adapter state from disk, returning None on missing or corrupt."""
        if not path.exists():
            return None

        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read adapter state from %s: %s", path, exc)
            return None

        try:
            state = AdapterState.model_validate(data)
        except Exception as exc:
            logger.warning("Invalid adapter state in %s: %s", path, exc)
            return None

        if state.version != _CURRENT_VERSION:
            logger.warning(
                "Adapter state version %d != current %d in %s, ignoring",
                state.version,
                _CURRENT_VERSION,
                path,
            )
            return None

        return state

    @staticmethod
    def timestamps_to_datetime(iso_strings: list[str]) -> list[datetime]:
        """Convert ISO 8601 timestamp strings back to timezone-aware datetime objects."""
        result: list[datetime] = []
        for s in iso_strings:
            try:
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                result.append(dt)
            except ValueError:
                logger.warning("Skipping invalid timestamp: %s", s)
        return result


def resolve_state_path(
    state_path: Path | None = None,
    profile_base_dir: str | None = None,
) -> Path:
    """Resolve the adapter state file path.

    Priority: explicit state_path > profile_base_dir > .traderbot default.
    """
    if state_path is not None:
        return state_path
    if profile_base_dir is not None:
        return Path(profile_base_dir) / "adaptation_state.json"
    return Path.home() / ".traderbot" / "adaptation_state.json"
