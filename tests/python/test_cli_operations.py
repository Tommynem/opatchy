from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import final

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
    Severity,
    SourceName,
    WatchMode,
)
from opatchy_helper.notification_types import NotificationSettings
from opatchy_helper.scan_types import ScanCollector, ScanRequest, ScanResult
from opatchy_helper.stars import WatchTransitionError
from opatchy_helper.storage import Storage, SystemAtomicOperations
from opatchy_helper.storage_types import PersistentState, SourceMetadata, WatchRecord

from tests.python.cli_support import NOW, item, storage, write_inventory
from tests.python.scan_support import FakeCollector, collector, run
from tests.python.scan_support import store as scan_store


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


def test_inventory_places_missing_permanent_watch_on_first_page(tmp_path: Path) -> None:
    # Given: more alphabetically earlier cached rows than the first page can hold.
    store = storage(tmp_path)
    write_inventory(
        store,
        ItemSource.ARCH,
        *(
            item(f"arch:a{index:03}", ItemSource.ARCH, f"a{index:03}")
            for index in range(101)
        ),
    )
    store.save_state(
        PersistentState(
            (
                WatchRecord(
                    ItemId("arch:zmissing"), WatchMode.PERMANENT, None, None, False
                ),
            ),
            (),
            (),
        )
    )

    # When: the bounded first empty-query page is requested.
    result = cli_operations.inventory_response(
        store, InventoryCommand(ItemSource.ARCH, "", 100, 0)
    )

    # Then: the durable missing watch precedes all unwatched rows before slicing.
    assert result.payload.total == 102
    assert result.payload.items[0].item_id == ItemId("arch:zmissing")


def test_set_star_clears_a_missing_permanent_watch(tmp_path: Path) -> None:
    # Given: a durable permanent watch absent from its cached inventory.
    store = storage(tmp_path)
    write_inventory(store, ItemSource.ARCH)
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

    # When: the ordinary permanent-to-off operation is requested.
    result = cli_operations.set_star(
        store, SetStarCommand(ItemId("arch:missing"), WatchMode.OFF)
    )

    # Then: both the result and subsequent browse state are authoritative off.
    assert result.payload.mode is WatchMode.OFF
    assert result.payload.watch_armed is False
    inventory = cli_operations.inventory_response(
        store, InventoryCommand(ItemSource.ARCH, "", 100, 0)
    )
    assert inventory.payload.items == ()


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


def test_fresh_scan_overlays_durable_armed_watch_and_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: collected item data defaults to off while durable state is armed.
    store = scan_store(tmp_path)
    store.save_state(
        PersistentState(
            (WatchRecord(ItemId("arch:linux"), WatchMode.TEMPORARY, "1", "2", True),),
            (),
            (),
        )
    )

    def runtime_collector(_: Storage) -> FakeCollector:
        return collector()

    monkeypatch.setattr(cli_operations, "RuntimeScanCollector", runtime_collector)

    # When: the CLI operation creates its fresh snapshot.
    result = cli_operations.scan(store, True)

    # Then: durable mode and armed truth replace collected metadata and its count.
    linux = next(
        item for item in result.payload.items if item.item_id == ItemId("arch:linux")
    )
    assert (linux.watch_mode, linux.watch_armed) == (WatchMode.TEMPORARY, True)
    assert result.payload.summary.watched_updates == 1


def test_restart_snapshot_overlays_durable_armed_watch_and_summary(
    tmp_path: Path,
) -> None:
    # Given: a persisted scan cache says off before durable state becomes armed.
    initial = scan_store(tmp_path)
    _ = run(initial, collector(), 1, force=True)
    initial.save_state(
        PersistentState(
            (WatchRecord(ItemId("arch:linux"), WatchMode.TEMPORARY, "1", "2", True),),
            (),
            (),
        )
    )
    restarted = Storage(
        tmp_path / "state" / "state.json",
        tmp_path / "cache",
        lambda: NOW,
        SystemAtomicOperations(),
    )

    # When: a new operation context loads the persisted snapshot.
    result = cli_operations.snapshot(restarted)

    # Then: durable mode and armed truth replace scanned metadata and its stale count.
    linux = next(
        item for item in result.payload.items if item.item_id == ItemId("arch:linux")
    )
    assert (linux.watch_mode, linux.watch_armed) == (WatchMode.TEMPORARY, True)
    assert result.payload.summary.watched_updates == 1


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


def test_set_star_rejects_inventory_removed_before_locked_mutation(
    tmp_path: Path,
) -> None:
    # Given: an item whose legacy cache disappears after the old pre-lock read.
    inventory_path = tmp_path / "cache" / "opatchy" / "inventory-arch.json"

    def remove_inventory() -> None:
        inventory_path.unlink(missing_ok=True)

    store = Storage(
        tmp_path / "state" / "opatchy" / "state.json",
        tmp_path / "cache" / "opatchy",
        lambda: NOW,
        SystemAtomicOperations(),
        before_mutation=remove_inventory,
    )
    write_inventory(store, ItemSource.ARCH, item("arch:demo", ItemSource.ARCH, "Demo"))

    # When: the first requested durable transition enters the state transaction.
    with pytest.raises(WatchTransitionError):
        _ = cli_operations.set_star(
            store, SetStarCommand(ItemId("arch:demo"), WatchMode.TEMPORARY)
        )

    # Then: no stale inventory evidence can create a temporary watch.
    assert store.load_state().state == PersistentState.empty()


def test_set_star_rejects_stale_temporary_promotion_from_legacy_inventory(
    tmp_path: Path,
) -> None:
    # Given: a temporary watch whose legacy cached inventory is later removed.
    store = storage(tmp_path)
    write_inventory(store, ItemSource.ARCH, item("arch:demo", ItemSource.ARCH, "Demo"))
    _ = cli_operations.set_star(
        store, SetStarCommand(ItemId("arch:demo"), WatchMode.TEMPORARY)
    )
    before = store.load_state().state
    before_bytes = store.state_path.read_bytes()
    (store.cache_path / "inventory-arch.json").unlink()

    # When: the temporary watch is promoted after its current evidence disappears.
    with pytest.raises(WatchTransitionError):
        _ = cli_operations.set_star(
            store, SetStarCommand(ItemId("arch:demo"), WatchMode.PERMANENT)
        )

    # Then: rejected stale promotion leaves durable state exactly unchanged.
    assert store.state_path.read_bytes() == before_bytes
    assert store.load_state().state == before


def test_set_star_reads_generation_inventory_inside_transaction(tmp_path: Path) -> None:
    # Given: a completed fresh generation with a watchable cached inventory item.
    store = storage(tmp_path)
    now = datetime.now(timezone.utc)
    store.save_state(
        PersistentState(
            (), (), tuple(SourceMetadata(source, now, None) for source in SourceName)
        )
    )
    _ = cli_operations.scan(store, False)
    write_inventory(store, ItemSource.ARCH, item("arch:demo", ItemSource.ARCH, "Demo"))

    # When: the first approved durable transition is requested.
    result = cli_operations.set_star(
        store, SetStarCommand(ItemId("arch:demo"), WatchMode.TEMPORARY)
    )

    # Then: generation-backed evidence creates the exact temporary watch.
    assert result.payload.mode is WatchMode.TEMPORARY


def test_set_star_rejects_stale_temporary_promotion_from_generation_inventory(
    tmp_path: Path,
) -> None:
    # Given: a temporary watch whose generation-backed inventory is later removed.
    store = storage(tmp_path)
    now = datetime.now(timezone.utc)
    store.save_state(
        PersistentState(
            (), (), tuple(SourceMetadata(source, now, None) for source in SourceName)
        )
    )
    _ = cli_operations.scan(store, False)
    write_inventory(store, ItemSource.ARCH, item("arch:demo", ItemSource.ARCH, "Demo"))
    _ = cli_operations.set_star(
        store, SetStarCommand(ItemId("arch:demo"), WatchMode.TEMPORARY)
    )
    before = store.load_state().state
    before_bytes = store.state_path.read_bytes()
    store.generation_path.unlink()

    # When: promotion is requested without current generation evidence.
    with pytest.raises(WatchTransitionError):
        _ = cli_operations.set_star(
            store, SetStarCommand(ItemId("arch:demo"), WatchMode.PERMANENT)
        )

    # Then: rejection preserves the exact durable temporary watch.
    assert store.state_path.read_bytes() == before_bytes
    assert store.load_state().state == before


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


def test_scan_operation_passes_explicit_notification_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: manifest-derived settings and a recording production-coordinator seam.
    store = scan_store(tmp_path)
    captured: list[NotificationSettings] = []

    @final
    class CapturingCoordinator:
        storage: Storage
        source: ScanCollector
        clock: Callable[[], datetime]

        def __init__(
            self,
            storage: Storage,
            source: ScanCollector,
            clock: Callable[[], datetime],
        ) -> None:
            self.storage = storage
            self.source = source
            self.clock = clock

        def run(self, request: ScanRequest) -> ScanResult:
            captured.append(request.notification_settings)
            return run(
                self.storage,
                self.source,
                request.generation_order,
                force=request.force,
            )

    expected = NotificationSettings(False, True, Severity.CRITICAL)
    monkeypatch.setattr(cli_operations, "ScanCoordinator", CapturingCoordinator)

    # When: the CLI operation receives parsed notification configuration.
    _ = cli_operations.scan(store, True, expected)

    # Then: that setting reaches the concrete scan request rather than defaults.
    assert captured == [expected]
