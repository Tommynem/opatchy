from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from .models import (
    ErrorCode,
    ErrorInfo,
    ItemSource,
    NormalizedItem,
    Provenance,
    ScopeHealth,
    SecurityFindingGroup,
    SnapshotResponse,
    SourceHealth,
    SourceName,
    SourceScope,
    SourceStatus,
)
from .scan_outcomes import SourceOutcome, successful
from .storage_generation import GenerationBundle

FRESHNESS = timedelta(hours=6)


@dataclass(frozen=True, slots=True)
class ResolvedOutcome:
    outcome: SourceOutcome
    health: SourceHealth | ScopeHealth
    items: tuple[NormalizedItem, ...]
    findings: tuple[SecurityFindingGroup, ...]
    usable: bool


def resolve_all(
    outcomes: tuple[SourceOutcome | None, ...],
    previous: GenerationBundle | None,
    now: datetime,
) -> tuple[ResolvedOutcome, ...]:
    identities = (
        (SourceName.OMARCHY, None),
        (SourceName.ARCH, None),
        (SourceName.AUR, None),
        (SourceName.FLATPAK, SourceScope.USER),
        (SourceName.FLATPAK, SourceScope.SYSTEM),
        (SourceName.MISE, None),
        (SourceName.SECURITY, None),
        (SourceName.CISA_KEV, None),
    )
    return tuple(
        resolve(current, source, scope, previous, now)
        for current, (source, scope) in zip(outcomes, identities, strict=True)
    )


def resolve(
    current: SourceOutcome | None,
    source: SourceName,
    scope: SourceScope | None,
    previous: GenerationBundle | None,
    now: datetime,
) -> ResolvedOutcome:
    if current is None:
        return _cached(source, scope, previous, now)
    if successful(current):
        return ResolvedOutcome(
            current, _fresh_health(current, now), current.items, current.findings, True
        )
    if previous is not None and current.key in previous.last_good_keys:
        return ResolvedOutcome(
            current,
            _stale_health(
                current, _previous_health(previous.last_good, source, scope, now)
            ),
            _last_good_items(previous.last_good, source, scope),
            _last_good_findings(previous.last_good, source),
            True,
        )
    return ResolvedOutcome(current, _failed_health(current, now), (), (), False)


def _cached(
    source: SourceName,
    scope: SourceScope | None,
    previous: GenerationBundle | None,
    now: datetime,
) -> ResolvedOutcome:
    if previous is None:
        outcome = SourceOutcome(
            source,
            scope,
            SourceStatus.ERROR,
            Provenance.LIVE,
            (),
            (),
            ErrorInfo(ErrorCode.SOURCE_UNAVAILABLE, "source has no cached evidence"),
            False,
            source is SourceName.AUR,
        )
        return ResolvedOutcome(outcome, _failed_health(outcome, now), (), (), False)
    health = _previous_health(previous.snapshot, source, scope, now)
    outcome = SourceOutcome(
        source,
        scope,
        health.status,
        health.provenance,
        (),
        (),
        health.cause,
        False,
        health.status is not SourceStatus.NOT_APPLICABLE,
    )
    items = _last_good_items(previous.snapshot, source, scope)
    findings = _last_good_findings(previous.snapshot, source)
    return ResolvedOutcome(
        outcome, health, items, findings, outcome.key in previous.last_good_keys
    )


def _fresh_health(outcome: SourceOutcome, now: datetime) -> SourceHealth | ScopeHealth:
    if outcome.scope is None:
        return SourceHealth(
            outcome.source,
            outcome.status,
            outcome.provenance,
            now,
            now + FRESHNESS,
            None,
        )
    return ScopeHealth(
        outcome.scope, outcome.status, outcome.provenance, now, now + FRESHNESS, None
    )


def _failed_health(outcome: SourceOutcome, now: datetime) -> SourceHealth | ScopeHealth:
    if outcome.scope is None:
        return SourceHealth(
            outcome.source, outcome.status, Provenance.LIVE, now, now, outcome.cause
        )
    return ScopeHealth(
        outcome.scope, outcome.status, Provenance.LIVE, now, now, outcome.cause
    )


def _stale_health(
    outcome: SourceOutcome, previous: SourceHealth | ScopeHealth
) -> SourceHealth | ScopeHealth:
    if outcome.scope is None:
        return SourceHealth(
            outcome.source,
            SourceStatus.STALE,
            Provenance.LAST_GOOD,
            previous.observed_at,
            previous.fresh_until,
            outcome.cause,
        )
    return ScopeHealth(
        outcome.scope,
        SourceStatus.STALE,
        Provenance.LAST_GOOD,
        previous.observed_at,
        previous.fresh_until,
        outcome.cause,
    )


def _previous_health(
    snapshot: SnapshotResponse,
    source: SourceName,
    scope: SourceScope | None,
    now: datetime,
) -> SourceHealth | ScopeHealth:
    health = next(value for value in snapshot.payload.sources if value.source is source)
    if scope is None:
        return health
    return next(
        (value for value in health.scopes if value.scope is scope),
        ScopeHealth(
            scope,
            SourceStatus.ERROR,
            Provenance.LIVE,
            now,
            now,
            ErrorInfo(
                ErrorCode.SOURCE_UNAVAILABLE, "source scope has no cached evidence"
            ),
        ),
    )


def _last_good_items(
    snapshot: SnapshotResponse, source: SourceName, scope: SourceScope | None
) -> tuple[NormalizedItem, ...]:
    return tuple(
        replace(item, provenance=Provenance.LAST_GOOD)
        for item in snapshot.payload.items
        if _belongs_to(item, source, scope)
    )


def _last_good_findings(
    snapshot: SnapshotResponse, source: SourceName
) -> tuple[SecurityFindingGroup, ...]:
    return snapshot.payload.findings if source is SourceName.SECURITY else ()


def _belongs_to(
    item: NormalizedItem, source: SourceName, scope: SourceScope | None
) -> bool:
    match source:
        case SourceName.OMARCHY:
            return item.source is ItemSource.OMARCHY
        case SourceName.ARCH:
            return item.source is ItemSource.ARCH
        case SourceName.AUR:
            return item.source is ItemSource.AUR
        case SourceName.FLATPAK:
            return item.source is ItemSource.FLATPAK and item.item_id.startswith(
                f"flatpak:{scope}:"
            )
        case SourceName.MISE:
            return item.source is ItemSource.MISE
        case SourceName.SECURITY | SourceName.CISA_KEV:
            return False
