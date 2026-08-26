from pathlib import Path

from opatchy_helper.adapters.arch import ArchDegraded, ArchFailure, ArchUpdates
from opatchy_helper.adapters.flatpak import (
    FlatpakResult,
    FlatpakScope,
    FlatpakScopeResult,
    FlatpakScopeStatus,
)
from opatchy_helper.models import ItemSource, SourceName, SourceScope, SourceStatus

from tests.python.scan_support import FakeCollector, collector, run, store


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
