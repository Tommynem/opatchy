from dataclasses import replace
from typing import assert_never
from uuid import uuid4

from .cli_requests import (
    CliCommand,
    CliUnavailableError,
    InventoryCommand,
    ScanCommand,
    SetStarCommand,
    SnapshotCommand,
)
from .models import (
    GenerationId,
    InventoryPayload,
    InventoryResponse,
    ItemSource,
    NormalizedItem,
    Provenance,
    Response,
    SnapshotResponse,
    StarResultPayload,
    StarResultResponse,
    WatchMode,
)
from .protocol import utc_now
from .scan import ScanCoordinator
from .scan_types import RuntimeScanCollector, ScanRequest
from .stars import (
    CachedInventory,
    StarClick,
    WatchTransitionError,
    cached_item,
    transition,
)
from .storage import Storage
from .storage_types import PersistentState, WatchRecord


def execute(command: CliCommand) -> Response:
    storage = Storage.from_environment(clock=utc_now)
    match command:
        case ScanCommand(force=force):
            return scan(storage, force)
        case SnapshotCommand():
            return snapshot(storage)
        case InventoryCommand() as inventory:
            return inventory_response(storage, inventory)
        case SetStarCommand() as star:
            return set_star(storage, star)
    assert_never(command)


def scan(storage: Storage, force: bool) -> SnapshotResponse:
    previous = storage.load_generation()
    order = 0 if previous is None else previous.order + 1
    request = ScanRequest(GenerationId(f"scan-{uuid4().hex}"), order, force)
    return (
        ScanCoordinator(storage, RuntimeScanCollector(storage), utc_now)
        .run(request)
        .snapshot
    )


def snapshot(storage: Storage) -> SnapshotResponse:
    snapshot = storage.load_snapshot()
    if snapshot is None:
        raise CliUnavailableError("validated snapshot storage is unavailable")
    state = storage.load_state().state
    return replace(
        snapshot,
        payload=replace(
            snapshot.payload,
            items=_watched_items(snapshot.payload.items, state.watches),
        ),
    )


def inventory_response(
    storage: Storage, command: InventoryCommand
) -> InventoryResponse:
    cached = storage.load_inventory(command.source)
    if cached is None:
        raise CliUnavailableError("validated inventory storage is unavailable")
    state = storage.load_state().state
    items = _inventory_items(cached, state.watches, command.source)
    query = command.query.casefold()
    filtered = tuple(item for item in items if _matches(item, query))
    ordered = tuple(sorted(filtered, key=_item_key))
    paged = ordered[command.offset : command.offset + command.limit]
    return InventoryResponse(
        cached.generated_at,
        cached.generation_id,
        InventoryPayload(command.source, len(ordered), paged),
    )


def _inventory_items(
    cached: InventoryResponse,
    watches: tuple[WatchRecord, ...],
    source: ItemSource,
) -> tuple[NormalizedItem, ...]:
    cached_items = _watched_items(cached.payload.items, watches)
    present = frozenset(item.item_id for item in cached_items)
    missing = tuple(
        NormalizedItem(
            watch.item_id,
            source,
            str(watch.item_id),
            None,
            None,
            WatchMode.PERMANENT,
            False,
            Provenance.CACHE,
        )
        for watch in watches
        if watch.mode is WatchMode.PERMANENT
        and watch.item_id not in present
        and str(watch.item_id).startswith(f"{source.value}:")
    )
    return missing + cached_items


def _watched_items(
    items: tuple[NormalizedItem, ...], watches: tuple[WatchRecord, ...]
) -> tuple[NormalizedItem, ...]:
    records = {watch.item_id: watch for watch in watches}
    return tuple(
        replace(
            item,
            watch_mode=record.mode,
            watch_armed=record.armed if record.mode is WatchMode.TEMPORARY else False,
        )
        if (record := records.get(item.item_id)) is not None
        else replace(item, watch_mode=WatchMode.OFF, watch_armed=False)
        for item in items
    )


def _matches(item: NormalizedItem, query: str) -> bool:
    return (
        not query
        or query in item.label.casefold()
        or query in str(item.item_id).casefold()
    )


def _item_key(item: NormalizedItem) -> tuple[str, str, str]:
    return (item.source.value, item.label.casefold(), str(item.item_id))


def set_star(storage: Storage, command: SetStarCommand) -> StarResultResponse:
    def mutate(
        state: PersistentState, inventories: tuple[InventoryResponse, ...]
    ) -> PersistentState:
        inventory = CachedInventory(
            tuple(
                cached_item(item)
                for cached in inventories
                for item in cached.payload.items
            )
        )
        current = next(
            (watch.mode for watch in state.watches if watch.item_id == command.item_id),
            None,
        )
        match current:
            case None:
                if command.mode is not WatchMode.TEMPORARY:
                    raise WatchTransitionError(
                        "watch mode does not match the transition"
                    )
                if not any(
                    item.item_id == command.item_id and item.watchable
                    for item in inventory.items
                ):
                    raise WatchTransitionError("item is not a current watchable item")
                return transition(state, StarClick(command.item_id, inventory))
            case WatchMode.TEMPORARY:
                if command.mode is not WatchMode.PERMANENT:
                    raise WatchTransitionError(
                        "watch mode does not match the transition"
                    )
                if not any(
                    item.item_id == command.item_id and item.watchable
                    for item in inventory.items
                ):
                    raise WatchTransitionError("item is not a current watchable item")
                return transition(state, StarClick(command.item_id, inventory))
            case WatchMode.PERMANENT:
                if command.mode is not WatchMode.OFF:
                    raise WatchTransitionError(
                        "watch mode does not match the transition"
                    )
                return transition(state, StarClick(command.item_id, inventory))
            case WatchMode.OFF:
                raise WatchTransitionError("off watches are not durable")
        assert_never(current)

    updated = storage.update_state_with_inventories(_sources(), mutate).state
    mode = next(
        (watch.mode for watch in updated.watches if watch.item_id == command.item_id),
        WatchMode.OFF,
    )
    return StarResultResponse(
        utc_now(),
        GenerationId(f"star-{uuid4().hex}"),
        StarResultPayload(command.item_id, mode),
    )


def _sources() -> tuple[ItemSource, ...]:
    return (ItemSource.ARCH, ItemSource.AUR, ItemSource.FLATPAK, ItemSource.MISE)
