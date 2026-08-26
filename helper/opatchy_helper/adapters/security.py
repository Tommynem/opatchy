"""Current-only Arch advisory correlation with independent CISA KEV enrichment."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, assert_never

from ..models import Provenance, SecurityFindingGroup
from ..runner_types import (
    CommandName,
    CommandSucceeded,
    EndpointDownloaded,
    EndpointName,
    EndpointNotModified,
    EndpointResult,
)
from ..storage_types import FeedName
from .arch import (
    ArchDegraded,
    CommandRunner,
    OfficialInventory,
    collect_official_inventory,
)
from .security_arch import (
    ArchAdvisory,
    ArchFeedInvalid,
    parse_arch_audit,
    parse_tracker,
)
from .security_correlation import (
    ArchCorrelationFailure,
    ArchFindings,
    correlate_arch,
    enrich_kev,
)
from .security_kev import KevCatalog, KevFeedInvalid, KevUnavailable, parse_kev


class EndpointFetcher(Protocol):
    """Fetches a named closed-registry endpoint and owns its transport cache."""

    def __call__(self, name: EndpointName, /) -> EndpointResult: ...


class SemanticFeedStore(Protocol):
    """Stores only parser-validated feed bytes as semantic last-good data."""

    def write_last_good_feed(
        self, feed: FeedName, body: bytes, validator: Callable[[bytes], bool], /
    ) -> bool: ...

    def read_last_good_feed(
        self, feed: FeedName, validator: Callable[[bytes], bool], /
    ) -> bytes | None: ...


@dataclass(frozen=True, slots=True)
class SecurityCollected:
    groups: tuple[SecurityFindingGroup, ...]
    arch_provenance: Provenance
    kev: KevCatalog | KevUnavailable


@dataclass(frozen=True, slots=True)
class SecurityArchUnavailable:
    diagnostic: str


type SecurityResult = SecurityCollected | SecurityArchUnavailable


def collect_security(
    run: CommandRunner,
    fetch: EndpointFetcher,
    store: SemanticFeedStore | None = None,
) -> SecurityResult:
    """Collect current Arch findings; unavailable evidence never becomes empty success."""
    inventory_result = collect_official_inventory(run)
    match inventory_result:
        case ArchDegraded(detail=detail):
            return SecurityArchUnavailable(detail)
        case OfficialInventory(records=inventory):
            pass
    primary = _primary(run)
    match primary:
        case _CurrentArch(advisories=advisories, provenance=provenance):
            pass
        case ArchFeedInvalid():
            fallback = _fallback(fetch, store)
            match fallback:
                case _CurrentArch(advisories=advisories, provenance=provenance):
                    pass
                case ArchFeedInvalid(diagnostic=diagnostic):
                    return SecurityArchUnavailable(diagnostic)
    correlated = correlate_arch(advisories, inventory, run, provenance)
    match correlated:
        case ArchCorrelationFailure(diagnostic=diagnostic):
            return SecurityArchUnavailable(diagnostic)
        case ArchFindings(groups=groups):
            kev = _kev(fetch, store)
            return SecurityCollected(enrich_kev(groups, kev), provenance, kev)
    assert_never(correlated)


@dataclass(frozen=True, slots=True)
class _CurrentArch:
    advisories: tuple[ArchAdvisory, ...]
    provenance: Provenance


def _primary(run: CommandRunner) -> _CurrentArch | ArchFeedInvalid:
    result = run(CommandName.ARCH_AUDIT, ())
    match result:
        case CommandSucceeded(stdout=stdout):
            parsed = parse_arch_audit(stdout)
            match parsed:
                case ArchFeedInvalid():
                    return parsed
                case tuple():
                    return _CurrentArch(parsed, Provenance.LIVE)
        case _:
            return ArchFeedInvalid("arch-audit is unavailable")
    assert_never(result)


def _fallback(
    fetch: EndpointFetcher, store: SemanticFeedStore | None
) -> _CurrentArch | ArchFeedInvalid:
    result = fetch(EndpointName.ARCH_SECURITY)
    match result:
        case EndpointDownloaded(body=body):
            parsed = parse_tracker(body)
            match parsed:
                case ArchFeedInvalid():
                    return parsed
                case tuple():
                    if store is not None:
                        _ = store.write_last_good_feed(
                            FeedName.ARCH_SECURITY, body, _is_tracker
                        )
                    return _CurrentArch(parsed, Provenance.FALLBACK)
        case EndpointNotModified():
            if store is None:
                return ArchFeedInvalid("Arch Security Tracker has no semantic cache")
            cached = store.read_last_good_feed(FeedName.ARCH_SECURITY, _is_tracker)
            if cached is None:
                return ArchFeedInvalid("Arch Security Tracker has no semantic cache")
            parsed = parse_tracker(cached)
            match parsed:
                case ArchFeedInvalid():
                    return parsed
                case tuple():
                    return _CurrentArch(parsed, Provenance.CACHE)
        case _:
            return ArchFeedInvalid("Arch Security Tracker is unavailable")
    assert_never(result)


def _kev(
    fetch: EndpointFetcher, store: SemanticFeedStore | None
) -> KevCatalog | KevUnavailable:
    result = fetch(EndpointName.CISA_KEV)
    match result:
        case EndpointDownloaded(body=body):
            parsed = parse_kev(body)
            match parsed:
                case KevCatalog():
                    if store is not None:
                        _ = store.write_last_good_feed(FeedName.CISA_KEV, body, _is_kev)
                    return parsed
                case KevFeedInvalid():
                    return KevUnavailable("CISA KEV evidence is invalid")
        case EndpointNotModified():
            if store is None:
                return KevUnavailable("CISA KEV has no semantic cache")
            cached = store.read_last_good_feed(FeedName.CISA_KEV, _is_kev)
            if cached is None:
                return KevUnavailable("CISA KEV has no semantic cache")
            parsed = parse_kev(cached, Provenance.CACHE)
            match parsed:
                case KevCatalog():
                    return parsed
                case KevFeedInvalid():
                    return KevUnavailable("CISA KEV evidence is invalid")
        case _:
            return KevUnavailable("CISA KEV is unavailable")
    assert_never(result)


def _is_tracker(body: bytes) -> bool:
    match parse_tracker(body):
        case tuple():
            return True
        case ArchFeedInvalid():
            return False


def _is_kev(body: bytes) -> bool:
    match parse_kev(body):
        case KevCatalog():
            return True
        case KevFeedInvalid():
            return False
