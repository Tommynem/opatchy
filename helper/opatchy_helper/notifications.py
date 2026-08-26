from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Final, assert_never, final
from uuid import uuid4

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
    NotificationSettings,
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

_LEASE_DURATION: Final = timedelta(seconds=30)
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
        candidates = notification_candidates(state, snapshot, now, self._settings)
        outcomes: list[NotificationOutcome] = []
        for kind in NotificationKind:
            candidate = _first_dispatchable(candidates, state, kind)
            if candidate is None:
                continue
            outcome = self._dispatch(candidate)
            if outcome is not None:
                outcomes.append(outcome)
        return tuple(outcomes)

    def _dispatch(self, candidate: NotificationCandidate) -> NotificationOutcome | None:
        now = self._clock()
        lease_token = uuid4().hex
        claimed = self._storage.update_state(
            lambda state: _reserve(state, candidate, now, lease_token)
        ).state
        if not _owns_lease(claimed, candidate.fingerprint, lease_token):
            return None
        result = self._run(CommandName.NOTIFY, (candidate.title, candidate.body))
        status = _delivery_status(result, candidate.change)
        _ = self._storage.update_state(
            lambda state: _replace_status(
                state, candidate.fingerprint, status, lease_token
            )
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
    state: PersistentState,
    candidate: NotificationCandidate,
    now: datetime,
    lease_token: str,
) -> PersistentState:
    existing = _entry(state, candidate.fingerprint)
    if existing is not None:
        if not _can_claim(existing, now):
            return state
        return _replace_entry(
            state,
            replace(
                existing,
                lease_token=lease_token,
                lease_expires_at=now + _LEASE_DURATION,
            ),
        )
    ledger = tuple(
        replace(entry, status=NotificationStatus.SUPPRESSED)
        if entry.is_active and str(entry.fingerprint).startswith(candidate.reference)
        else entry
        for entry in state.ledger
    )
    entry = LedgerEntry(
        candidate.fingerprint,
        NotificationStatus.PENDING,
        now,
        lease_token,
        now + _LEASE_DURATION,
    )
    return PersistentState(state.watches, (*ledger, entry), state.sources)


def _replace_status(
    state: PersistentState,
    fingerprint: NotificationFingerprint,
    status: NotificationStatus,
    lease_token: str,
) -> PersistentState:
    return PersistentState(
        state.watches,
        tuple(
            replace(entry, status=status, lease_token=None, lease_expires_at=None)
            if entry.fingerprint == fingerprint
            and entry.status is NotificationStatus.PENDING
            and entry.lease_token == lease_token
            else entry
            for entry in state.ledger
        ),
        state.sources,
    )


def _replace_entry(state: PersistentState, updated: LedgerEntry) -> PersistentState:
    return PersistentState(
        state.watches,
        tuple(
            updated if entry.fingerprint == updated.fingerprint else entry
            for entry in state.ledger
        ),
        state.sources,
    )


def _owns_lease(
    state: PersistentState, fingerprint: NotificationFingerprint, lease_token: str
) -> bool:
    entry = _entry(state, fingerprint)
    return entry is not None and entry.lease_token == lease_token


def _can_claim(entry: LedgerEntry, now: datetime) -> bool:
    return entry.status is NotificationStatus.PENDING and (
        entry.lease_expires_at is None or entry.lease_expires_at <= now
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
