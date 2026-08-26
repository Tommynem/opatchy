import hashlib
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Final

from .models import (
    ErrorCode,
    ErrorInfo,
    GenerationId,
    InventoryPayload,
    InventoryResponse,
    ItemId,
    ItemSource,
    NormalizedItem,
    ProtocolError,
    Provenance,
    ScanState,
    ScopeHealth,
    SecurityFindingGroup,
    SourceHealth,
    SourceName,
    SourceStatus,
    Summary,
    WatchMode,
)
from .scan_outcomes import SourceOutcome, successful
from .scan_resolution import ResolvedOutcome
from .storage_generation import GenerationBundle
from .storage_types import SourceMetadata

RETRY_DELAYS: Final = (
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
    timedelta(hours=6),
)
_OMARCHY_SYSTEM_IDS: Final = frozenset(
    (ItemId("arch:omarchy"), ItemId("arch:omarchy-dev"))
)
type SourceOutcomeGroups = tuple[
    tuple[SourceName, tuple[SourceOutcome | None, ...]], ...
]


def source_healths(
    resolved: tuple[ResolvedOutcome, ...], now: datetime
) -> tuple[SourceHealth, ...]:
    basic = tuple(
        _source_health(value)
        for value in resolved
        if value.outcome.source is not SourceName.FLATPAK
    )
    user, system = (
        value for value in resolved if value.outcome.source is SourceName.FLATPAK
    )
    user_health = _scope_health(user)
    system_health = _scope_health(system)
    flatpak = SourceHealth(
        SourceName.FLATPAK,
        _flatpak_status(user_health, system_health),
        _flatpak_provenance(user_health, system_health),
        now,
        min(user_health.fresh_until, system_health.fresh_until),
        _flatpak_cause(user_health, system_health),
        (user_health, system_health),
    )
    return tuple(sorted((*basic, flatpak), key=lambda health: health.source.value))


def normalized_items(
    resolved: tuple[ResolvedOutcome, ...],
) -> tuple[NormalizedItem, ...]:
    items = tuple(
        item
        for outcome in resolved
        for item in outcome.items
        if item.item_id not in _OMARCHY_SYSTEM_IDS
    )
    fingerprints = tuple(_fingerprinted(item) for item in items)
    if len({item.item_id for item in fingerprints}) != len(fingerprints):
        raise ProtocolError(
            ErrorInfo(ErrorCode.DUPLICATE_ITEM_ID, "scan item IDs are duplicated")
        )
    return tuple(sorted(fingerprints, key=lambda item: str(item.item_id)))


def normalized_findings(
    resolved: tuple[ResolvedOutcome, ...],
) -> tuple[SecurityFindingGroup, ...]:
    groups = tuple(group for outcome in resolved for group in outcome.findings)
    return tuple(sorted(groups, key=lambda group: str(group.item_id)))


def summary(
    items: tuple[NormalizedItem, ...],
    findings: tuple[SecurityFindingGroup, ...],
    sources: tuple[SourceHealth, ...],
) -> Summary:
    return Summary(
        len(items),
        sum(item.watch_mode is not WatchMode.OFF for item in items),
        sum(len(group.findings) for group in findings),
        sum(
            source.status not in {SourceStatus.OK, SourceStatus.NOT_APPLICABLE}
            for source in sources
        ),
    )


def scan_state(resolved: tuple[ResolvedOutcome, ...]) -> ScanState:
    mandatory = tuple(
        value
        for value in resolved
        if value.outcome.source
        in {SourceName.OMARCHY, SourceName.ARCH, SourceName.SECURITY}
        or (value.outcome.source is SourceName.AUR and value.outcome.applicable)
    )
    if all(
        successful(value.outcome) and value.health.status is SourceStatus.OK
        for value in mandatory
    ):
        return ScanState.COMPLETE
    if any(value.usable for value in mandatory):
        return ScanState.PARTIAL
    return ScanState.FAILED


def inventories(
    generated_at: datetime,
    generation_id: GenerationId,
    items: tuple[NormalizedItem, ...],
) -> tuple[InventoryResponse, ...]:
    return tuple(
        InventoryResponse(
            generated_at,
            generation_id,
            InventoryPayload(source, len(source_items), source_items),
        )
        for source in (
            ItemSource.ARCH,
            ItemSource.AUR,
            ItemSource.FLATPAK,
            ItemSource.MISE,
        )
        if (source_items := tuple(item for item in items if item.source is source))
    )


def last_good_keys(
    previous: GenerationBundle | None, resolved: tuple[ResolvedOutcome, ...]
) -> tuple[str, ...]:
    retained = () if previous is None else previous.last_good_keys
    return tuple(
        sorted(
            {
                *retained,
                *(value.outcome.key for value in resolved if successful(value.outcome)),
            }
        )
    )


def metadata(
    previous: tuple[SourceMetadata, ...],
    outcomes: SourceOutcomeGroups,
    now: datetime,
) -> tuple[SourceMetadata, ...]:
    return tuple(
        _next_metadata(
            source,
            current,
            next((entry for entry in previous if entry.source is source), None),
            now,
        )
        for source, current in outcomes
    )


def _scope_health(resolved: ResolvedOutcome) -> ScopeHealth:
    match resolved.health:
        case ScopeHealth() as health:
            return health
        case SourceHealth():
            raise ProtocolError(
                ErrorInfo(ErrorCode.INVALID_ENVELOPE, "Flatpak scope health is invalid")
            )


def _source_health(resolved: ResolvedOutcome) -> SourceHealth:
    match resolved.health:
        case SourceHealth() as health:
            return health
        case ScopeHealth():
            raise ProtocolError(
                ErrorInfo(ErrorCode.INVALID_ENVELOPE, "source health is scoped")
            )


def _flatpak_status(user: ScopeHealth, system: ScopeHealth) -> SourceStatus:
    statuses = {user.status, system.status}
    if SourceStatus.STALE in statuses:
        return SourceStatus.STALE
    if SourceStatus.OK in statuses and statuses.issubset(
        {SourceStatus.OK, SourceStatus.NOT_APPLICABLE}
    ):
        return SourceStatus.OK
    if statuses == {SourceStatus.NOT_APPLICABLE}:
        return SourceStatus.NOT_APPLICABLE
    return next(
        status
        for status in (user.status, system.status)
        if status is not SourceStatus.NOT_APPLICABLE
    )


def _flatpak_provenance(user: ScopeHealth, system: ScopeHealth) -> Provenance:
    return (
        Provenance.LAST_GOOD
        if SourceStatus.STALE in {user.status, system.status}
        else Provenance.LIVE
    )


def _flatpak_cause(user: ScopeHealth, system: ScopeHealth) -> ErrorInfo | None:
    return next(
        (health.cause for health in (user, system) if health.cause is not None), None
    )


def _fingerprinted(item: NormalizedItem) -> NormalizedItem:
    return replace(
        item,
        installed_fingerprint=_fingerprint(item, item.installed),
        candidate_fingerprint=_fingerprint(item, item.candidate),
    )


def _fingerprint(item: NormalizedItem, value: str | None) -> str:
    evidence = "<none>" if value is None else value
    return hashlib.sha256(
        f"{item.source.value}\0{item.item_id}\0{evidence}".encode()
    ).hexdigest()


def _next_metadata(
    source: SourceName,
    current: tuple[SourceOutcome | None, ...],
    previous: SourceMetadata | None,
    now: datetime,
) -> SourceMetadata:
    old = SourceMetadata(source, None, None) if previous is None else previous
    attempted = tuple(outcome for outcome in current if outcome is not None)
    if not attempted:
        return old
    if all(successful(outcome) for outcome in attempted):
        return SourceMetadata(source, now, None)
    failure = next(outcome for outcome in attempted if not successful(outcome))
    count = old.failure_count + 1
    if failure.permanent:
        return SourceMetadata(source, old.last_success, None, count, True)
    delay = RETRY_DELAYS[min(count, len(RETRY_DELAYS)) - 1]
    return SourceMetadata(source, old.last_success, now + delay, count, False)
