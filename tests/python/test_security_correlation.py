from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Final

import pytest

HELPER_ROOT: Final = Path(__file__).resolve().parents[2] / "helper"
FIXTURE_ROOT: Final = Path(__file__).resolve().parents[1] / "fixtures" / "security"
sys.path.insert(0, str(HELPER_ROOT))

from opatchy_helper.adapters.arch import PackageRecord
from opatchy_helper.adapters.security_arch import (
    ArchFeedInvalid,
    parse_arch_audit,
    parse_tracker,
)
from opatchy_helper.adapters.security_correlation import (
    ArchCorrelationFailure,
    ArchFindings,
    correlate_arch,
)
from opatchy_helper.adapters.security_kev import KevFeedInvalid, parse_kev
from opatchy_helper.models import KevStatus, Provenance
from opatchy_helper.runner_types import CommandName, CommandResult, CommandSucceeded


def _fixture(name: str) -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()


def _vercmp(
    signs: tuple[str, ...],
) -> tuple[
    Callable[[CommandName, tuple[str, ...]], CommandResult], list[tuple[str, str]]
]:
    calls: list[tuple[str, str]] = []
    remaining = iter(signs)

    def run(name: CommandName, arguments: tuple[str, ...]) -> CommandResult:
        assert name is CommandName.VERCMP
        assert len(arguments) == 2
        calls.append(arguments)
        return CommandSucceeded(next(remaining).encode(), b"")

    return run, calls


def test_primary_and_tracker_have_equivalent_surviving_official_findings() -> None:
    # Given: source-equivalent feeds and an official inventory that excludes an AUR collision.
    primary = parse_arch_audit(_fixture("arch-audit.json"))
    fallback = parse_tracker(_fixture("tracker-all.json"))
    inventory = (
        PackageRecord("linux", "1:6.12.2-1"),
        PackageRecord("openssl", "3.0.0-1"),
    )
    primary_run, primary_calls = _vercmp(("-1",))
    fallback_run, fallback_calls = _vercmp(("-1",))

    # When: each feed is correlated only with the fresh official inventory.
    primary_result = correlate_arch(primary, inventory, primary_run, Provenance.LIVE)
    fallback_result = correlate_arch(
        fallback, inventory, fallback_run, Provenance.FALLBACK
    )

    # Then: fixed, no-fix, testing, CVE ordering, and exact official joins agree.
    assert isinstance(primary_result, ArchFindings)
    assert isinstance(fallback_result, ArchFindings)
    assert [
        (group.item_id, group.findings[0].advisory_id)
        for group in primary_result.groups
    ] == [
        ("arch:linux", "AVG-20260001"),
        ("arch:openssl", "AVG-20260002"),
    ]
    assert primary_result.groups[1].findings[0].fixed_version is None
    assert primary_result.groups[1].findings[0].cve_ids == ("CVE-2026-0002",)
    assert [
        (
            group.item_id,
            tuple((finding.advisory_id, finding.cve_ids) for finding in group.findings),
        )
        for group in fallback_result.groups
    ] == [
        (
            group.item_id,
            tuple((finding.advisory_id, finding.cve_ids) for finding in group.findings),
        )
        for group in primary_result.groups
    ]
    assert fallback_result.groups[0].findings[0].provenance is Provenance.FALLBACK
    assert primary_calls == [("1:6.12.2-1", "1:6.12.3-1")]
    assert fallback_calls == [("1:6.12.2-1", "1:6.12.3-1")]


def test_correlation_discards_equal_or_newer_fixed_versions_and_keeps_no_fix() -> None:
    # Given: an epoch/pkgrel fixed record, an equal record, and a no-fix record.
    advisories = parse_arch_audit(
        b'[{"name":"AVG-1","packages":["older"],"status":"Fixed","type":"security","severity":"High","fixed":"1:2.0-1","issues":["CVE-2026-0004"]},{"name":"AVG-2","packages":["equal"],"status":"Fixed","type":"security","severity":"Medium","fixed":"2.0-1","issues":[]},{"name":"AVG-3","packages":["newer"],"status":"Fixed","type":"security","severity":"Medium","fixed":"2.0-1","issues":[]},{"name":"AVG-4","packages":["nofix"],"status":"Unknown","type":"security","severity":"Unknown","fixed":null,"issues":[]}]'
    )
    run, calls = _vercmp(("-1", "0", "1"))

    # When: the advisory records are compared through native vercmp.
    result = correlate_arch(
        advisories,
        (
            PackageRecord("older", "2.0-1"),
            PackageRecord("equal", "2.0-1"),
            PackageRecord("newer", "3.0-1"),
            PackageRecord("nofix", "9.9-1"),
        ),
        run,
        Provenance.LIVE,
    )

    # Then: only the older fixed package and the no-fix package remain affected.
    assert isinstance(result, ArchFindings)
    assert [group.item_id for group in result.groups] == ["arch:nofix", "arch:older"]
    assert calls == [
        ("2.0-1", "1:2.0-1"),
        ("2.0-1", "2.0-1"),
        ("3.0-1", "2.0-1"),
    ]


def test_comparison_degradation_invalidates_current_arch_evidence() -> None:
    # Given: a fixed advisory and a native comparison that cannot establish a sign.
    advisories = parse_arch_audit(_fixture("arch-audit.json"))

    def run(name: CommandName, arguments: tuple[str, ...]) -> CommandResult:
        assert name is CommandName.VERCMP
        assert arguments == ("1", "1:6.12.3-1")
        return CommandSucceeded(b"not-a-sign", b"")

    # When: the required fixed-version comparison degrades.
    result = correlate_arch(
        advisories, (PackageRecord("linux", "1"),), run, Provenance.LIVE
    )

    # Then: no partial empty/clean result is created.
    assert isinstance(result, ArchCorrelationFailure)


@pytest.mark.parametrize(
    "payload",
    (
        b"{}",
        b'[{"name":"AVG-1","packages":[],"status":"Not affected","type":"security","severity":"Low","fixed":null,"issues":[]}]',
        b'[{"name":"AVG-1","packages":["pkg"],"status":"Vulnerable","type":"security","severity":"High","fixed":null,"issues":[true]}]',
        b'[{"name":"ASA-1","packages":["pkg"],"status":"Vulnerable","type":"security","severity":"High","fixed":null,"issues":[]}]',
        b'[{"name":"AVG-1","packages":["pkg","pkg"],"status":"Vulnerable","type":"security","severity":"High","fixed":null,"issues":[]}]',
        b'[{"name":"AVG-1","packages":["pkg"],"status":"Vulnerable","type":"security\\u0001","severity":"High","fixed":null,"issues":[]}]',
    ),
)
def test_primary_parser_rejects_incompatible_or_malformed_evidence(
    payload: bytes,
) -> None:
    # Given: a primary root or record that cannot truthfully represent arch-audit evidence.
    # When: the primary parser consumes it through decode_json.
    result = parse_arch_audit(payload)

    # Then: the adapter can use Tracker fallback rather than treating it as clean.
    assert isinstance(result, ArchFeedInvalid)


def test_tracker_discards_not_affected_and_kev_exact_joins_only_valid_cves() -> None:
    # Given: Tracker records plus a valid KEV catalog.
    tracker = parse_tracker(_fixture("tracker-all.json"))
    kev = parse_kev(_fixture("cisa-kev.json"))
    run, _ = _vercmp(("-1",))

    # When: surviving Arch findings are enriched with exact KEV CVE IDs.
    correlated = correlate_arch(
        tracker,
        (PackageRecord("linux", "1:6.12.2-1"), PackageRecord("openssl", "3.0-1")),
        run,
        Provenance.FALLBACK,
    )

    # Then: primary evidence has no not-affected group, and KEV parsing is exact.
    assert isinstance(correlated, ArchFindings)
    assert len(correlated.groups) == 2
    assert not isinstance(kev, KevFeedInvalid)
    assert kev.cve_ids == frozenset({"CVE-2026-0001"})
    assert correlated.groups[0].findings[0].kev_status is KevStatus.UNAVAILABLE


@pytest.mark.parametrize(
    "payload",
    (
        b'[{"name":"AVG-1","packages":["pkg"],"status":"Vulnerable","type":"security","severity":"High","fixed":null,"issues":["CVE-2026-0001","CVE-2026-0001"]}]',
        b'[{"name":"AVG-1","packages":["pkg"],"status":"Vulnerable","type":"security","severity":"High","fixed":null,"issues":[],"affected":"pkg","ticket":null,"advisories":["AVG-1","AVG-1"]}]',
    ),
)
def test_arch_parsers_reject_duplicate_normalized_array_values(payload: bytes) -> None:
    # Given: an advisory with repeated issue or Tracker advisory values.
    # When: its matching source parser validates the record.
    result = (
        parse_tracker(payload)
        if b'"advisories"' in payload
        else parse_arch_audit(payload)
    )

    # Then: no repeated value can create duplicate normalized findings.
    assert isinstance(result, ArchFeedInvalid)


@pytest.mark.parametrize(
    "date_value",
    (
        "not-a-date-time",
        "2026-01-02",
        "2026-99-99T00:00:00Z",
        "2026-01-02T00:00:00Z",
    ),
)
def test_kev_parser_requires_documented_dates_and_cwe_identifiers(
    date_value: str,
) -> None:
    # Given: otherwise complete KEV data with an invalid release time or CWE identifier.
    payload = (
        '{"catalogVersion":"1","dateReleased":"'
        + date_value
        + '","count":1,"vulnerabilities":[{"cveID":"CVE-2026-0001","vendorProject":"Vendor","product":"Product","vulnerabilityName":"Name","dateAdded":"2026-01-02","shortDescription":"Description","requiredAction":"Act","dueDate":"2026-02-02","cwes":["CWE-nope"]}]}'
    ).encode()

    # When: the catalog is parsed.
    result = parse_kev(payload)

    # Then: invalid documented formats are not retained.
    assert isinstance(result, KevFeedInvalid)
