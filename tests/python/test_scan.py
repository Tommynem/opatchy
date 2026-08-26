from pathlib import Path

from opatchy_helper.adapters.arch import ArchDegraded, ArchFailure, ArchUpdates
from opatchy_helper.adapters.omarchy import OmarchyAvailability
from opatchy_helper.adapters.security import SecurityArchUnavailable
from opatchy_helper.models import (
    ItemId,
    ItemSource,
    Provenance,
    ScanState,
    SourceName,
    SourceStatus,
)

from tests.python.scan_support import collector, item, run, store


def test_scan_builds_complete_normalized_generation_and_filters_omarchy_identity(
    tmp_path: Path,
) -> None:
    # Given: all mandatory sources are current and System repeats the canonical omarchy ID.
    duplicate = item(ItemSource.ARCH, "omarchy")
    generated = run(
        store(tmp_path),
        collector(ArchUpdates((duplicate, item(ItemSource.ARCH, "linux")))),
        1,
    )

    # When: a generation is committed.
    snapshot = generated.snapshot

    # Then: summary derives from normalized output and only the Omarchy-owned row remains.
    assert snapshot.payload.scan_state is ScanState.COMPLETE
    assert [entry.item_id for entry in snapshot.payload.items] == [
        ItemId("arch:linux"),
        ItemId("omarchy:omarchy"),
    ]
    assert snapshot.payload.summary.total_updates == 2
    assert all(entry.installed_fingerprint for entry in snapshot.payload.items)
    assert all(entry.candidate_fingerprint for entry in snapshot.payload.items)


def test_scan_uses_valid_last_good_only_as_stale_evidence(tmp_path: Path) -> None:
    # Given: a prior healthy Arch source slice.
    storage = store(tmp_path)
    _ = run(storage, collector(), 1)

    # When: Arch fails on the next due scan.
    failed = run(
        storage,
        collector(ArchDegraded(ArchFailure.COMMAND_TIMED_OUT, "checkupdates")),
        2,
        force=True,
    )

    # Then: its old item remains explicitly stale instead of becoming fresh empty data.
    arch_health = next(
        value
        for value in failed.snapshot.payload.sources
        if value.source is SourceName.ARCH
    )
    assert arch_health.status is SourceStatus.STALE
    assert arch_health.provenance is Provenance.LAST_GOOD
    assert arch_health.cause is not None
    assert failed.snapshot.payload.scan_state is ScanState.PARTIAL
    assert (
        next(
            value
            for value in failed.snapshot.payload.items
            if value.source is ItemSource.ARCH
        ).provenance
        is Provenance.LAST_GOOD
    )


def test_scan_fails_when_no_mandatory_slice_is_usable(tmp_path: Path) -> None:
    # Given: no cached mandatory source and every mandatory adapter fails.
    failed = run(
        store(tmp_path),
        collector(
            ArchDegraded(ArchFailure.COMMAND_TIMED_OUT, "checkupdates"),
            OmarchyAvailability(SourceStatus.TIMEOUT, (), "timeout"),
            SecurityArchUnavailable("arch-audit unavailable"),
        ),
        1,
    )

    # When: the invalid generation is normalized.
    states = {entry.status for entry in failed.snapshot.payload.sources}

    # Then: it remains failed and cannot fabricate empty successful slices.
    assert failed.snapshot.payload.scan_state is ScanState.FAILED
    assert SourceStatus.OK not in {
        entry.status
        for entry in failed.snapshot.payload.sources
        if entry.source in {SourceName.ARCH, SourceName.OMARCHY, SourceName.SECURITY}
    }
    assert SourceStatus.TIMEOUT in states
