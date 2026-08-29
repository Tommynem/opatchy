import hashlib
from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Final, assert_never

from .adapters.arch import (
    ArchDegraded,
    CommandRunner,
    VersionComparison,
    compare_versions,
)
from .models import (
    ArchStatus,
    FindingId,
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
from .storage_types import (
    LedgerEntry,
    PersistentState,
    SecurityFixCondition,
    WatchRecord,
)

_TITLE: Final = "Security fix update available"
_MAX_TEXT: Final = 256


@dataclass(frozen=True, slots=True)
class ConditionalSecurityCandidate:
    candidate: NotificationCandidate
    finding_id: FindingId


def conditional_security_owned_findings(
    state: PersistentState, snapshot: SnapshotResponse
) -> frozenset[FindingId]:
    return frozenset(
        finding.finding_id
        for watch in state.watches
        if watch.mode is WatchMode.TEMPORARY
        for condition in (watch.condition,)
        if condition is not None
        for finding in (_matching_finding(snapshot, watch, condition),)
        if finding is not None
    )


def conditional_security_candidates(
    state: PersistentState,
    snapshot: SnapshotResponse,
    now: datetime,
    settings: NotificationSettings,
    run: CommandRunner,
) -> tuple[ConditionalSecurityCandidate, ...]:
    if not settings.notify_security or not (
        _fresh_source(snapshot, SourceName.ARCH, now)
        and _fresh_source(snapshot, SourceName.SECURITY, now)
    ):
        return ()
    candidates: list[ConditionalSecurityCandidate] = []
    for watch in state.watches:
        match watch.condition:
            case None:
                continue
            case condition:
                candidate = _candidate(state, snapshot, watch, condition, settings, run)
                if candidate is not None:
                    candidates.append(candidate)
    return tuple(candidates)


def _candidate(
    state: PersistentState,
    snapshot: SnapshotResponse,
    watch: WatchRecord,
    condition: SecurityFixCondition,
    settings: NotificationSettings,
    run: CommandRunner,
) -> ConditionalSecurityCandidate | None:
    if watch.mode is not WatchMode.TEMPORARY:
        return None
    item = next(
        (
            value
            for value in snapshot.payload.items
            if value.item_id == watch.item_id
            and value.source is ItemSource.ARCH
            and value.candidate is not None
            and _live(value.provenance)
        ),
        None,
    )
    if item is None or item.candidate is None:
        return None
    finding = _matching_finding(snapshot, watch, condition)
    if (
        finding is None
        or finding.status is not ArchStatus.FIXED
        or not _live(finding.provenance)
        or not _notifiable(finding.severity, settings.security_minimum_severity)
    ):
        return None
    comparison = compare_versions(run, item.candidate, condition.fixed_version)
    match comparison:
        case VersionComparison(sign=sign) if sign >= 0:
            return ConditionalSecurityCandidate(
                _notification(state.ledger, watch, condition, item.candidate),
                finding.finding_id,
            )
        case VersionComparison() | ArchDegraded():
            return None
    assert_never(comparison)


def _matching_finding(
    snapshot: SnapshotResponse,
    watch: WatchRecord,
    condition: SecurityFixCondition,
) -> SecurityFinding | None:
    return next(
        (
            finding
            for group in snapshot.payload.findings
            if group.item_id == watch.item_id
            for finding in group.findings
            if finding.item_id == watch.item_id
            and finding.advisory_id == condition.advisory_id
            and finding.fixed_version == condition.fixed_version
            and frozenset(finding.cve_ids) == frozenset(condition.cve_ids)
        ),
        None,
    )


def _notification(
    ledger: tuple[LedgerEntry, ...],
    watch: WatchRecord,
    condition: SecurityFixCondition,
    candidate: str,
) -> NotificationCandidate:
    reference = f"security-condition-v1:{watch.item_id}:{condition.advisory_id}:"
    fingerprint = NotificationFingerprint(
        reference + _digest((condition.fixed_version, candidate, *condition.cve_ids))
    )
    change = _change(ledger, fingerprint, reference)
    cves = ", ".join(condition.cve_ids)
    return NotificationCandidate(
        fingerprint,
        reference,
        NotificationKind.SECURITY_CONDITION,
        change,
        _TITLE,
        "Security condition for "
        + f"{_text(str(watch.item_id))}: {_text(condition.advisory_id)} "
        + f"({_text(cves)}); installable candidate {_text(candidate)}; "
        + f"fixed version {_text(condition.fixed_version)}.",
    )


def _fresh_source(
    snapshot: SnapshotResponse, source: SourceName, now: datetime
) -> bool:
    health = next(
        (value for value in snapshot.payload.sources if value.source is source), None
    )
    return (
        health is not None and _live(health.provenance) and _fresh_status(health, now)
    )


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


def _live(provenance: Provenance) -> bool:
    match provenance:
        case Provenance.LIVE:
            return True
        case Provenance.CACHE | Provenance.FALLBACK | Provenance.LAST_GOOD:
            return False
    assert_never(provenance)


def _notifiable(severity: Severity, minimum: Severity) -> bool:
    match severity:
        case Severity.CRITICAL:
            return True
        case Severity.HIGH:
            return minimum is not Severity.CRITICAL
        case Severity.UNKNOWN | Severity.LOW | Severity.MEDIUM:
            return False
    assert_never(severity)


def _change(
    ledger: tuple[LedgerEntry, ...],
    fingerprint: NotificationFingerprint,
    reference: str,
) -> NotificationChange:
    entry = next((value for value in ledger if value.fingerprint == fingerprint), None)
    if entry is not None:
        return NotificationChange.UNCHANGED
    return (
        NotificationChange.NEW
        if any(str(value.fingerprint).startswith(reference) for value in ledger)
        else NotificationChange.FIRST
    )


def _digest(values: tuple[str, ...]) -> str:
    return hashlib.sha256("\0".join(values).encode()).hexdigest()


def _text(value: str) -> str:
    return escape(value, quote=False)[:_MAX_TEXT]
