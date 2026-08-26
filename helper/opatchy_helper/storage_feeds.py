from collections.abc import Callable
from pathlib import Path

from .json_value import decode_json
from .models import ProtocolError
from .runner_types import EndpointCache
from .storage_types import FeedName


def read_last_good_feed(
    cache_path: Path, feed: FeedName, discard: Callable[[Path], None]
) -> bytes | None:
    path = semantic_feed_path(cache_path, feed)
    if not path.exists():
        return None
    raw = path.read_bytes()
    try:
        _ = decode_json(raw.decode("utf-8"))
    except UnicodeDecodeError, ProtocolError:
        discard(path)
        return None
    return raw


def semantic_feed_path(cache_path: Path, feed: FeedName) -> Path:
    return cache_path / f"{feed.value}.json"


def transport_endpoint_cache(cache_path: Path, feed: FeedName) -> EndpointCache:
    prefix = cache_path / f"transport-{feed.value}"
    return EndpointCache(prefix.with_suffix(".body"), prefix.with_suffix(".metadata"))
