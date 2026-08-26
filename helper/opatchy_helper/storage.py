import fcntl
import hashlib
import os
import tempfile
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Final, Protocol, TypeAlias, final

from .models import InventoryResponse, ItemSource, ProtocolError, SnapshotResponse
from .protocol import decode_response, encode_response
from .runner_types import EndpointCache
from .storage_feeds import (
    read_last_good_feed,
    semantic_feed_path,
    transport_endpoint_cache,
)
from .storage_state import decode_state, encode_state, prune_ledger, validate_state
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

PRIVATE_DIRECTORY_MODE: Final = 0o700
PRIVATE_FILE_MODE: Final = 0o600
StateMutation: TypeAlias = Callable[[PersistentState], PersistentState]


class AtomicOperations(Protocol):
    def write(self, handle: BinaryIO, data: bytes) -> int: ...

    def fsync(self, descriptor: int) -> None: ...

    def replace(self, source: Path, destination: Path) -> None: ...


@final
class SystemAtomicOperations:
    def write(self, handle: BinaryIO, data: bytes) -> int:
        return handle.write(data)

    def fsync(self, descriptor: int) -> None:
        os.fsync(descriptor)

    def replace(self, source: Path, destination: Path) -> None:
        os.replace(source, destination)


@final
class Storage:
    def __init__(
        self,
        state_path: Path,
        cache_path: Path,
        clock: Callable[[], datetime],
        operations: AtomicOperations,
    ) -> None:
        self._state_path = state_path
        self._cache_path = cache_path
        self._clock = clock
        self._operations = operations

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
            updated = mutation(loaded.state)
            self._write_state_locked(updated)
            return StateLoad(updated, loaded.warning)

    def write_feed_cache(self, feed: FeedName, body: bytes) -> None:
        with self._state_lock():
            self._atomic_write(semantic_feed_path(self._cache_path, feed), body)

    def write_last_good_feed(
        self, feed: FeedName, body: bytes, validator: Callable[[bytes], bool]
    ) -> bool:
        """Replace semantic feed data only after its complete schema validator accepts it."""
        if not validator(body):
            return False
        with self._state_lock():
            self._atomic_write(semantic_feed_path(self._cache_path, feed), body)
        return True

    def read_feed_cache(self, feed: FeedName) -> bytes | None:
        with self._state_lock():
            return read_last_good_feed(self._cache_path, feed, self._discard)

    def read_last_good_feed(self, feed: FeedName) -> bytes | None:
        """Read schema-validated last-good feed bytes without consulting transport cache."""
        return self.read_feed_cache(feed)

    def endpoint_cache(self, feed: FeedName) -> EndpointCache:
        """Return dedicated transport paths that cannot overwrite semantic feed data."""
        return transport_endpoint_cache(self._cache_path, feed)

    def save_snapshot(self, response: SnapshotResponse) -> None:
        with self._state_lock():
            self._atomic_write(
                self._cache_path / "snapshot.json", encode_response(response)
            )

    def load_snapshot(self) -> SnapshotResponse | None:
        with self._state_lock():
            return self._read_snapshot_locked()

    def save_inventory(self, response: InventoryResponse) -> None:
        with self._state_lock():
            self._atomic_write(
                self._inventory_path(response.payload.source), encode_response(response)
            )

    def load_inventory(self, source: ItemSource) -> InventoryResponse | None:
        with self._state_lock():
            path = self._inventory_path(source)
            if not path.exists():
                return None
            try:
                cached = decode_response(path.read_bytes())
            except ProtocolError:
                self._discard(path)
                return None
            match cached:
                case InventoryResponse(payload=payload):
                    if payload.source == source:
                        return cached
                case _:
                    pass
            self._discard(path)
            return None

    @contextmanager
    def _state_lock(self) -> Generator[None]:
        self._ensure_directory(self._state_path.parent)
        lock_path = self._state_path.parent / "state.lock"
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, PRIVATE_FILE_MODE)
        os.chmod(lock_path, PRIVATE_FILE_MODE)
        with os.fdopen(descriptor, "r+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _load_state_locked(self, *, persist_pruning: bool = True) -> StateLoad:
        if not self._state_path.exists():
            return StateLoad(PersistentState.empty(), None)
        raw = self._state_path.read_bytes()
        try:
            decoded = decode_state(raw)
            pruned = prune_ledger(decoded, self._clock())
            if persist_pruning and pruned != decoded:
                self._write_state_locked(pruned)
            return StateLoad(pruned, None)
        except ProtocolError, StateCorruptError:
            self._quarantine(raw)
            return StateLoad(PersistentState.empty(), StorageWarning.STATE_CORRUPT)

    def _write_state_locked(self, state: PersistentState) -> None:
        self._atomic_write(self._state_path, encode_state(state, self._clock()))

    def _read_snapshot_locked(self) -> SnapshotResponse | None:
        path = self._cache_path / "snapshot.json"
        if not path.exists():
            return None
        try:
            cached = decode_response(path.read_bytes())
        except ProtocolError:
            self._discard(path)
            return None
        match cached:
            case SnapshotResponse():
                return cached
            case _:
                self._discard(path)
                return None

    def _inventory_path(self, source: ItemSource) -> Path:
        return self._cache_path / f"inventory-{source.value}.json"

    def _quarantine(self, raw: bytes) -> None:
        digest = hashlib.sha256(raw).hexdigest()
        target = self._state_path.with_name(f"state.json.corrupt-{digest}")
        self._operations.replace(self._state_path, target)
        os.chmod(target, PRIVATE_FILE_MODE)
        self._fsync_directory(self._state_path.parent)

    def _discard(self, path: Path) -> None:
        path.unlink(missing_ok=True)
        self._fsync_directory(path.parent)

    def _atomic_write(self, path: Path, data: bytes) -> None:
        self._ensure_directory(path.parent)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary_path = Path(temporary_name)
        replaced = False
        try:
            os.fchmod(descriptor, PRIVATE_FILE_MODE)
            with os.fdopen(descriptor, "wb") as handle:
                written = self._operations.write(handle, data)
                if written != len(data):
                    raise OSError("atomic write was partial")
                handle.flush()
                self._operations.fsync(handle.fileno())
            self._operations.replace(temporary_path, path)
            replaced = True
            os.chmod(path, PRIVATE_FILE_MODE)
            self._fsync_directory(path.parent)
        except OSError:
            if not replaced:
                temporary_path.unlink(missing_ok=True)
            raise

    def _ensure_directory(self, path: Path) -> None:
        path.mkdir(mode=PRIVATE_DIRECTORY_MODE, parents=True, exist_ok=True)
        os.chmod(path, PRIVATE_DIRECTORY_MODE)

    def _fsync_directory(self, path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            self._operations.fsync(descriptor)
        finally:
            os.close(descriptor)


__all__ = (
    "AtomicOperations",
    "FeedName",
    "LedgerEntry",
    "PersistentState",
    "StateSchemaIncompatible",
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
