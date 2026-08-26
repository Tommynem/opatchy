from datetime import datetime, timezone
from pathlib import Path

import pytest
from opatchy_helper import cli_operations
from opatchy_helper.cli_requests import (
    CliUnavailableError,
    InventoryCommand,
    SetStarCommand,
)
from opatchy_helper.models import (
    ItemId,
    ItemSource,
    SourceName,
    WatchMode,
)
from opatchy_helper.stars import WatchTransitionError
from opatchy_helper.storage_types import PersistentState, SourceMetadata, WatchRecord

from tests.python.cli_support import item, storage, write_inventory


def test_inventory_reads_valid_cache_and_adds_missing_permanent_id(
    tmp_path: Path,
) -> None:
    # Given: a cached item plus a permanent watch missing from that inventory.
    store = storage(tmp_path)
    write_inventory(
        store, ItemSource.ARCH, item("arch:present", ItemSource.ARCH, "Present")
    )
    store.save_state(
        PersistentState(
            (
                WatchRecord(
                    ItemId("arch:missing"), WatchMode.PERMANENT, None, None, False
                ),
            ),
            (),
            (),
        )
    )

    # When: the cache-only inventory operation is called directly.
    result = cli_operations.inventory_response(
        store, InventoryCommand(ItemSource.ARCH, "", 100, 0)
    )

    # Then: cached and missing permanent identities are both deterministic output.
    assert tuple(entry.item_id for entry in result.payload.items) == (
        ItemId("arch:missing"),
        ItemId("arch:present"),
    )


def test_snapshot_uses_only_validated_cached_response_or_reports_unavailable(
    tmp_path: Path,
) -> None:
    # Given: a storage root first without, then with, a validated snapshot.
    store = storage(tmp_path)
    with pytest.raises(CliUnavailableError):
        _ = cli_operations.snapshot(store)
    store.save_state(
        PersistentState(
            (),
            (),
            tuple(
                SourceMetadata(source, datetime.now(timezone.utc), None)
                for source in SourceName
            ),
        )
    )
    snapshot = cli_operations.scan(store, False)

    # When: the snapshot operation reads the stored object.
    result = cli_operations.snapshot(store)

    # Then: it returns the precise validated cache object without a scan.
    assert result == snapshot


def test_set_star_uses_the_existing_three_state_transition(tmp_path: Path) -> None:
    # Given: a current cached watchable identity with installed evidence.
    store = storage(tmp_path)
    write_inventory(store, ItemSource.ARCH, item("arch:demo", ItemSource.ARCH, "Demo"))

    # When: each legal requested next mode is applied through durable state.
    temporary = cli_operations.set_star(
        store, SetStarCommand(ItemId("arch:demo"), WatchMode.TEMPORARY)
    )
    permanent = cli_operations.set_star(
        store, SetStarCommand(ItemId("arch:demo"), WatchMode.PERMANENT)
    )
    cleared = cli_operations.set_star(
        store, SetStarCommand(ItemId("arch:demo"), WatchMode.OFF)
    )

    # Then: the approved off-temporary-permanent-off cycle is the only mutation.
    assert (temporary.payload.mode, permanent.payload.mode, cleared.payload.mode) == (
        WatchMode.TEMPORARY,
        WatchMode.PERMANENT,
        WatchMode.OFF,
    )
    assert store.load_state().state.watches == ()


def test_set_star_rejects_a_requested_mode_outside_the_cycle(tmp_path: Path) -> None:
    # Given: an off cached watchable item.
    store = storage(tmp_path)
    write_inventory(store, ItemSource.ARCH, item("arch:demo", ItemSource.ARCH, "Demo"))

    # When: permanent is requested instead of the required first temporary mode.
    with pytest.raises(WatchTransitionError):
        _ = cli_operations.set_star(
            store, SetStarCommand(ItemId("arch:demo"), WatchMode.PERMANENT)
        )

    # Then: no arbitrary direct durable state is constructed.
    assert store.load_state().state == PersistentState.empty()


def test_scan_uses_runtime_coordinator_without_collecting_not_due_sources(
    tmp_path: Path,
) -> None:
    # Given: every source is fresh enough that runtime collection is not due.
    store = storage(tmp_path)
    now = datetime.now(timezone.utc)
    store.save_state(
        PersistentState(
            (), (), tuple(SourceMetadata(source, now, None) for source in SourceName)
        )
    )

    # When: the scan operation creates its next generation.
    result = cli_operations.scan(store, False)

    # Then: the coordinator returns a cached-generation snapshot without network work.
    assert result.generation_id.startswith("scan-")
