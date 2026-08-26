from datetime import timedelta
from pathlib import Path

import pytest
from opatchy_helper.adapters.arch import ArchDegraded, ArchFailure, ArchUpdates
from opatchy_helper.models import ItemSource, ScanState, SourceName

from tests.python.scan_support import NOW, collector, item, run, store


@pytest.mark.parametrize(
    ("failure_count", "expected_delay"),
    (
        (1, timedelta(minutes=5)),
        (2, timedelta(minutes=15)),
        (3, timedelta(hours=1)),
        (4, timedelta(hours=6)),
        (5, timedelta(hours=6)),
    ),
)
def test_scan_persists_exact_transient_retry_schedule_and_resets_on_success(
    tmp_path: Path, failure_count: int, expected_delay: timedelta
) -> None:
    # Given: repeated transient Arch failures from a clean store.
    storage = store(tmp_path)
    failure = collector(ArchDegraded(ArchFailure.COMMAND_TIMED_OUT, "checkupdates"))

    # When: each due retry completes.
    for order in range(1, failure_count + 1):
        _ = run(storage, failure, order, force=True)
    source = next(
        entry
        for entry in storage.load_state().state.sources
        if entry.source is SourceName.ARCH
    )

    # Then: the capped delay is durable and a healthy retry clears it.
    assert source.backoff_until == NOW + expected_delay
    recovered = run(storage, collector(), failure_count + 1, force=True)
    after = next(
        entry
        for entry in storage.load_state().state.sources
        if entry.source is SourceName.ARCH
    )
    assert recovered.committed
    assert after.backoff_until is None
    assert after.failure_count == 0


def test_force_bypasses_backoff_once_and_candidate_changes_fingerprint(
    tmp_path: Path,
) -> None:
    # Given: a current Arch candidate is followed by a backoff-blocked failure.
    storage = store(tmp_path)
    initial = run(storage, collector(), 1)
    _ = run(
        storage,
        collector(ArchDegraded(ArchFailure.COMMAND_TIMED_OUT, "checkupdates")),
        2,
        force=True,
    )

    # When: normal scheduling skips it, then --force reruns it with a new candidate.
    skipped = run(storage, collector(), 3)
    forced = run(
        storage,
        collector(ArchUpdates((item(ItemSource.ARCH, "linux", "1", "3"),))),
        4,
        force=True,
    )

    # Then: force alone bypasses the retry window and the opaque candidate changes identity.
    initial_arch = next(
        value
        for value in initial.snapshot.payload.items
        if value.source is ItemSource.ARCH
    )
    forced_arch = next(
        value
        for value in forced.snapshot.payload.items
        if value.source is ItemSource.ARCH
    )
    assert skipped.snapshot.payload.scan_state is ScanState.PARTIAL
    assert forced_arch.candidate_fingerprint != initial_arch.candidate_fingerprint


def test_older_generation_rejection_leaves_every_persisted_byte_unchanged(
    tmp_path: Path,
) -> None:
    # Given: a newer generation has committed all atomic cache/state data.
    storage = store(tmp_path)
    newer = run(storage, collector(), 2)
    before = storage.generation_path.read_bytes()
    state_before = storage.state_path.read_bytes()

    # When: an earlier attempt completes after it.
    older = run(
        storage, collector(ArchUpdates((item(ItemSource.ARCH, "old"),))), 1, force=True
    )

    # Then: it is rejected without modifying snapshot, inventory, or source metadata bytes.
    assert newer.committed
    assert not older.committed
    assert storage.generation_path.read_bytes() == before
    assert storage.state_path.read_bytes() == state_before
