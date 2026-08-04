"""Profile-token rotation — Infisical-only, 4-hour cycle (DD-037 §4).

:class:`TokenRotationManager` rotates every stored profile token through the
:class:`SecretsStore` (``rotate_profile_token``, which composes to
``set(service=agent_id, key="token", namespace="tokens")``). Rotation is
**Infisical-only**: a store without an Infisical client (local fallback)
raises :class:`NotImplementedError` — local tokens are never auto-rotated.

Each agent's rotation failures are tracked in memory; after 24 hours of
continuous failure the profile name is added to
``mcp.resolver._SUSPENDED_PROFILES``, so the MCP resolver stops accepting its
token (a suspended profile is indistinguishable from an invalid token).

:class:`RotationScheduler` runs the rotation as an asyncio background task
under an :class:`asyncio.Lock` — the token store is not thread-safe, so
``threading.Timer`` is deliberately avoided. The module-level
:func:`start_scheduler` / :func:`stop_scheduler` pair is wired into the MCP
server lifecycle.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import time
from typing import Final

from traderbot.mcp.resolver import _SUSPENDED_PROFILES
from traderbot.secrets.store import SecretsStore

logger = logging.getLogger(__name__)

#: Hours of continuous rotation failure before a profile is administratively
#: suspended (DD-037 §4). The MCP resolver treats a suspended profile as an
#: invalid token.
_SUSPENSION_THRESHOLD_HOURS: Final = 24.0

#: Default rotation interval for :class:`RotationScheduler`.
DEFAULT_INTERVAL_HOURS: Final = 4.0


class TokenRotationManager:
    """Rotates profile tokens in the Infisical-backed store.

    Args:
        secrets_store: The unified secrets store. Rotation requires an
            Infisical client; a local-only store raises
            :class:`NotImplementedError`.
    """

    def __init__(self, secrets_store: SecretsStore) -> None:
        self._store: SecretsStore = secrets_store
        #: First-failure wall-clock timestamp per agent (continuous-failure window).
        self._failures: dict[str, float] = {}
        #: Last successful rotation wall-clock timestamp per agent.
        self._rotated_at: dict[str, float] = {}

    def _require_infisical(self) -> None:
        """Raise :class:`NotImplementedError` for a local-only store."""
        if self._store._infisical_client is None:
            raise NotImplementedError(
                "Token rotation requires the Infisical backend; "
                "local-only stores are not auto-rotated"
            )

    def rotate_all(self) -> dict[str, str]:
        """Rotate every stored profile token; return ``{agent_id: new_token}``.

        A failed agent is skipped (its failure is tracked for the 24-hour
        suspension window) so one failure cannot abort the rest of the fleet.

        Raises:
            NotImplementedError: if the store has no Infisical client.
        """
        self._require_infisical()
        rotated: dict[str, str] = {}
        for entry in self._store.list_profile_tokens():
            agent_id = entry["agent_id"]
            try:
                rotated[agent_id] = self.rotate_one(agent_id)
            except Exception:
                # Per-agent isolation boundary: a store/transport failure for
                # one agent must not abort rotation of the others.
                logger.exception("Token rotation failed for agent_id=%s", agent_id)
                self._record_failure(agent_id)
        return rotated

    def rotate_one(self, agent_id: str) -> str:
        """Rotate one agent's profile token; return the new token.

        Raises:
            NotImplementedError: if the store has no Infisical client.
            KeyError: if ``agent_id`` has no stored profile token.
        """
        self._require_infisical()
        new_token = secrets.token_urlsafe(32)
        self._store.rotate_profile_token(agent_id, new_token)
        _ = self._failures.pop(agent_id, None)
        self._rotated_at[agent_id] = time.time()
        return new_token

    def get_staleness(self) -> dict[str, float]:
        """Return ``{agent_id: hours_since_rotation}`` for every stored token.

        Hours are measured from the manager's last successful rotation of each
        agent (wall clock). Agents never rotated by this manager instance are
        omitted.
        """
        now = time.time()
        staleness: dict[str, float] = {}
        for entry in self._store.list_profile_tokens():
            agent_id = entry["agent_id"]
            rotated_at = self._rotated_at.get(agent_id)
            if rotated_at is not None:
                staleness[agent_id] = max(0.0, (now - rotated_at) / 3600.0)
        return staleness

    def _record_failure(self, agent_id: str) -> None:
        """Track a rotation failure; suspend the profile after 24h continuous failure."""
        now = time.time()
        first = self._failures.get(agent_id)
        if first is None:
            self._failures[agent_id] = now
            return
        if (now - first) / 3600.0 >= _SUSPENSION_THRESHOLD_HOURS:
            _ = _SUSPENDED_PROFILES.add(agent_id)
            logger.warning("Suspending profile %s after 24h of rotation failures", agent_id)
            _ = self._failures.pop(agent_id, None)


class RotationScheduler:
    """Asyncio background task that fires :meth:`TokenRotationManager.rotate_all`.

    The loop runs under an :class:`asyncio.Lock` because the token store is
    not thread-safe — the scheduler must never run concurrently with itself or
    with a manual rotation. ``threading.Timer`` is deliberately avoided.
    """

    def __init__(self, manager: TokenRotationManager, interval_hours: float = 4.0) -> None:
        self._manager: TokenRotationManager = manager
        self._interval_hours: float = interval_hours
        self._lock: asyncio.Lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the background rotation loop (idempotent)."""
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Cancel the background rotation loop and await its completion."""
        task = self._task
        if task is None:
            return
        self._task = None
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _run(self) -> None:
        """Rotate all tokens every ``interval_hours`` until cancelled."""
        while True:
            await asyncio.sleep(self._interval_hours * 3600.0)
            async with self._lock:
                try:
                    _ = self._manager.rotate_all()
                except Exception:
                    # Keep the loop alive across unexpected failures (e.g. a
                    # store that became local-only mid-flight).
                    logger.exception("Scheduled token rotation failed")


_scheduler: RotationScheduler | None = None


def _build_store() -> SecretsStore:
    """Build the process-wide store via the SecretsResolver (Infisical primary).

    The resolver falls back to the local encrypted store when Infisical is
    unreachable; rotation then raises :class:`NotImplementedError` on each
    cycle, which the scheduler logs.
    """
    from traderbot.secrets.resolver import get_resolver

    return get_resolver()._store


async def start_scheduler() -> None:
    """Start the process-wide rotation scheduler (idempotent)."""
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = RotationScheduler(TokenRotationManager(_build_store()))
    await _scheduler.start()


async def stop_scheduler() -> None:
    """Stop the process-wide rotation scheduler (no-op if never started)."""
    global _scheduler
    if _scheduler is None:
        return
    scheduler = _scheduler
    _scheduler = None
    await scheduler.stop()
