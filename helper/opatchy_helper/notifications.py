from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import assert_never, final

from .models import (
    NotificationFingerprint,
    NotificationOutcome,
    NotificationStatus,
    SnapshotResponse,
)
from .notification_policy import notification_candidates
from .notification_types import (
    NotificationCandidate,
    NotificationChange,
    NotificationKind,
    NotificationRunner,
)
from .runner import run_command
from .runner_types import (
    CommandExited,
    CommandMissing,
    CommandName,
    CommandOutputExceeded,
    CommandRejected,
    CommandResult,
    CommandSucceeded,
    CommandTimedOut,
)
from .storage import Storage
from .storage_types import LedgerEntry, PersistentState

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
    ) -> None:
        self._storage = storage
        self._run = run
        self._clock = clock

    def dispatch(self, snapshot: SnapshotResponse) -> tuple[NotificationOutcome, ...]:
        now = self._clock()
        state = self._storage.load_state().state
        candidates = notification_candidates(state, snapshot, now)
        return tuple(
            self._dispatch(candidate)
            for kind in NotificationKind
            if (candidate := _first_dispatchable(candidates, state, kind)) is not None
        )

    def _dispatch(self, candidate: NotificationCandidate) -> NotificationOutcome:
        now = self._clock()
        _ = self._storage.update_state(lambda state: _reserve(state, candidate, now))
        result = self._run(CommandName.NOTIFY, (candidate.title, candidate.body))
        status = _delivery_status(result, candidate.change)
        _ = self._storage.update_state(
            lambda state: _replace_status(state, candidate.fingerprint, status)
        )
        return NotificationOutcome(candidate.fingerprint, status)


def _first_dispatchable(
    candidates: tuple[NotificationCandidate, ...],
    state: PersistentState,
    kind: NotificationKind,
) -> NotificationCandidate | None:
    return next(
        (
            candidate
            for candidate in candidates
            if candidate.kind is kind
            and is_dispatchable(_entry(state, candidate.fingerprint))
        ),
        None,
    )


def is_dispatchable(entry: LedgerEntry | None) -> bool:
    if entry is None:
        return True
    return _pending(entry.status)


def _reserve(
    state: PersistentState, candidate: NotificationCandidate, now: datetime
) -> PersistentState:
    if _entry(state, candidate.fingerprint) is not None:
        return state
    ledger = tuple(
        replace(entry, status=NotificationStatus.SUPPRESSED)
        if entry.is_active and str(entry.fingerprint).startswith(candidate.reference)
        else entry
        for entry in state.ledger
    )
    entry = LedgerEntry(candidate.fingerprint, NotificationStatus.PENDING, now)
    return PersistentState(state.watches, (*ledger, entry), state.sources)


def _replace_status(
    state: PersistentState,
    fingerprint: NotificationFingerprint,
    status: NotificationStatus,
) -> PersistentState:
    return PersistentState(
        state.watches,
        tuple(
            replace(entry, status=status)
            if entry.fingerprint == fingerprint
            and entry.status is NotificationStatus.PENDING
            else entry
            for entry in state.ledger
        ),
        state.sources,
    )


def _entry(
    state: PersistentState, fingerprint: NotificationFingerprint
) -> LedgerEntry | None:
    return next(
        (entry for entry in state.ledger if entry.fingerprint == fingerprint), None
    )


def failure_status(change: NotificationChange) -> NotificationStatus:
    match change:
        case NotificationChange.FIRST | NotificationChange.NEW:
            return NotificationStatus.PENDING
        case NotificationChange.UNCHANGED:
            return NotificationStatus.FAILED
    assert_never(change)


def _delivery_status(
    result: CommandResult, change: NotificationChange
) -> NotificationStatus:
    match result:
        case CommandSucceeded():
            return NotificationStatus.DELIVERED
        case (
            CommandExited()
            | CommandMissing()
            | CommandOutputExceeded()
            | CommandRejected()
            | CommandTimedOut()
        ):
            return failure_status(change)
    assert_never(result)


def _pending(status: NotificationStatus) -> bool:
    match status:
        case NotificationStatus.PENDING:
            return True
        case (
            NotificationStatus.DELIVERED
            | NotificationStatus.SUPPRESSED
            | NotificationStatus.FAILED
        ):
            return False
    assert_never(status)
