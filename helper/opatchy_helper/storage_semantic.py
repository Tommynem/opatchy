from collections.abc import Callable
from pathlib import Path

from .storage_feeds import semantic_feed_path
from .storage_types import FeedName


def write_last_good_feed(
    cache_path: Path,
    feed: FeedName,
    body: bytes,
    validator: Callable[[bytes], bool],
    write: Callable[[Path, bytes], None],
) -> bool:
    if not validator(body):
        return False
    write(semantic_feed_path(cache_path, feed), body)
    return True
