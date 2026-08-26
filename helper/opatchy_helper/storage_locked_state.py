import fcntl
import hashlib
import os
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from .models import ProtocolError
from .storage_generation import GenerationBundle
from .storage_io import (
    PRIVATE_FILE_MODE,
    AtomicOperations,
    atomic_write,
    ensure_directory,
    fsync_directory,
)
from .storage_state import decode_state, encode_state, prune_ledger
from .storage_types import (
    PersistentState,
    StateCorruptError,
    StateLoad,
    StorageWarning,
)


@dataclass(frozen=True, slots=True)
class StateAccess:
    state_path: Path
    clock: Callable[[], datetime]
    operations: AtomicOperations
    load_generation: Callable[[], GenerationBundle | None]
    write_generation: Callable[[GenerationBundle], None]


@contextmanager
def state_lock(state_path: Path) -> Generator[None]:
    ensure_directory(state_path.parent)
    lock_path = state_path.parent / "state.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    os.chmod(lock_path, 0o600)
    with os.fdopen(descriptor, "r+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def load_state(access: StateAccess, *, persist_pruning: bool = True) -> StateLoad:
    generation = access.load_generation()
    if generation is not None:
        decoded = generation.state
        pruned = prune_ledger(decoded, access.clock())
        if persist_pruning and pruned != decoded:
            write_state(access, pruned)
        return StateLoad(pruned, None)
    if not access.state_path.exists():
        return StateLoad(PersistentState.empty(), None)
    raw = access.state_path.read_bytes()
    try:
        decoded = decode_state(raw)
        pruned = prune_ledger(decoded, access.clock())
        if persist_pruning and pruned != decoded:
            write_state(access, pruned)
        return StateLoad(pruned, None)
    except ProtocolError, StateCorruptError:
        _quarantine(access, raw)
        return StateLoad(PersistentState.empty(), StorageWarning.STATE_CORRUPT)


def write_state(access: StateAccess, state: PersistentState) -> None:
    generation = access.load_generation()
    if generation is not None:
        access.write_generation(replace(generation, state=state))
    atomic_write(
        access.state_path, encode_state(state, access.clock()), access.operations
    )


def _quarantine(access: StateAccess, raw: bytes) -> None:
    digest = hashlib.sha256(raw).hexdigest()
    target = access.state_path.with_name(f"state.json.corrupt-{digest}")
    access.operations.replace(access.state_path, target)
    os.chmod(target, PRIVATE_FILE_MODE)
    fsync_directory(access.state_path.parent, access.operations)
