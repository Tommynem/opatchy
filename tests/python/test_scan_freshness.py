from datetime import timedelta
from pathlib import Path

from opatchy_helper.adapters.arch import ArchDegraded, ArchFailure, ArchUpdates
from opatchy_helper.adapters.security import SecurityArchUnavailable
from opatchy_helper.models import (
    ItemSource,
    Provenance,
    ScanState,
    SourceName,
    SourceStatus,
)

from tests.python.scan_support import NOW, ScanClock, collector, item, run, store


def test_scan_reuses_fresh_source_until_expiry_then_marks_failed_slice_stale(
    tmp_path: Path,
) -> None:
    # Given: a fresh generation and a deterministic clock.
    clock = ScanClock(NOW)
    storage = store(tmp_path, clock)
    _ = run(storage, collector(), 1, clock=clock)
    failure = collector(ArchDegraded(ArchFailure.COMMAND_TIMED_OUT, "checkupdates"))

    # When: a normal scan runs before and then at the six-hour freshness deadline.
    clock.now = NOW + timedelta(hours=5, minutes=59)
    fresh = run(storage, failure, 2, clock=clock)
    clock.now = NOW + timedelta(hours=6)
    expired = run(storage, failure, 3, clock=clock)

    # Then: only the due scan executes its failure and preserves stale evidence.
    fresh_arch = next(
        health
        for health in fresh.snapshot.payload.sources
        if health.source is SourceName.ARCH
    )
    expired_arch = next(
        health
        for health in expired.snapshot.payload.sources
        if health.source is SourceName.ARCH
    )
    assert fresh_arch.status is SourceStatus.OK
    assert expired_arch.status is SourceStatus.STALE


def test_scan_preserves_each_failed_mandatory_slice_independently(
    tmp_path: Path,
) -> None:
    # Given: a complete generation with last-good Arch and security evidence.
    storage = store(tmp_path)
    _ = run(storage, collector(), 1)

    # When: both mandatory adapters fail together.
    failed = run(
        storage,
        collector(
            ArchDegraded(ArchFailure.COMMAND_TIMED_OUT, "checkupdates"),
            security=SecurityArchUnavailable("arch-audit unavailable"),
        ),
        2,
        force=True,
    )

    # Then: the generation is partial and each source retains only explicit stale evidence.
    statuses = {
        health.source: health.status
        for health in failed.snapshot.payload.sources
        if health.source in {SourceName.ARCH, SourceName.SECURITY}
    }
    assert failed.snapshot.payload.scan_state is ScanState.PARTIAL
    assert statuses == {
        SourceName.ARCH: SourceStatus.STALE,
        SourceName.SECURITY: SourceStatus.STALE,
    }


def test_scan_recovery_replaces_stale_slice_with_current_live_evidence(
    tmp_path: Path,
) -> None:
    # Given: a stale Arch slice after a transient failure.
    storage = store(tmp_path)
    _ = run(storage, collector(), 1)
    _ = run(
        storage,
        collector(ArchDegraded(ArchFailure.COMMAND_TIMED_OUT, "checkupdates")),
        2,
        force=True,
    )

    # When: a forced retry returns a changed Arch candidate.
    recovered = run(
        storage,
        collector(ArchUpdates((item(ItemSource.ARCH, "linux", "1", "3"),))),
        3,
        force=True,
    )

    # Then: recovery is current/live and clears durable retry state.
    arch_health = next(
        health
        for health in recovered.snapshot.payload.sources
        if health.source is SourceName.ARCH
    )
    metadata = next(
        entry
        for entry in storage.load_state().state.sources
        if entry.source is SourceName.ARCH
    )
    assert (arch_health.status, arch_health.provenance) == (
        SourceStatus.OK,
        Provenance.LIVE,
    )
    assert metadata.failure_count == 0
