"""Adapter state persistence for BayesianAdapter.

Provides JSON-based, atomic persistence of the BayesianAdapter state
with a small versioned schema and profile-aware path resolution.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


def _ensure_parent_dir(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.debug("Could not create parent directory for state file: %s", path, exc_info=True)


class AdapterState(BaseModel):
    """Persistent JSON state for BayesianAdapter.

    version: schema version for forward compatibility.
    update_timestamps: ISO-formatted timestamps (UTC) as strings.
    drift_counts: per-parameter drift counters.
    distribution_states: serialised distribution parameter states.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    version: int = 1
    update_timestamps: list[str]  # ISO 8601 strings
    drift_counts: dict[str, int]
    distribution_states: dict[str, Any]


class AdapterStateStore:
    """Persist and load AdapterState to/from JSON files.

    Uses atomic writes via a temporary file and os.rename for safety.
    """

    @staticmethod
    def _to_state(
        update_timestamps: list[datetime],
        drift_counts: dict[str, int],
        distribution_states: dict[str, Any],
    ) -> AdapterState:
        ts_strs = [ts.isoformat() for ts in update_timestamps]
        return AdapterState(
            update_timestamps=ts_strs,
            drift_counts=dict(drift_counts),
            distribution_states=dict(distribution_states),
        )

    @staticmethod
    def save(
        *,
        update_timestamps: list[datetime],
        drift_counts: dict[str, int],
        distribution_states: dict[str, Any],
        path: Path | None,
    ) -> None:
        """Persist state to a JSON file atomically if a path is provided."""
        if path is None:
            return
        state = AdapterStateStore._to_state(update_timestamps, drift_counts, distribution_states)
        _tmp_path = path.parent / (path.name + ".tmp")
        _data = state.model_dump()
        _ensure_parent_dir(path)
        try:
            with open(_tmp_path) as f:
                json.dump(_data, f, indent=2, default=str)
            os.rename(_tmp_path, path)
        except Exception:
            logger.warning("Failed to persist adapter state to %s", path, exc_info=True)
            # Clean up temp file if present
            try:
                if _tmp_path.exists():
                    _tmp_path.unlink()
            except Exception:
                pass

    @staticmethod
    def load(path: Path | None) -> AdapterState | None:
        """Load persisted state from disk. Returns AdapterState or None if not available/damaged."""
        if path is None:
            return None
        if not path.exists():
            return None
        try:
            with open(path) as f:
                data = json.load(f)
            return AdapterState(**data)
        except Exception:
            logger.warning("Corrupted or unreadable adapter state at %s", path, exc_info=True)
            return None

    @staticmethod
    def timestamps_to_datetime(timestamps: list[str]) -> list[datetime]:
        """Convert list of ISO timestamp strings to datetime objects (UTC)."""
        result: list[datetime] = []
        for ts in timestamps:
            try:
                dt = datetime.fromisoformat(ts)
            except ValueError:
                # Fallback: if parsing fails, skip the entry
                continue
            result.append(dt)
        return result


def resolve_state_path(state_path: Path | None, profile_base_dir: str | None) -> Path | None:
    """Resolve the adapter state path.

    - If an explicit path is provided, use it.
    - Otherwise, use a default profile-aware path:
      {profile_base_dir or .traderbot}/adaptation_state.json
    """
    if state_path is not None:
        return Path(state_path)
    base = Path(profile_base_dir) if profile_base_dir else Path(".traderbot")
    return base / "adaptation_state.json"
