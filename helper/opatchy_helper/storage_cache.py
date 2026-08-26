from collections.abc import Callable
from pathlib import Path

from .models import InventoryResponse, ItemSource, ProtocolError, SnapshotResponse
from .protocol import decode_response


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
