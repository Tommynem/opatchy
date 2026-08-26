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
    return snapshot


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
        InventoryPayload(command.source, len(paged), paged),
    )


def _inventory_items(
    cached: InventoryResponse,
    watches: tuple[WatchRecord, ...],
    source: ItemSource,
) -> tuple[NormalizedItem, ...]:
    modes = {watch.item_id: watch.mode for watch in watches}
    cached_items = tuple(
        replace(item, watch_mode=modes.get(item.item_id, WatchMode.OFF))
        for item in cached.payload.items
    )
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
    return cached_items + missing


def _matches(item: NormalizedItem, query: str) -> bool:
    return (
        not query
        or query in item.label.casefold()
        or query in str(item.item_id).casefold()
    )


def _item_key(item: NormalizedItem) -> tuple[str, str, str]:
    return (item.source.value, item.label.casefold(), str(item.item_id))


def set_star(storage: Storage, command: SetStarCommand) -> StarResultResponse:
    inventory = CachedInventory(
        tuple(
            cached_item(item)
            for source in _sources()
            if (cached := storage.load_inventory(source)) is not None
            for item in cached.payload.items
        )
    )
    event = StarClick(command.item_id, inventory)

    def mutate(state: PersistentState) -> PersistentState:
        current = next(
            (watch.mode for watch in state.watches if watch.item_id == command.item_id),
            None,
        )
        if command.mode is not _next_mode(current):
            raise WatchTransitionError("watch mode does not match the transition")
        return transition(state, event)

    updated = storage.update_state(mutate).state
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


def _next_mode(current: WatchMode | None) -> WatchMode:
    match current:
        case None:
            return WatchMode.TEMPORARY
        case WatchMode.TEMPORARY:
            return WatchMode.PERMANENT
        case WatchMode.PERMANENT:
            return WatchMode.OFF
        case WatchMode.OFF:
            raise WatchTransitionError("off watches are not durable")
    assert_never(current)
