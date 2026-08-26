from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import TypeAlias, assert_never, final, override

from .models import (
    ItemId,
    ItemSource,
    NormalizedItem,
    NotificationFingerprint,
    WatchMode,
)
from .storage import Storage
from .storage_types import LedgerEntry, PersistentState, WatchRecord


@dataclass(frozen=True, slots=True)
class CachedItem:
    item_id: ItemId
    source: ItemSource
    installed_fingerprint: str | None
    candidate_fingerprint: str | None
    watchable: bool


@dataclass(frozen=True, slots=True)
class CachedInventory:
    items: tuple[CachedItem, ...]


@dataclass(frozen=True, slots=True)
class StarClick:
    item_id: ItemId
    inventory: CachedInventory
    require_current_inventory: bool = False


@dataclass(frozen=True, slots=True)
class FreshSourceScan:
    source: ItemSource
    inventory: CachedInventory
    confirmed_removed_item_ids: frozenset[ItemId] = frozenset()


@dataclass(frozen=True, slots=True)
class StaleSourceScan:
    source: ItemSource


@dataclass(frozen=True, slots=True)
class FailedSourceScan:
    source: ItemSource


@dataclass(frozen=True, slots=True)
class InvalidSourceScan:
    source: ItemSource


WatchEvent: TypeAlias = (
    StarClick | FreshSourceScan | StaleSourceScan | FailedSourceScan | InvalidSourceScan
)


@final
class WatchTransitionError(Exception):
    reason: str

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)

    @override
    def __str__(self) -> str:
        return self.reason


def cached_item(item: NormalizedItem) -> CachedItem:
    return CachedItem(
        item.item_id,
        item.source,
        _fingerprint(item.source, item.item_id, item.installed),
        _fingerprint(item.source, item.item_id, item.candidate),
        item.watchable,
    )


def transition(state: PersistentState, event: WatchEvent) -> PersistentState:
    match event:
        case StarClick():
            return _star_click(state, event)
        case FreshSourceScan():
            return _fresh_scan(state, event)
        case StaleSourceScan() | FailedSourceScan() | InvalidSourceScan():
            return state
    assert_never(event)


def apply_durable_event(storage: Storage, event: WatchEvent) -> PersistentState:
    return storage.update_state(lambda state: transition(state, event)).state


def missing_permanent_item_ids(
    state: PersistentState, inventory: CachedInventory
) -> tuple[ItemId, ...]:
    present = frozenset(item.item_id for item in inventory.items)
    return tuple(
        watch.item_id
        for watch in sorted(state.watches, key=lambda record: str(record.item_id))
        if watch.mode is WatchMode.PERMANENT and watch.item_id not in present
    )


def watch_notification_reference(
    item_id: ItemId,
    candidate_fingerprint: str,
    installed_fingerprint: str | None = None,
) -> NotificationFingerprint:
    return NotificationFingerprint(
        f"watch-v1:{item_id}:{installed_fingerprint}:{candidate_fingerprint}"
        if installed_fingerprint is not None
        else f"watch-v1:{item_id}:{candidate_fingerprint}"
    )


def _star_click(state: PersistentState, event: StarClick) -> PersistentState:
    current = next(
        (watch for watch in state.watches if watch.item_id == event.item_id), None
    )
    match current:
        case None:
            item = next(
                (
                    candidate
                    for candidate in event.inventory.items
                    if candidate.item_id == event.item_id
                ),
                None,
            )
            if item is None or not item.watchable or item.installed_fingerprint is None:
                raise WatchTransitionError("item is not a cached watchable item")
            watch = WatchRecord(
                item.item_id,
                WatchMode.TEMPORARY,
                item.installed_fingerprint,
                item.candidate_fingerprint,
                item.candidate_fingerprint is not None,
            )
            return PersistentState((*state.watches, watch), state.ledger, state.sources)
        case watch:
            return _click_existing_watch(
                state, watch, event.inventory, event.require_current_inventory
            )


def _click_existing_watch(
    state: PersistentState,
    watch: WatchRecord,
    inventory: CachedInventory,
    require_current_inventory: bool,
) -> PersistentState:
    match str(watch.mode):
        case "temporary":
            if require_current_inventory and not any(
                item.item_id == watch.item_id and item.watchable
                for item in inventory.items
            ):
                raise WatchTransitionError("item is not a cached watchable item")
            permanent = WatchRecord(
                watch.item_id, WatchMode.PERMANENT, None, None, False
            )
            return PersistentState(
                tuple(
                    permanent if record == watch else record for record in state.watches
                ),
                state.ledger,
                state.sources,
            )
        case "permanent":
            return PersistentState(
                tuple(record for record in state.watches if record != watch),
                _without_active_references(state.ledger, watch.item_id),
                state.sources,
            )
        case "off":
            raise WatchTransitionError("off watches are not durable")
        case _:
            raise WatchTransitionError("watch mode is invalid")


def _fresh_scan(state: PersistentState, event: FreshSourceScan) -> PersistentState:
    items = {
        item.item_id: item
        for item in event.inventory.items
        if item.source is event.source
    }
    watches = tuple(
        updated
        for watch in state.watches
        if (updated := _observe_watch(watch, event, items)) is not None
    )
    return PersistentState(watches, state.ledger, state.sources)


def _observe_watch(
    watch: WatchRecord,
    event: FreshSourceScan,
    items: dict[ItemId, CachedItem],
) -> WatchRecord | None:
    match str(watch.mode):
        case "permanent":
            return watch
        case "temporary":
            if not str(watch.item_id).startswith(f"{event.source.value}:"):
                return watch
            item = items.get(watch.item_id)
            if item is None:
                return (
                    None if watch.item_id in event.confirmed_removed_item_ids else watch
                )
            if (
                item.installed_fingerprint is not None
                and item.installed_fingerprint != watch.installed_fingerprint
            ):
                return None
            if not watch.armed and item.candidate_fingerprint is not None:
                return replace(
                    watch, candidate_fingerprint=item.candidate_fingerprint, armed=True
                )
            return watch
        case "off":
            raise WatchTransitionError("off watches are not durable")
        case _:
            raise WatchTransitionError("watch mode is invalid")


def _fingerprint(
    source: ItemSource, item_id: ItemId, evidence: str | None
) -> str | None:
    if evidence is None:
        return None
    return hashlib.sha256(f"{source.value}\0{item_id}\0{evidence}".encode()).hexdigest()


def _without_active_references(
    ledger: tuple[LedgerEntry, ...], item_id: ItemId
) -> tuple[LedgerEntry, ...]:
    prefix = f"watch-v1:{item_id}:"
    return tuple(
        entry
        for entry in ledger
        if not (entry.is_active and str(entry.fingerprint).startswith(prefix))
    )
