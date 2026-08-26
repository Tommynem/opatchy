"""Correlation of validated Arch advisories with fresh official package inventory."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Final

from ..models import (
    ArchStatus,
    FindingId,
    ItemId,
    KevStatus,
    Provenance,
    SecurityFinding,
    SecurityFindingGroup,
)
from .arch import (
    ArchDegraded,
    ArchFailure,
    CommandRunner,
    PackageRecord,
    VersionComparison,
    compare_versions,
)
from .security_arch import ArchAdvisory, ArchFeedInvalid
from .security_kev import KevCatalog, KevUnavailable

_CVE: Final = re.compile(r"CVE-[0-9]{4}-[0-9]{4,19}")


@dataclass(frozen=True, slots=True)
class ArchFindings:
    groups: tuple[SecurityFindingGroup, ...]


@dataclass(frozen=True, slots=True)
class ArchCorrelationFailure:
    failure: ArchFailure
    diagnostic: str


def correlate_arch(
    advisories: tuple[ArchAdvisory, ...] | ArchFeedInvalid,
    inventory: tuple[PackageRecord, ...],
    run: CommandRunner,
    provenance: Provenance,
) -> ArchFindings | ArchCorrelationFailure:
    """Build deterministic findings solely for packages in fresh pacman -Qn output."""
    match advisories:
        case ArchFeedInvalid(diagnostic=diagnostic):
            return ArchCorrelationFailure(ArchFailure.MALFORMED_ROW, diagnostic)
        case tuple():
            pass
    official = {record.name: record for record in inventory}
    grouped: dict[str, list[SecurityFinding]] = {}
    for advisory in advisories:
        match advisory.status:
            case ArchStatus.NOT_AFFECTED:
                continue
            case (
                ArchStatus.UNKNOWN
                | ArchStatus.VULNERABLE
                | ArchStatus.TESTING
                | ArchStatus.FIXED
            ):
                pass
        for package in advisory.packages:
            record = official.get(package)
            if record is None:
                continue
            finding = _finding(advisory, record, run, provenance)
            match finding:
                case SecurityFinding():
                    grouped.setdefault(package, []).append(finding)
                case ArchCorrelationFailure():
                    return finding
                case _Unaffected():
                    continue
    return ArchFindings(
        tuple(
            SecurityFindingGroup(ItemId(f"arch:{package}"), tuple(grouped[package]))
            for package in sorted(grouped)
        )
    )


def enrich_kev(
    groups: tuple[SecurityFindingGroup, ...], kev: KevCatalog | KevUnavailable
) -> tuple[SecurityFindingGroup, ...]:
    """Join only validated CVE identifiers while retaining Arch findings on KEV failure."""
    match kev:
        case KevCatalog(cve_ids=cve_ids):
            return tuple(
                SecurityFindingGroup(
                    group.item_id,
                    tuple(
                        _with_kev(
                            finding, any(cve in cve_ids for cve in finding.cve_ids)
                        )
                        for finding in group.findings
                    ),
                )
                for group in groups
            )
        case KevUnavailable():
            return groups


def _finding(
    advisory: ArchAdvisory,
    record: PackageRecord,
    run: CommandRunner,
    provenance: Provenance,
) -> SecurityFinding | ArchCorrelationFailure | _Unaffected:
    if advisory.fixed is not None:
        compared = compare_versions(run, record.installed, advisory.fixed)
        match compared:
            case VersionComparison(sign=-1):
                pass
            case VersionComparison():
                return _unaffected()
            case ArchDegraded(failure=failure, detail=detail):
                return ArchCorrelationFailure(failure, detail)
    return SecurityFinding(
        FindingId(f"{advisory.name}:{record.name}"),
        ItemId(f"arch:{record.name}"),
        advisory.name,
        _cve_ids(advisory.issues),
        advisory.severity,
        advisory.fixed,
        False,
        provenance,
        advisory.status,
        advisory.advisory_type,
        record.installed,
        KevStatus.UNAVAILABLE,
        None,
    )


@dataclass(frozen=True, slots=True)
class _Unaffected:
    pass


def _unaffected() -> _Unaffected:
    return _Unaffected()


def _cve_ids(issues: tuple[str, ...]) -> tuple[str, ...]:
    retained: list[str] = []
    for issue in issues:
        if _CVE.fullmatch(issue) is not None and issue not in retained:
            retained.append(issue)
    return tuple(retained)


def _with_kev(finding: SecurityFinding, listed: bool) -> SecurityFinding:
    return replace(
        finding,
        known_exploited=listed,
        kev_status=KevStatus.LISTED if listed else KevStatus.NOT_LISTED,
        kev_provenance=Provenance.LIVE,
    )
