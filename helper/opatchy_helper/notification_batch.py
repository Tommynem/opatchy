from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Final, assert_never
from uuid import uuid4

from .models import NotificationFingerprint, NotificationOutcome, NotificationStatus
from .notification_types import (
    NotificationCandidate,
    NotificationChange,
    NotificationKind,
)
from .runner_types import (
    CommandExited,
    CommandMissing,
    CommandOutputExceeded,
    CommandRejected,
    CommandResult,
    CommandSucceeded,
    CommandTimedOut,
)
from .storage import Storage
from .storage_types import LedgerEntry, PersistentState

_LEASE_DURATION: Final = timedelta(seconds=30)


@dataclass(frozen=True, slots=True)
class NotificationBatch:
    kind: NotificationKind
    candidates: tuple[NotificationCandidate, ...]
    lease_token: str


def claim_batch(
    storage: Storage,
    kind: NotificationKind,
    candidates: tuple[NotificationCandidate, ...],
    now: datetime,
) -> NotificationBatch | None:
    token = uuid4().hex
    state = storage.update_state(
        lambda current: _reserve_batch(current, kind, candidates, now, token)
    ).state
    claimed = tuple(
        candidate
        for candidate in candidates
        if _owned_by(_entry(state, candidate.fingerprint), token)
    )
    return (
        None
        if not claimed or not _owns_owner(state, kind, token)
        else NotificationBatch(kind, claimed, token)
    )


def complete_batch(
    storage: Storage, batch: NotificationBatch, result: CommandResult
) -> tuple[NotificationOutcome, ...]:
    completed: frozenset[NotificationFingerprint] = frozenset()

    def complete(current: PersistentState) -> PersistentState:
        nonlocal completed
        state, completed = _complete_batch(current, batch, result)
        return state

    _ = storage.update_state(complete)
    return tuple(
        NotificationOutcome(
            candidate.fingerprint, _delivery_status(result, candidate.change)
        )
        for candidate in batch.candidates
        if candidate.fingerprint in completed
    )


def is_dispatchable(entry: LedgerEntry | None) -> bool:
    return entry is None or _pending(entry.status)


def failure_status(change: NotificationChange) -> NotificationStatus:
    match change:
        case (
            NotificationChange.FIRST
            | NotificationChange.NEW
            | NotificationChange.UNCHANGED
        ):
            return NotificationStatus.PENDING
    assert_never(change)


def _reserve_batch(
    state: PersistentState,
    kind: NotificationKind,
    candidates: tuple[NotificationCandidate, ...],
    now: datetime,
    token: str,
) -> PersistentState:
    owner = _entry(state, _owner_fingerprint(kind))
    if owner is not None and _live_lease(owner, now):
        return state
    claimed = tuple(
        candidate
        for candidate in candidates
        if _claimable(_entry(state, candidate.fingerprint), now)
    )
    if not claimed:
        return state
    ledger = _suppress_superseded(state.ledger, claimed)
    for candidate in claimed:
        ledger = _upsert(
            ledger,
            LedgerEntry(
                candidate.fingerprint,
                NotificationStatus.PENDING,
                now,
                token,
                now + _LEASE_DURATION,
            ),
        )
    ledger = _upsert(
        ledger,
        LedgerEntry(
            _owner_fingerprint(kind),
            NotificationStatus.PENDING,
            now,
            token,
            now + _LEASE_DURATION,
        ),
    )
    return PersistentState(state.watches, ledger, state.sources)


def _complete_batch(
    state: PersistentState, batch: NotificationBatch, result: CommandResult
) -> tuple[PersistentState, frozenset[NotificationFingerprint]]:
    if not _owns_owner(state, batch.kind, batch.lease_token):
        return state, frozenset()
    updates = {
        candidate.fingerprint: _delivery_status(result, candidate.change)
        for candidate in batch.candidates
    }
    completed = frozenset(
        entry.fingerprint
        for entry in state.ledger
        if entry.fingerprint in updates and _owned_by(entry, batch.lease_token)
    )
    ledger = tuple(
        replace(
            entry,
            status=updates[entry.fingerprint],
            lease_token=None,
            lease_expires_at=None,
        )
        if entry.fingerprint in updates and _owned_by(entry, batch.lease_token)
        else entry
        for entry in state.ledger
        if entry.fingerprint != _owner_fingerprint(batch.kind)
    )
    return PersistentState(state.watches, ledger, state.sources), completed


def _suppress_superseded(
    ledger: tuple[LedgerEntry, ...], candidates: tuple[NotificationCandidate, ...]
) -> tuple[LedgerEntry, ...]:
    fingerprints = frozenset(candidate.fingerprint for candidate in candidates)
    references = tuple(candidate.reference for candidate in candidates)
    return tuple(
        replace(entry, status=NotificationStatus.SUPPRESSED)
        if entry.fingerprint not in fingerprints
        and entry.is_active
        and any(
            str(entry.fingerprint).startswith(reference) for reference in references
        )
        else entry
        for entry in ledger
    )


def _upsert(
    ledger: tuple[LedgerEntry, ...], updated: LedgerEntry
) -> tuple[LedgerEntry, ...]:
    return (
        tuple(
            updated if entry.fingerprint == updated.fingerprint else entry
            for entry in ledger
        )
        if any(entry.fingerprint == updated.fingerprint for entry in ledger)
        else (*ledger, updated)
    )


def _claimable(entry: LedgerEntry | None, now: datetime) -> bool:
    return entry is None or (_pending(entry.status) and not _live_lease(entry, now))


def _owns_owner(state: PersistentState, kind: NotificationKind, token: str) -> bool:
    return _owned_by(_entry(state, _owner_fingerprint(kind)), token)


def _owned_by(entry: LedgerEntry | None, token: str) -> bool:
    return entry is not None and entry.lease_token == token


def _live_lease(entry: LedgerEntry, now: datetime) -> bool:
    return (
        entry.lease_token is not None
        and entry.lease_expires_at is not None
        and entry.lease_expires_at > now
    )


def _entry(
    state: PersistentState, fingerprint: NotificationFingerprint
) -> LedgerEntry | None:
    return next(
        (entry for entry in state.ledger if entry.fingerprint == fingerprint), None
    )


def _owner_fingerprint(kind: NotificationKind) -> NotificationFingerprint:
    return NotificationFingerprint(f"notification-owner-v1:{kind.value}")


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
            | CommandTimedOut()
        ):
            return failure_status(change)
        case CommandRejected():
            return NotificationStatus.FAILED
    assert_never(result)
