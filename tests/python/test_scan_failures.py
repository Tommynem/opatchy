from dataclasses import replace
from pathlib import Path

from opatchy_helper.adapters.arch import ArchDegraded, ArchFailure, ArchUpdates
from opatchy_helper.adapters.flatpak import (
    FlatpakResult,
    FlatpakScope,
    FlatpakScopeResult,
    FlatpakScopeStatus,
)
from opatchy_helper.adapters.omarchy import OmarchyAvailability
from opatchy_helper.adapters.security import SecurityArchUnavailable, SecurityCollected
from opatchy_helper.adapters.security_kev import KevCatalog
from opatchy_helper.models import (
    ItemSource,
    Provenance,
    ScanState,
    SourceName,
    SourceScope,
    SourceStatus,
)
from opatchy_helper.scan_resolution import resolve

from tests.python.scan_support import NOW, FakeCollector, collector, run, store


def test_scan_reports_flatpak_scope_failure_without_hiding_healthy_scope(
    tmp_path: Path,
) -> None:
    # Given: user Flatpak collection times out while the system scope is inapplicable.
    base = collector()
    flatpak = FlatpakResult(
        (
            FlatpakScopeResult(
                FlatpakScope.USER, FlatpakScopeStatus.TIMEOUT, (), "user timed out"
            ),
            FlatpakScopeResult(
                FlatpakScope.SYSTEM, FlatpakScopeStatus.NOT_APPLICABLE, (), None
            ),
        )
    )
    source = FakeCollector(base.omarchy, base.arch, base.security, flatpak=flatpak)

    # When: the complete generation is normalized.
    generated = run(store(tmp_path), source, 1)

    # Then: the parent is degraded and both scoped statuses remain observable.
    health = next(
        value
        for value in generated.snapshot.payload.sources
        if value.source is SourceName.FLATPAK
    )
    assert health.status is SourceStatus.TIMEOUT
    assert {scope.scope: scope.status for scope in health.scopes} == {
        SourceScope.USER: SourceStatus.TIMEOUT,
        SourceScope.SYSTEM: SourceStatus.NOT_APPLICABLE,
    }


def test_scan_marks_an_empty_last_good_slice_stale_instead_of_current(
    tmp_path: Path,
) -> None:
    # Given: Arch validly reports no rows before a later transient failure.
    storage = store(tmp_path)
    _ = run(storage, collector(ArchUpdates(())), 1)

    # When: the same source fails after its empty result was stored as last-good.
    failed = run(
        storage,
        collector(ArchDegraded(ArchFailure.COMMAND_TIMED_OUT, "checkupdates")),
        2,
        force=True,
    )

    # Then: empty data is never relabeled as current evidence.
    health = next(
        value
        for value in failed.snapshot.payload.sources
        if value.source is SourceName.ARCH
    )
    assert health.status is SourceStatus.STALE
    assert all(
        value.source is not ItemSource.ARCH for value in failed.snapshot.payload.items
    )


def test_scan_keeps_empty_mandatory_last_good_slices_usable_during_backoff(
    tmp_path: Path,
) -> None:
    # Given: every mandatory source first returns validated, empty current evidence.
    storage = store(tmp_path)
    initial = run(
        storage,
        collector(
            ArchUpdates(()),
            OmarchyAvailability(SourceStatus.OK, (), None),
            SecurityCollected(
                (), Provenance.LIVE, KevCatalog(frozenset(), Provenance.LIVE)
            ),
        ),
        1,
    )
    failed_source = FakeCollector(
        OmarchyAvailability(SourceStatus.ERROR, (), "unavailable"),
        ArchDegraded(ArchFailure.COMMAND_TIMED_OUT, "checkupdates"),
        SecurityArchUnavailable("unavailable"),
    )

    # When: failures commit and the next scan skips them inside retry backoff.
    failed = run(storage, failed_source, 2, force=True)
    skipped = run(storage, collector(), 3)

    # Then: validated empty stale slices retain mandatory usability.
    assert tuple(
        result.snapshot.payload.scan_state for result in (initial, failed, skipped)
    ) == (ScanState.COMPLETE, ScanState.PARTIAL, ScanState.PARTIAL)
    health_by_source = {
        health.source: health for health in skipped.snapshot.payload.sources
    }
    for source in (SourceName.OMARCHY, SourceName.ARCH, SourceName.SECURITY):
        assert health_by_source[source].status is SourceStatus.STALE
        assert health_by_source[source].provenance is Provenance.LAST_GOOD


def test_cached_source_without_a_validated_last_good_key_is_unusable(
    tmp_path: Path,
) -> None:
    # Given: cached Arch health exists but its validated identity key is absent.
    storage = store(tmp_path)
    _ = run(storage, collector(ArchUpdates(())), 1)
    generation = storage.load_generation()
    assert generation is not None
    without_arch = replace(
        generation,
        last_good_keys=tuple(key for key in generation.last_good_keys if key != "arch"),
    )

    # When: cached Arch evidence is resolved without its validation proof.
    cached = resolve(None, SourceName.ARCH, None, without_arch, NOW)

    # Then: a health entry alone cannot make cache evidence usable.
    assert not cached.usable


def test_scan_skips_permanent_failure_until_force_requests_recovery(
    tmp_path: Path,
) -> None:
    # Given: Arch has a permanent missing-command failure.
    storage = store(tmp_path)
    _ = run(
        storage,
        collector(ArchDegraded(ArchFailure.COMMAND_MISSING, "checkupdates")),
        1,
        force=True,
    )

    # When: normal scheduling runs, followed by an explicit forced recovery attempt.
    skipped = run(storage, collector(), 2)
    recovered = run(storage, collector(), 3, force=True)

    # Then: normal scheduling preserves failure while force allows a healthy reset.
    skipped_health = next(
        value
        for value in skipped.snapshot.payload.sources
        if value.source is SourceName.ARCH
    )
    metadata = next(
        value
        for value in storage.load_state().state.sources
        if value.source is SourceName.ARCH
    )
    assert skipped_health.status is SourceStatus.MISSING_DEPENDENCY
    assert recovered.committed
    assert not metadata.permanent_failure


def test_scan_discards_invalid_generation_before_failed_source_can_use_it(
    tmp_path: Path,
) -> None:
    # Given: a complete generation whose cache is later corrupted.
    storage = store(tmp_path)
    _ = run(storage, collector(), 1)
    _ = storage.generation_path.write_bytes(b"{}")

    # When: a forced Arch failure runs after cache validation rejects that generation.
    failed = run(
        storage,
        collector(ArchDegraded(ArchFailure.COMMAND_TIMED_OUT, "checkupdates")),
        2,
        force=True,
    )

    # Then: it exposes the live failure rather than stale unvalidated cache data.
    health = next(
        value
        for value in failed.snapshot.payload.sources
        if value.source is SourceName.ARCH
    )
    assert health.status is SourceStatus.TIMEOUT
