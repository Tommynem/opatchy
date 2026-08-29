from dataclasses import replace
from typing import Final, assert_never
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
    SnapshotPayload,
    SnapshotResponse,
    SourceHealth,
    SourceScope,
    SourceStatus,
    StarResultPayload,
    StarResultResponse,
    WatchMode,
)
from .notification_types import NotificationSettings
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

_DEFAULT_NOTIFICATION_SETTINGS: Final = NotificationSettings()


def execute(command: CliCommand) -> Response:
    storage = Storage.from_environment(clock=utc_now)
    match command:
        case ScanCommand(force=force, notification_settings=notification_settings):
            return scan(storage, force, notification_settings)
        case SnapshotCommand():
            return snapshot(storage)
        case InventoryCommand() as inventory:
            return inventory_response(storage, inventory)
        case SetStarCommand() as star:
            return set_star(storage, star)
    assert_never(command)


def scan(
    storage: Storage,
    force: bool,
    notification_settings: NotificationSettings = _DEFAULT_NOTIFICATION_SETTINGS,
) -> SnapshotResponse:
    previous = storage.load_generation()
    order = 0 if previous is None else previous.order + 1
    request = ScanRequest(
        GenerationId(f"scan-{uuid4().hex}"), order, force, notification_settings
    )
    result = (
        ScanCoordinator(storage, RuntimeScanCollector(storage), utc_now)
        .run(request)
        .snapshot
    )
    return _overlay_snapshot(result, storage.load_state().state.watches)


def snapshot(storage: Storage) -> SnapshotResponse:
    snapshot = storage.load_snapshot()
    if snapshot is None:
        raise CliUnavailableError("validated snapshot storage is unavailable")
    state = storage.load_state().state
    return _overlay_snapshot(snapshot, state.watches)


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


def _overlay_snapshot(
    response: SnapshotResponse, watches: tuple[WatchRecord, ...]
) -> SnapshotResponse:
    items = _watched_items(response.payload.items, watches)
    summary = replace(
        response.payload.summary,
        watched_updates=sum(item.watch_mode is not WatchMode.OFF for item in items),
    )
    return replace(
        response, payload=replace(response.payload, items=items, summary=summary)
    )


def _matches(item: NormalizedItem, query: str) -> bool:
    return (
        not query
        or query in item.label.casefold()
        or query in str(item.item_id).casefold()
    )


def _item_key(item: NormalizedItem) -> tuple[str, str, str]:
    return (
        "0" if item.watch_mode is not WatchMode.OFF else "1",
        item.label.casefold(),
        str(item.item_id),
    )


def set_star(storage: Storage, command: SetStarCommand) -> StarResultResponse:
    def mutate(
        state: PersistentState,
        inventories: tuple[InventoryResponse, ...],
        snapshot: SnapshotResponse | None,
    ) -> PersistentState:
        inventory = CachedInventory(
            tuple(
                cached_item(item)
                for cached in inventories
                for item in cached.payload.items
            )
            + tuple(cached_item(item) for item in _current_snapshot_items(snapshot))
        )
        updated = transition(state, StarClick(command.item_id, inventory, True))
        if command.condition is not None:
            updated = PersistentState(
                tuple(
                    replace(watch, condition=command.condition)
                    if watch.item_id == command.item_id
                    and watch.mode is WatchMode.TEMPORARY
                    else watch
                    for watch in updated.watches
                ),
                updated.ledger,
                updated.sources,
            )
        watch = next(
            (watch for watch in updated.watches if watch.item_id == command.item_id),
            None,
        )
        mode = WatchMode.OFF if watch is None else watch.mode
        if mode is not command.mode:
            raise WatchTransitionError("watch mode does not match the transition")
        return updated

    updated = storage.update_state_with_inventories(_sources(), mutate).state
    watch = next(
        (watch for watch in updated.watches if watch.item_id == command.item_id), None
    )
    mode = WatchMode.OFF if watch is None else watch.mode
    return StarResultResponse(
        utc_now(),
        GenerationId(f"star-{uuid4().hex}"),
        StarResultPayload(command.item_id, mode, watch is not None and watch.armed),
    )


def _sources() -> tuple[ItemSource, ...]:
    return (ItemSource.ARCH, ItemSource.AUR, ItemSource.FLATPAK, ItemSource.MISE)


def _current_snapshot_items(
    snapshot: SnapshotResponse | None,
) -> tuple[NormalizedItem, ...]:
    match snapshot:
        case SnapshotResponse(payload=SnapshotPayload(sources=sources, items=items)):
            return tuple(
                item for item in items if _current_snapshot_item(item, sources)
            )
        case None:
            return ()


def _current_snapshot_item(
    item: NormalizedItem, sources: tuple[SourceHealth, ...]
) -> bool:
    health = next(
        (source for source in sources if source.source.value == item.source.value),
        None,
    )
    if (
        item.provenance is not Provenance.LIVE
        or health is None
        or health.status is not SourceStatus.OK
        or health.provenance is not Provenance.LIVE
    ):
        return False
    match item.source:
        case ItemSource.FLATPAK:
            return _current_flatpak_scope(item, health)
        case ItemSource.OMARCHY | ItemSource.ARCH | ItemSource.AUR | ItemSource.MISE:
            return True
    assert_never(item.source)


def _current_flatpak_scope(item: NormalizedItem, health: SourceHealth) -> bool:
    match str(item.item_id):
        case value if value.startswith("flatpak:user:"):
            scope = SourceScope.USER
        case value if value.startswith("flatpak:system:"):
            scope = SourceScope.SYSTEM
        case _:
            return False
    return any(
        entry.scope is scope
        and entry.status is SourceStatus.OK
        and entry.provenance is Provenance.LIVE
        for entry in health.scopes
    )
