from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from .models import InventoryResponse, ItemSource, ProtocolError, SnapshotResponse
from .protocol import decode_response, encode_response
from .storage_generation import GenerationBundle
from .storage_io import AtomicOperations, atomic_write


@dataclass(frozen=True, slots=True)
class CacheAccess:
    cache_path: Path
    operations: AtomicOperations
    load_generation: Callable[[], GenerationBundle | None]
    write_generation: Callable[[GenerationBundle], None]
    discard: Callable[[Path], None]


def save_cached_snapshot(access: CacheAccess, response: SnapshotResponse) -> None:
    generation = access.load_generation()
    if generation is not None:
        access.write_generation(replace(generation, snapshot=response))
        return
    atomic_write(
        access.cache_path / "snapshot.json",
        encode_response(response),
        access.operations,
    )


def read_cached_snapshot(access: CacheAccess) -> SnapshotResponse | None:
    generation = access.load_generation()
    if generation is not None:
        return generation.snapshot
    return load_snapshot(access.cache_path, access.discard)


def save_cached_inventory(access: CacheAccess, response: InventoryResponse) -> None:
    generation = access.load_generation()
    if generation is not None:
        inventories = tuple(
            item
            for item in generation.inventories
            if item.payload.source is not response.payload.source
        ) + (response,)
        access.write_generation(
            replace(
                generation,
                inventories=tuple(
                    sorted(inventories, key=lambda item: item.payload.source)
                ),
            )
        )
        return
    atomic_write(
        access.cache_path / f"inventory-{response.payload.source.value}.json",
        encode_response(response),
        access.operations,
    )


def read_cached_inventory(
    access: CacheAccess, source: ItemSource
) -> InventoryResponse | None:
    generation = access.load_generation()
    if generation is not None:
        return next(
            (item for item in generation.inventories if item.payload.source is source),
            None,
        )
    return load_inventory(access.cache_path, source, access.discard)


def read_current_inventories(
    access: CacheAccess, sources: tuple[ItemSource, ...]
) -> tuple[InventoryResponse, ...]:
    generation = access.load_generation()
    if generation is not None:
        allowed = frozenset(sources)
        return tuple(
            response
            for response in generation.inventories
            if response.payload.source in allowed
        )
    return tuple(
        response
        for source in sources
        if (response := load_inventory(access.cache_path, source, access.discard))
        is not None
    )


def load_snapshot(
    cache_path: Path, discard: Callable[[Path], None]
) -> SnapshotResponse | None:
    path = cache_path / "snapshot.json"
    if not path.exists():
        return None
    try:
        cached = decode_response(path.read_bytes())
    except ProtocolError:
        discard(path)
        return None
    match cached:
        case SnapshotResponse():
            return cached
        case _:
            discard(path)
            return None


def load_inventory(
    cache_path: Path, source: ItemSource, discard: Callable[[Path], None]
) -> InventoryResponse | None:
    path = cache_path / f"inventory-{source.value}.json"
    if not path.exists():
        return None
    try:
        cached = decode_response(path.read_bytes())
    except ProtocolError:
        discard(path)
        return None
    match cached:
        case InventoryResponse(payload=payload) if payload.source is source:
            return cached
        case _:
            discard(path)
            return None
