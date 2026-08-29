import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TypeAlias, final

from .cache_metadata import read_cache_validators
from .models import InventoryResponse, ItemSource, ProtocolError, SnapshotResponse
from .runner_types import EndpointCache
from .storage_cache import (
    CacheAccess,
    read_cached_inventory,
    read_cached_snapshot,
    read_current_inventories,
    save_cached_inventory,
    save_cached_snapshot,
)
from .storage_feeds import (
    read_last_good_feed,
    transport_endpoint_cache,
)
from .storage_generation import (
    GenerationBundle,
    decode_generation,
    encode_generation,
)
from .storage_io import (
    AtomicOperations,
    SystemAtomicOperations,
    atomic_write,
    fsync_directory,
)
from .storage_locked_state import StateAccess, load_state, state_lock, write_state
from .storage_semantic import write_last_good_feed
from .storage_state import encode_state, validate_state
from .storage_types import (
    FeedName,
    LedgerEntry,
    PersistentState,
    StateCorruptError,
    StateLoad,
    StateSchemaIncompatible,
    StoragePathError,
    StorageWarning,
    WatchRecord,
)

StateMutation: TypeAlias = Callable[[PersistentState], PersistentState]
StateInventoryMutation: TypeAlias = Callable[
    [PersistentState, tuple[InventoryResponse, ...], SnapshotResponse | None],
    PersistentState,
]


@final
class Storage:
    def __init__(
        self,
        state_path: Path,
        cache_path: Path,
        clock: Callable[[], datetime],
        operations: AtomicOperations,
        *,
        before_mutation: Callable[[], None] | None = None,
    ) -> None:
        self._state_path = state_path
        self._cache_path = cache_path
        self._clock = clock
        self._operations = operations
        self._before_mutation = before_mutation

    @classmethod
    def from_environment(
        cls,
        *,
        clock: Callable[[], datetime],
        operations: AtomicOperations | None = None,
    ) -> "Storage":
        state_home = _xdg_home("XDG_STATE_HOME", Path.home() / ".local" / "state")
        cache_home = _xdg_home("XDG_CACHE_HOME", Path.home() / ".cache")
        return cls(
            state_home / "opatchy" / "state.json",
            cache_home / "opatchy",
            clock,
            operations if operations is not None else SystemAtomicOperations(),
        )

    @property
    def state_path(self) -> Path:
        return self._state_path

    @property
    def cache_path(self) -> Path:
        return self._cache_path

    @property
    def generation_path(self) -> Path:
        return self._cache_path / "generation.json"

    def load_state(self) -> StateLoad:
        with self._state_lock():
            return self._load_state_locked()

    def save_state(self, state: PersistentState) -> None:
        validate_state(state)
        with self._state_lock():
            _ = self._load_state_locked(persist_pruning=False)
            self._write_state_locked(state)

    def update_state(self, mutation: StateMutation) -> StateLoad:
        with self._state_lock():
            loaded = self._load_state_locked(persist_pruning=False)
            if self._before_mutation is not None:
                self._before_mutation()
            updated = mutation(loaded.state)
            self._write_state_locked(updated)
            return StateLoad(updated, loaded.warning)

    def update_state_with_inventories(
        self, sources: tuple[ItemSource, ...], mutation: StateInventoryMutation
    ) -> StateLoad:
        with self._state_lock():
            loaded = self._load_state_locked(persist_pruning=False)
            if self._before_mutation is not None:
                self._before_mutation()
            updated = mutation(
                loaded.state,
                read_current_inventories(self._cache_access(), sources),
                read_cached_snapshot(self._cache_access()),
            )
            self._write_state_locked(updated)
            return StateLoad(updated, loaded.warning)

    def write_last_good_feed(
        self, feed: FeedName, body: bytes, validator: Callable[[bytes], bool]
    ) -> bool:
        """Replace semantic feed data only after its complete schema validator accepts it."""
        with self._state_lock():
            return write_last_good_feed(
                self._cache_path,
                feed,
                body,
                validator,
                lambda path, value: atomic_write(path, value, self._operations),
            )

    def read_last_good_feed(
        self, feed: FeedName, validator: Callable[[bytes], bool]
    ) -> bytes | None:
        """Read feed bytes only after their complete source validator accepts them."""
        with self._state_lock():
            return read_last_good_feed(self._cache_path, feed, validator, self._discard)

    def read_confirmed_feed(
        self, feed: FeedName, validator: Callable[[bytes], bool]
    ) -> bytes | None:
        """Read semantic data only when it equals the validated transport body."""
        with self._state_lock():
            semantic = read_last_good_feed(
                self._cache_path, feed, validator, self._discard
            )
            if semantic is None:
                return None
            cache = self.endpoint_cache(feed)
            try:
                transport = cache.body_path.read_bytes()
            except OSError:
                return None
            if (
                read_cache_validators(cache, transport) is None
                or transport != semantic
                or not validator(transport)
            ):
                return None
            return semantic

    def endpoint_cache(self, feed: FeedName) -> EndpointCache:
        """Return dedicated transport paths that cannot overwrite semantic feed data."""
        return transport_endpoint_cache(self._cache_path, feed)

    def save_snapshot(self, response: SnapshotResponse) -> None:
        with self._state_lock():
            save_cached_snapshot(self._cache_access(), response)

    def load_snapshot(self) -> SnapshotResponse | None:
        with self._state_lock():
            return read_cached_snapshot(self._cache_access())

    def save_inventory(self, response: InventoryResponse) -> None:
        with self._state_lock():
            save_cached_inventory(self._cache_access(), response)

    def load_inventory(self, source: ItemSource) -> InventoryResponse | None:
        with self._state_lock():
            return read_cached_inventory(self._cache_access(), source)

    def load_generation(self) -> GenerationBundle | None:
        with self._state_lock():
            return self._load_generation_locked()

    def commit_generation(self, generation: GenerationBundle) -> bool:
        """Publish a complete validated generation only when its order is newest."""
        with self._state_lock():
            current = self._load_generation_locked()
            if current is not None and generation.order <= current.order:
                return False
            self._write_generation_locked(generation)
            atomic_write(
                self._state_path,
                encode_state(generation.state, self._clock()),
                self._operations,
            )
            return True

    def _state_lock(self):
        return state_lock(self._state_path)

    def _load_state_locked(self, *, persist_pruning: bool = True) -> StateLoad:
        return load_state(self._state_access(), persist_pruning=persist_pruning)

    def _write_state_locked(self, state: PersistentState) -> None:
        write_state(self._state_access(), state)

    def _load_generation_locked(self) -> GenerationBundle | None:
        if not self.generation_path.exists():
            return None
        try:
            return decode_generation(self.generation_path.read_bytes())
        except ProtocolError, StateCorruptError:
            self._discard(self.generation_path)
            return None

    def _write_generation_locked(self, generation: GenerationBundle) -> None:
        atomic_write(
            self.generation_path,
            encode_generation(generation, self._clock()),
            self._operations,
        )

    def _cache_access(self) -> CacheAccess:
        return CacheAccess(
            self._cache_path,
            self._operations,
            self._load_generation_locked,
            self._write_generation_locked,
            self._discard,
        )

    def _state_access(self) -> StateAccess:
        return StateAccess(
            self._state_path,
            self._clock,
            self._operations,
            self._load_generation_locked,
            self._write_generation_locked,
        )

    def _discard(self, path: Path) -> None:
        path.unlink(missing_ok=True)
        fsync_directory(path.parent, self._operations)


__all__ = (
    "AtomicOperations",
    "FeedName",
    "LedgerEntry",
    "PersistentState",
    "StateSchemaIncompatible",
    "SystemAtomicOperations",
    "StoragePathError",
    "Storage",
    "StorageWarning",
    "WatchRecord",
)


def _xdg_home(variable: str, fallback: Path) -> Path:
    configured = os.environ.get(variable)
    path = fallback if not configured else Path(configured)
    if not path.is_absolute():
        raise StoragePathError(variable)
    return path
