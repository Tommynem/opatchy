from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Final, final

from .models import (
    NotificationOutcome,
    SnapshotResponse,
)
from .notification_batch import (
    NotificationBatch,
    claim_batch,
    complete_batch,
    failure_status,
    is_dispatchable,
)
from .notification_policy import notification_candidates
from .notification_types import (
    NotificationCandidate,
    NotificationChange,
    NotificationKind,
    NotificationRunner,
    NotificationSettings,
)
from .runner import run_command
from .runner_types import CommandName
from .storage import Storage

_DEFAULT_SETTINGS: Final = NotificationSettings()

__all__ = (
    "NotificationCandidate",
    "NotificationChange",
    "NotificationCoordinator",
    "NotificationKind",
    "NotificationRunner",
    "failure_status",
    "is_dispatchable",
    "notification_candidates",
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@final
class NotificationCoordinator:
    """Atomically persists deduplicated ordinary desktop-notification delivery."""

    def __init__(
        self,
        storage: Storage,
        run: NotificationRunner = run_command,
        clock: Callable[[], datetime] = _utc_now,
        *,
        settings: NotificationSettings = _DEFAULT_SETTINGS,
    ) -> None:
        self._storage = storage
        self._run = run
        self._clock = clock
        self._settings = settings

    def dispatch(self, snapshot: SnapshotResponse) -> tuple[NotificationOutcome, ...]:
        now = self._clock()
        state = self._storage.load_state().state
        candidates = notification_candidates(
            state, snapshot, now, self._settings, self._run
        )
        outcomes: list[NotificationOutcome] = []
        for kind in NotificationKind:
            batch = claim_batch(
                self._storage,
                kind,
                tuple(candidate for candidate in candidates if candidate.kind is kind),
                self._clock(),
            )
            if batch is None:
                continue
            outcomes.extend(self._dispatch(batch))
        return tuple(outcomes)

    def _dispatch(self, batch: NotificationBatch) -> tuple[NotificationOutcome, ...]:
        candidate = batch.candidates[0]
        result = self._run(CommandName.NOTIFY, (candidate.title, _body(batch)))
        return complete_batch(self._storage, batch, result)


def _body(batch: NotificationBatch) -> str:
    first = batch.candidates[0].body
    additional = len(batch.candidates) - 1
    label = "watched" if batch.kind is NotificationKind.WATCH else "security"
    return (
        first
        if additional == 0
        else f"{first} {additional} additional {label} update(s)."
    )
