import hashlib
from datetime import timedelta
from pathlib import Path

import pytest
from opatchy_helper.adapters.arch import ArchDegraded, ArchFailure, ArchUpdates
from opatchy_helper.adapters.flatpak import (
    FlatpakResult,
    FlatpakScope,
    FlatpakScopeResult,
    FlatpakScopeStatus,
)
from opatchy_helper.adapters.mise import (
    MiseCollected,
    MiseCommandFailed,
    MiseCommandRejected,
    MiseInvalid,
    MiseOutputExceeded,
    MiseResult,
    MiseTimedOut,
)
from opatchy_helper.adapters.omarchy import OmarchyAvailability
from opatchy_helper.adapters.security import SecurityArchUnavailable, SecurityCollected
from opatchy_helper.adapters.security_kev import KevDisabled, KevUnavailable
from opatchy_helper.models import (
    FindingId,
    ItemId,
    ItemSource,
    NormalizedItem,
    Provenance,
    ScanState,
    SecurityFinding,
    SecurityFindingGroup,
    Severity,
    SourceName,
    SourceStatus,
    WatchMode,
)
from opatchy_helper.protocol import decode_response, encode_response

from tests.python.scan_support import (
    NOW,
    FakeCollector,
    ScanClock,
    collector,
    run,
    store,
)


def test_scan_is_partial_when_an_applicable_flatpak_scope_times_out(
    tmp_path: Path,
) -> None:
    # Given: mandatory sources are healthy while the user Flatpak scope times out.
    base = collector()
    flatpak = FlatpakResult(
        (
            FlatpakScopeResult(
                FlatpakScope.USER, FlatpakScopeStatus.TIMEOUT, (), "timed out"
            ),
            FlatpakScopeResult(
                FlatpakScope.SYSTEM, FlatpakScopeStatus.NOT_APPLICABLE, (), None
            ),
        )
    )
    source = FakeCollector(base.omarchy, base.arch, base.security, flatpak=flatpak)

    # When: the coordinator commits the generation.
    generated = run(store(tmp_path), source, 1)

    # Then: parent Flatpak degradation and snapshot state agree.
    assert generated.snapshot.payload.scan_state is ScanState.PARTIAL


def test_scan_fails_when_no_mandatory_source_is_usable(tmp_path: Path) -> None:
    # Given: Omarchy, Arch, and security are unusable while mise is current.
    source = FakeCollector(
        OmarchyAvailability(SourceStatus.ERROR, (), "unavailable"),
        ArchDegraded(ArchFailure.COMMAND_TIMED_OUT, "timed out"),
        SecurityArchUnavailable("unavailable"),
        mise=MiseCollected(()),
    )

    # When: the coordinator assembles this generation.
    generated = run(store(tmp_path), source, 1)

    # Then: optional evidence cannot rescue mandatory source failure.
    assert generated.snapshot.payload.scan_state is ScanState.FAILED


def test_scan_is_complete_when_flatpak_is_not_installed(tmp_path: Path) -> None:
    # Given: all mandatory evidence is current and the Flatpak executable is absent.
    base = collector()
    flatpak = FlatpakResult(
        (
            FlatpakScopeResult(
                FlatpakScope.USER,
                FlatpakScopeStatus.MISSING_DEPENDENCY,
                (),
                "missing",
            ),
            FlatpakScopeResult(
                FlatpakScope.SYSTEM,
                FlatpakScopeStatus.MISSING_DEPENDENCY,
                (),
                "missing",
            ),
        )
    )
    source = FakeCollector(base.omarchy, base.arch, base.security, flatpak=flatpak)

    # When: the coordinator normalizes source availability.
    generated = run(store(tmp_path), source, 1)

    # Then: absent optional Flatpak is informational rather than degraded.
    flatpak_health = next(
        health
        for health in generated.snapshot.payload.sources
        if health.source is SourceName.FLATPAK
    )
    assert generated.snapshot.payload.scan_state is ScanState.COMPLETE
    assert flatpak_health.status is SourceStatus.NOT_APPLICABLE


@pytest.mark.parametrize(
    "mise",
    (
        MiseInvalid("invalid"),
        MiseTimedOut(),
        MiseOutputExceeded("stdout"),
        MiseCommandFailed(1),
        MiseCommandRejected("rejected"),
    ),
)
def test_scan_is_partial_when_an_applicable_mise_collection_fails(
    tmp_path: Path, mise: MiseResult
) -> None:
    # Given: all mandatory evidence is healthy and mise times out after applicability.
    base = collector()
    source = FakeCollector(base.omarchy, base.arch, base.security, mise=mise)

    # When: the coordinator normalizes the collected outcomes.
    generated = run(store(tmp_path), source, 1)

    # Then: optional applicable failure cannot be reported as complete.
    assert generated.snapshot.payload.scan_state is ScanState.PARTIAL


def test_scan_is_partial_when_cisa_enrichment_is_unavailable(tmp_path: Path) -> None:
    # Given: Arch security collection succeeds but KEV enrichment is unavailable.
    base = collector()
    finding = SecurityFinding(
        FindingId("AVG-20260001"),
        ItemId("arch:linux"),
        "AVG-20260001",
        (),
        Severity.HIGH,
        "2",
        False,
        Provenance.LIVE,
    )
    group = SecurityFindingGroup(finding.item_id, (finding,))
    security = SecurityCollected((group,), Provenance.LIVE, KevUnavailable("offline"))
    source = FakeCollector(base.omarchy, base.arch, security)

    # When: the coordinator records the current security generation.
    generated = run(store(tmp_path), source, 1)

    # Then: the enrichment outage degrades the snapshot without losing security data.
    cisa = next(
        health
        for health in generated.snapshot.payload.sources
        if health.source is SourceName.CISA_KEV
    )
    assert generated.snapshot.payload.scan_state is ScanState.PARTIAL
    assert cisa.status is SourceStatus.ERROR
    assert generated.snapshot.payload.findings == (group,)


def test_scan_reports_disabled_cisa_as_not_applicable_without_losing_arch_findings(
    tmp_path: Path,
) -> None:
    # Given: Arch security findings with explicitly disabled KEV enrichment.
    base = collector()
    finding = SecurityFinding(
        FindingId("AVG-20260001"),
        ItemId("arch:linux"),
        "AVG-20260001",
        (),
        Severity.HIGH,
        "2",
        False,
        Provenance.LIVE,
    )
    group = SecurityFindingGroup(finding.item_id, (finding,))
    source = FakeCollector(
        base.omarchy,
        base.arch,
        SecurityCollected((group,), Provenance.LIVE, KevDisabled()),
    )

    # When: the coordinator normalizes the scan generation.
    generated = run(store(tmp_path), source, 1)

    # Then: disabled coverage is not an outage or a fresh empty KEV result.
    cisa = next(
        health
        for health in generated.snapshot.payload.sources
        if health.source is SourceName.CISA_KEV
    )
    assert generated.snapshot.payload.scan_state is ScanState.COMPLETE
    assert cisa.status is SourceStatus.NOT_APPLICABLE
    assert cisa.cause is None
    assert generated.snapshot.payload.findings == (group,)


def test_permanent_failure_is_due_again_at_six_hour_refresh_boundary(
    tmp_path: Path,
) -> None:
    # Given: a permanent Arch capability failure at a deterministic initial clock.
    clock = ScanClock(NOW)
    storage = store(tmp_path, clock)
    _ = run(
        storage,
        collector(ArchDegraded(ArchFailure.COMMAND_MISSING, "missing")),
        1,
        clock=clock,
    )

    # When: a healthy Arch result arrives immediately before and at the six-hour boundary.
    clock.now = NOW + timedelta(hours=5, minutes=59)
    before = run(storage, collector(), 2, clock=clock)
    clock.now = NOW + timedelta(hours=6)
    at_boundary = run(storage, collector(), 3, clock=clock)

    # Then: regular refresh resumes only at the boundary.
    before_arch = next(
        health
        for health in before.snapshot.payload.sources
        if health.source is SourceName.ARCH
    )
    boundary_arch = next(
        health
        for health in at_boundary.snapshot.payload.sources
        if health.source is SourceName.ARCH
    )
    assert before_arch.status is SourceStatus.MISSING_DEPENDENCY
    assert boundary_arch.status is SourceStatus.OK
    metadata = next(
        entry
        for entry in storage.load_state().state.sources
        if entry.source is SourceName.ARCH
    )
    assert metadata.backoff_until is None
    assert metadata.failure_count == 0
    assert not metadata.permanent_failure


def test_scan_persists_empty_inventory_responses_for_every_inventory_source(
    tmp_path: Path,
) -> None:
    # Given: only Arch currently has an update.
    storage = store(tmp_path)

    # When: a generation commits.
    generated = run(storage, collector(), 1)

    # Then: all supported inventories exist and valid empty sources remain observable.
    stored = storage.load_generation()
    assert generated.committed
    assert stored is not None
    inventories = {response.payload.source: response for response in stored.inventories}
    assert tuple(inventories) == (
        ItemSource.ARCH,
        ItemSource.AUR,
        ItemSource.FLATPAK,
        ItemSource.MISE,
    )
    assert inventories[ItemSource.AUR].payload.total == 0
    assert inventories[ItemSource.FLATPAK].payload.total == 0
    assert inventories[ItemSource.MISE].payload.total == 0
    assert storage.load_inventory(ItemSource.AUR) == inventories[ItemSource.AUR]


def test_non_applicable_optional_sources_remain_informational(tmp_path: Path) -> None:
    # Given: optional AUR, Flatpak, and mise sources are not applicable.
    generated = run(store(tmp_path), collector(), 1)

    # When: the coordinator assembles source health and snapshot state.
    health_by_source = {
        health.source: health.status for health in generated.snapshot.payload.sources
    }

    # Then: unavailable optional capabilities do not degrade an otherwise healthy scan.
    assert generated.snapshot.payload.scan_state is ScanState.COMPLETE
    assert health_by_source[SourceName.AUR] is SourceStatus.NOT_APPLICABLE
    assert health_by_source[SourceName.FLATPAK] is SourceStatus.NOT_APPLICABLE
    assert health_by_source[SourceName.MISE] is SourceStatus.NOT_APPLICABLE


def test_scan_leaves_absent_native_evidence_without_fingerprints(
    tmp_path: Path,
) -> None:
    # Given: an Arch record with neither installed nor candidate native evidence.
    absent = NormalizedItem(
        ItemId("arch:unknown"),
        ItemSource.ARCH,
        "unknown",
        None,
        None,
        WatchMode.OFF,
        True,
        Provenance.LIVE,
    )

    # When: the record is normalized into a generation.
    generated = run(store(tmp_path), collector(ArchUpdates((absent,))), 1)
    item = next(
        value
        for value in generated.snapshot.payload.items
        if value.item_id == absent.item_id
    )

    # Then: missing native evidence remains distinguishable from a fingerprint value.
    assert item.installed_fingerprint is None
    assert item.candidate_fingerprint is None
    assert decode_response(encode_response(generated.snapshot)) == generated.snapshot


def test_present_native_evidence_uses_a_deterministic_sha256_fingerprint(
    tmp_path: Path,
) -> None:
    # Given: a native item has opaque installed and candidate versions.
    generated = run(store(tmp_path), collector(), 1)
    native = next(
        item
        for item in generated.snapshot.payload.items
        if item.source is ItemSource.ARCH
    )

    # When: scan normalization fingerprints the native evidence.
    expected = hashlib.sha256(
        f"{native.source.value}\0{native.item_id}\0{native.installed}".encode()
    ).hexdigest()

    # Then: the persisted fingerprint is stable and source-qualified.
    assert native.installed_fingerprint == expected
    assert decode_response(encode_response(generated.snapshot)) == generated.snapshot


def test_missing_or_corrupt_generation_inventory_is_unavailable(tmp_path: Path) -> None:
    # Given: a generation initially provides valid empty inventories.
    missing = store(tmp_path / "missing")
    assert missing.load_inventory(ItemSource.AUR) is None
    storage = store(tmp_path)
    _ = run(storage, collector(), 1)
    assert storage.load_inventory(ItemSource.AUR) is not None

    # When: the generation cache becomes malformed.
    _ = storage.generation_path.write_bytes(b"{torn")

    # Then: corrupt data is discarded and remains distinguishable from valid empty data.
    assert storage.load_inventory(ItemSource.AUR) is None
    assert not storage.generation_path.exists()
