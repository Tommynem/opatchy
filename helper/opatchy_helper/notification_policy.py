from __future__ import annotations

import hashlib
from datetime import datetime
from html import escape
from typing import Final, assert_never

from .models import (
    ArchStatus,
    ItemSource,
    NotificationFingerprint,
    Provenance,
    SecurityFinding,
    Severity,
    SnapshotResponse,
    SourceHealth,
    SourceName,
    SourceStatus,
    WatchMode,
)
from .notification_types import (
    NotificationCandidate,
    NotificationChange,
    NotificationKind,
    NotificationSettings,
)
from .stars import watch_notification_reference
from .storage_types import LedgerEntry, PersistentState

_MAX_TEXT: Final = 256
_WATCH_TITLE: Final = "Watched update available"
_SECURITY_TITLE: Final = "Security update available"
_DEFAULT_SETTINGS: Final = NotificationSettings()


def notification_candidates(
    state: PersistentState,
    snapshot: SnapshotResponse,
    now: datetime,
    settings: NotificationSettings = _DEFAULT_SETTINGS,
) -> tuple[NotificationCandidate, ...]:
    """Return every fresh eligible candidate with durable identity classification."""
    candidates = (
        *_watch_candidates(state, snapshot, now, settings),
        *_security_candidates(state, snapshot, now, settings),
    )
    return tuple(
        sorted(
            candidates, key=lambda candidate: (candidate.kind, candidate.fingerprint)
        )
    )


def _watch_candidates(
    state: PersistentState,
    snapshot: SnapshotResponse,
    now: datetime,
    settings: NotificationSettings,
) -> tuple[NotificationCandidate, ...]:
    if not settings.notify_permanent:
        return ()
    watched_ids = frozenset(
        watch.item_id for watch in state.watches if watch.mode is WatchMode.PERMANENT
    )
    candidates: list[NotificationCandidate] = []
    for item in snapshot.payload.items:
        candidate = item.candidate
        if (
            item.item_id not in watched_ids
            or candidate is None
            or item.installed_fingerprint is None
            or item.candidate_fingerprint is None
            or not _fresh_item(snapshot, item.source, item.provenance, now)
        ):
            continue
        fingerprint = watch_notification_reference(
            item.item_id, item.candidate_fingerprint, item.installed_fingerprint
        )
        reference = f"watch-v1:{item.item_id}:"
        candidates.append(
            NotificationCandidate(
                fingerprint,
                reference,
                NotificationKind.WATCH,
                _change(state, fingerprint, reference),
                _WATCH_TITLE,
                f"Watched item {_text(item.label)} has update {_text(candidate)} available.",
            )
        )
    return tuple(candidates)


def _security_candidates(
    state: PersistentState,
    snapshot: SnapshotResponse,
    now: datetime,
    settings: NotificationSettings,
) -> tuple[NotificationCandidate, ...]:
    if not settings.notify_security or not _fresh_source(
        snapshot, SourceName.SECURITY, now
    ):
        return ()
    candidates: list[NotificationCandidate] = []
    for group in snapshot.payload.findings:
        for finding in group.findings:
            fixed = finding.fixed_version
            if fixed is None or not _eligible_security(
                finding, settings.security_minimum_severity
            ):
                continue
            reference_hash = _digest(
                ("security", str(finding.item_id), finding.advisory_id)
            )
            reference = f"security-v1:{reference_hash}:"
            fingerprint = NotificationFingerprint(
                f"{reference}{_digest((fixed, finding.severity.value))}"
            )
            candidates.append(
                NotificationCandidate(
                    fingerprint,
                    reference,
                    NotificationKind.SECURITY,
                    _change(state, fingerprint, reference),
                    _SECURITY_TITLE,
                    "Security update for "
                    + f"{_text(str(finding.item_id))}: {_text(finding.advisory_id)} "
                    + f"is fixed in {_text(fixed)} ({finding.severity.value}).",
                )
            )
    return tuple(candidates)


def _fresh_item(
    snapshot: SnapshotResponse,
    source: ItemSource,
    provenance: Provenance,
    now: datetime,
) -> bool:
    return _current_provenance(provenance) and _fresh_source(
        snapshot, _source_name(source), now
    )


def _fresh_source(
    snapshot: SnapshotResponse, source: SourceName, now: datetime
) -> bool:
    health = next(
        (health for health in snapshot.payload.sources if health.source is source), None
    )
    if health is None:
        return False
    return _current_provenance(health.provenance) and _fresh_status(health, now)


def _fresh_status(health: SourceHealth, now: datetime) -> bool:
    match health.status:
        case SourceStatus.OK:
            return health.observed_at <= now <= health.fresh_until
        case (
            SourceStatus.NOT_APPLICABLE
            | SourceStatus.MISSING_DEPENDENCY
            | SourceStatus.OFFLINE
            | SourceStatus.TIMEOUT
            | SourceStatus.ERROR
            | SourceStatus.INVALID
            | SourceStatus.STALE
        ):
            return False
    assert_never(health.status)


def _current_provenance(provenance: Provenance) -> bool:
    match provenance:
        case Provenance.LIVE | Provenance.CACHE | Provenance.FALLBACK:
            return True
        case Provenance.LAST_GOOD:
            return False
    assert_never(provenance)


def _source_name(source: ItemSource) -> SourceName:
    match source:
        case ItemSource.OMARCHY:
            return SourceName.OMARCHY
        case ItemSource.ARCH:
            return SourceName.ARCH
        case ItemSource.AUR:
            return SourceName.AUR
        case ItemSource.FLATPAK:
            return SourceName.FLATPAK
        case ItemSource.MISE:
            return SourceName.MISE
    assert_never(source)


def _eligible_security(finding: SecurityFinding, minimum: Severity) -> bool:
    return (
        str(finding.item_id).startswith("arch:")
        and _current_provenance(finding.provenance)
        and _fixed(finding.status)
        and _notifiable_severity(finding.severity, minimum)
    )


def _fixed(status: ArchStatus) -> bool:
    match status:
        case ArchStatus.FIXED:
            return True
        case (
            ArchStatus.UNKNOWN
            | ArchStatus.VULNERABLE
            | ArchStatus.TESTING
            | ArchStatus.NOT_AFFECTED
        ):
            return False
    assert_never(status)


def _notifiable_severity(severity: Severity, minimum: Severity) -> bool:
    match severity:
        case Severity.CRITICAL:
            return True
        case Severity.HIGH:
            return minimum is not Severity.CRITICAL
        case Severity.UNKNOWN | Severity.LOW | Severity.MEDIUM:
            return False
    assert_never(severity)


def _change(
    state: PersistentState, fingerprint: NotificationFingerprint, reference: str
) -> NotificationChange:
    if _entry(state, fingerprint) is not None:
        return NotificationChange.UNCHANGED
    if any(str(entry.fingerprint).startswith(reference) for entry in state.ledger):
        return NotificationChange.NEW
    return NotificationChange.FIRST


def _entry(
    state: PersistentState, fingerprint: NotificationFingerprint
) -> LedgerEntry | None:
    return next(
        (entry for entry in state.ledger if entry.fingerprint == fingerprint), None
    )


def _digest(parts: tuple[str, ...]) -> str:
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()


def _text(value: str) -> str:
    return escape(value.replace("\0", "?")[:_MAX_TEXT], quote=True)
