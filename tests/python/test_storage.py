import fcntl
import hashlib
import multiprocessing
import os
import stat
import sys
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from queue import Empty
from threading import Event, Lock, Thread
from typing import BinaryIO, Final, final, override

import pytest

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
HELPER_ROOT: Final = REPOSITORY_ROOT / "helper"
sys.path.insert(0, str(HELPER_ROOT))

from opatchy_helper.models import (
    GenerationId,
    InventoryPayload,
    InventoryResponse,
    ItemId,
    ItemSource,
    NormalizedItem,
    NotificationFingerprint,
    NotificationStatus,
    Provenance,
    SourceName,
    WatchMode,
)
from opatchy_helper.protocol import encode_response
from opatchy_helper.storage import (
    AtomicOperations,
    FeedName,
    LedgerEntry,
    PersistentState,
    StateSchemaIncompatible,
    Storage,
    StoragePathError,
    StorageWarning,
    SystemAtomicOperations,
    WatchRecord,
)
from opatchy_helper.storage_locked_state import state_lock
from opatchy_helper.storage_types import SourceMetadata, StateCorruptError

NOW: Final = datetime(2026, 8, 25, 12, tzinfo=timezone.utc)


@final
class RecordingOperations(AtomicOperations):
    def __init__(self, fail_at: str | None = None) -> None:
        self.events: list[str] = []
        self.fail_at: str | None = fail_at

    @override
    def write(self, handle: BinaryIO, data: bytes) -> int:
        self.events.append("write")
        self._raise_if_requested("write")
        return handle.write(data)

    @override
    def fsync(self, descriptor: int) -> None:
        self.events.append("fsync")
        self._raise_if_requested("fsync")

    @override
    def replace(self, source: Path, destination: Path) -> None:
        self.events.append("replace")
        self._raise_if_requested("replace")
        os.replace(source, destination)

    def _raise_if_requested(self, event: str) -> None:
        if self.fail_at == event:
            raise OSError(f"injected {event} failure")


@pytest.fixture
def xdg_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    state_root = tmp_path / "state-root"
    cache_root = tmp_path / "cache-root"
    monkeypatch.setenv("XDG_STATE_HOME", str(state_root))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_root))
    return state_root, cache_root


@pytest.fixture
def storage(xdg_roots: tuple[Path, Path]) -> Storage:
    _ = xdg_roots
    return Storage.from_environment(clock=lambda: NOW)


def watch(item_id: str = "arch:demo") -> WatchRecord:
    return WatchRecord(ItemId(item_id), WatchMode.PERMANENT, None, None, False)


def inventory() -> InventoryResponse:
    item = NormalizedItem(
        ItemId("arch:demo"),
        ItemSource.ARCH,
        "demo",
        "1.0",
        "1.1",
        WatchMode.OFF,
        True,
        Provenance.LIVE,
    )
    return InventoryResponse(
        NOW,
        GenerationId("generation-inventory"),
        InventoryPayload(ItemSource.ARCH, 1, (item,)),
    )


def duplicate_states() -> tuple[PersistentState, ...]:
    duplicate_ledger = (
        LedgerEntry(
            NotificationFingerprint("notice"), NotificationStatus.DELIVERED, NOW
        ),
        LedgerEntry(
            NotificationFingerprint("notice"), NotificationStatus.SUPPRESSED, NOW
        ),
    )
    duplicate_sources = (
        SourceMetadata(SourceName.ARCH, NOW, None),
        SourceMetadata(SourceName.ARCH, None, NOW),
    )
    return (
        PersistentState((watch(), watch()), (), ()),
        PersistentState((), duplicate_ledger, ()),
        PersistentState((), (), duplicate_sources),
    )


def unpruned_state_bytes() -> bytes:
    entries = ",".join(
        f'{{"fingerprint":"notice-{index}","recordedAt":"2026-08-24T12:00:00.000000Z","status":"delivered"}}'
        for index in range(5_001)
    )
    return (
        f'{{"ledger":[{entries}],"schemaVersion":1,"sources":[],"watches":[]}}'.encode()
    )


def test_default_xdg_paths_resolve_from_temporary_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(home))

    store = Storage.from_environment(clock=lambda: NOW)

    assert store.state_path == home / ".local" / "state" / "opatchy" / "state.json"
    assert store.cache_path == home / ".cache" / "opatchy"


def test_empty_xdg_paths_use_defaults_and_relative_paths_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_STATE_HOME", "")
    monkeypatch.setenv("XDG_CACHE_HOME", "")

    defaulted = Storage.from_environment(clock=lambda: NOW)

    assert defaulted.state_path == home / ".local" / "state" / "opatchy" / "state.json"
    assert defaulted.cache_path == home / ".cache" / "opatchy"
    monkeypatch.setenv("XDG_STATE_HOME", "relative-state")
    with pytest.raises(StoragePathError):
        _ = Storage.from_environment(clock=lambda: NOW)


def _permissive_umask(_: int) -> int:
    return 0


def test_paths_modes_and_defaults_are_private_under_permissive_umask(
    storage: Storage, xdg_roots: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root, cache_root = xdg_roots
    monkeypatch.setattr(os, "umask", _permissive_umask)

    storage.save_state(PersistentState.empty())
    assert storage.write_last_good_feed(FeedName.ARCH_SECURITY, b"feed", lambda _: True)

    assert storage.state_path == state_root / "opatchy" / "state.json"
    assert storage.cache_path == cache_root / "opatchy"
    assert stat.S_IMODE(storage.state_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(storage.cache_path.stat().st_mode) == 0o700
    assert stat.S_IMODE(storage.state_path.stat().st_mode) == 0o600
    assert (
        stat.S_IMODE((storage.cache_path / "arch-security.json").stat().st_mode)
        == 0o600
    )


def test_atomic_write_flushes_fsyncs_replaces_and_fsyncs_directory(
    xdg_roots: tuple[Path, Path],
) -> None:
    _ = xdg_roots
    operations = RecordingOperations()
    store = Storage.from_environment(clock=lambda: NOW, operations=operations)

    store.save_state(PersistentState.empty())

    assert operations.events == ["write", "fsync", "replace", "fsync"]
    assert not list(store.state_path.parent.glob(".state.json.*.tmp"))


@pytest.mark.parametrize("failure", ("write", "fsync", "replace"))
def test_atomic_state_failure_preserves_last_good_bytes(
    xdg_roots: tuple[Path, Path], failure: str
) -> None:
    _ = xdg_roots
    healthy = Storage.from_environment(clock=lambda: NOW)
    healthy.save_state(PersistentState.empty())
    before = healthy.state_path.read_bytes()
    failing = Storage.from_environment(
        clock=lambda: NOW, operations=RecordingOperations(failure)
    )

    with pytest.raises(OSError):
        failing.save_state(PersistentState((watch(),), (), ()))

    assert healthy.state_path.read_bytes() == before


@pytest.mark.parametrize("invalid_state", duplicate_states())
def test_duplicate_caller_state_is_rejected_before_empty_target_write(
    storage: Storage, invalid_state: PersistentState
) -> None:
    with pytest.raises(StateCorruptError):
        storage.save_state(invalid_state)

    assert not storage.state_path.exists()


@pytest.mark.parametrize("invalid_state", duplicate_states())
def test_duplicate_caller_save_preserves_last_good_state(
    storage: Storage, invalid_state: PersistentState
) -> None:
    storage.save_state(PersistentState.empty())
    before = storage.state_path.read_bytes()

    with pytest.raises(StateCorruptError):
        storage.save_state(invalid_state)

    assert storage.state_path.read_bytes() == before
    assert storage.load_state().warning is None


@pytest.mark.parametrize("invalid_state", duplicate_states())
def test_duplicate_update_cannot_replace_last_good_state(
    storage: Storage, invalid_state: PersistentState
) -> None:
    storage.save_state(PersistentState.empty())
    before = storage.state_path.read_bytes()

    with pytest.raises(StateCorruptError):
        _ = storage.update_state(lambda _: invalid_state)

    assert storage.state_path.read_bytes() == before
    assert storage.load_state().warning is None


@pytest.mark.parametrize("invalid_state", duplicate_states())
def test_duplicate_update_preserves_unpruned_last_good_bytes(
    storage: Storage, invalid_state: PersistentState
) -> None:
    before = unpruned_state_bytes()
    storage.state_path.parent.mkdir(parents=True)
    _ = storage.state_path.write_bytes(before)

    with pytest.raises(StateCorruptError):
        _ = storage.update_state(lambda _: invalid_state)

    assert storage.state_path.read_bytes() == before


@pytest.mark.parametrize("invalid_state", duplicate_states())
def test_duplicate_save_preserves_unpruned_last_good_bytes(
    storage: Storage, invalid_state: PersistentState
) -> None:
    before = unpruned_state_bytes()
    storage.state_path.parent.mkdir(parents=True)
    _ = storage.state_path.write_bytes(before)

    with pytest.raises(StateCorruptError):
        storage.save_state(invalid_state)

    assert storage.state_path.read_bytes() == before


def test_v0_state_migrates_deterministically_to_v2(storage: Storage) -> None:
    storage.state_path.parent.mkdir(parents=True)
    _ = storage.state_path.write_bytes(
        b'{"schemaVersion":0,"watches":[{"itemId":"arch:demo","mode":"permanent"}]}'
    )

    loaded = storage.load_state()

    assert loaded.warning is None
    assert loaded.state == PersistentState((watch(),), (), ())
    storage.save_state(loaded.state)
    assert b'"schemaVersion":2' in storage.state_path.read_bytes()


def test_v0_temporary_watch_migrates_conservatively_to_permanent(
    storage: Storage,
) -> None:
    storage.state_path.parent.mkdir(parents=True)
    _ = storage.state_path.write_bytes(
        b'{"schemaVersion":0,"watches":[{"itemId":"arch:demo","mode":"temporary"}]}'
    )

    loaded = storage.load_state()

    assert loaded.warning is None
    assert loaded.state.watches == (watch(),)


@pytest.mark.parametrize(
    "invalid_watch",
    (
        WatchRecord(ItemId("arch:demo"), WatchMode.OFF, None, None, False),
        WatchRecord(ItemId("arch:demo"), WatchMode.PERMANENT, "base", None, False),
        WatchRecord(ItemId("arch:demo"), WatchMode.TEMPORARY, None, None, False),
        WatchRecord(ItemId("arch:demo"), WatchMode.TEMPORARY, "base", None, True),
        WatchRecord(
            ItemId("arch:demo"), WatchMode.TEMPORARY, "base", "candidate", False
        ),
    ),
)
def test_impossible_watch_caller_state_preserves_last_good_bytes(
    storage: Storage, invalid_watch: WatchRecord
) -> None:
    storage.save_state(PersistentState.empty())
    before = storage.state_path.read_bytes()

    with pytest.raises(StateCorruptError):
        storage.save_state(PersistentState((invalid_watch,), (), ()))

    assert storage.state_path.read_bytes() == before


@pytest.mark.parametrize(
    "invalid_watch",
    (
        WatchRecord(ItemId("arch:demo"), WatchMode.OFF, None, None, False),
        WatchRecord(ItemId("arch:demo"), WatchMode.TEMPORARY, None, None, False),
    ),
)
def test_impossible_watch_update_preserves_last_good_bytes(
    storage: Storage, invalid_watch: WatchRecord
) -> None:
    storage.save_state(PersistentState.empty())
    before = storage.state_path.read_bytes()

    with pytest.raises(StateCorruptError):
        _ = storage.update_state(lambda _: PersistentState((invalid_watch,), (), ()))

    assert storage.state_path.read_bytes() == before


@pytest.mark.parametrize(
    "raw",
    (
        b'{"ledger":[],"schemaVersion":1,"sources":[],"watches":[{"armed":false,"candidateFingerprint":null,"installedFingerprint":null,"itemId":"arch:demo","mode":"off"}]}',
        b'{"ledger":[],"schemaVersion":1,"sources":[],"watches":[{"armed":true,"candidateFingerprint":null,"installedFingerprint":"base","itemId":"arch:demo","mode":"temporary"}]}',
    ),
)
def test_impossible_persisted_watch_combinations_are_quarantined(
    storage: Storage, raw: bytes
) -> None:
    storage.state_path.parent.mkdir(parents=True)
    _ = storage.state_path.write_bytes(raw)

    assert storage.load_state().warning is StorageWarning.STATE_CORRUPT
    assert not storage.state_path.exists()


def test_duplicate_v0_watches_are_quarantined(storage: Storage) -> None:
    storage.state_path.parent.mkdir(parents=True)
    _ = storage.state_path.write_bytes(
        b'{"schemaVersion":0,"watches":[{"itemId":"arch:demo","mode":"permanent"},{"itemId":"arch:demo","mode":"temporary"}]}'
    )

    assert storage.load_state().warning is StorageWarning.STATE_CORRUPT


def test_corrupt_state_is_quarantined_without_destroying_bytes(
    storage: Storage,
) -> None:
    corrupt = b"{torn"
    storage.state_path.parent.mkdir(parents=True)
    _ = storage.state_path.write_bytes(corrupt)

    loaded = storage.load_state()

    assert loaded.state == PersistentState.empty()
    assert loaded.warning is StorageWarning.STATE_CORRUPT
    quarantines = list(storage.state_path.parent.glob("state.json.corrupt-*"))
    assert len(quarantines) == 1
    assert quarantines[0].read_bytes() == corrupt
    assert not storage.state_path.exists()


def test_corrupt_cache_is_discarded(storage: Storage) -> None:
    cache_file = storage.cache_path / "arch-security.json"
    cache_file.parent.mkdir(parents=True)
    _ = cache_file.write_bytes(b"{torn")

    assert storage.read_last_good_feed(FeedName.ARCH_SECURITY, lambda _: False) is None
    assert not cache_file.exists()


def test_valid_feed_cache_reads_and_state_update_is_locked(storage: Storage) -> None:
    assert storage.read_last_good_feed(FeedName.CISA_KEV, lambda _: True) is None
    assert storage.write_last_good_feed(FeedName.ARCH_SECURITY, b"{}", lambda _: True)

    updated = storage.update_state(
        lambda state: replace(state, watches=(watch("arch:updated"),))
    )

    assert storage.read_last_good_feed(FeedName.ARCH_SECURITY, lambda _: True) == b"{}"
    assert updated.state.watches == (watch("arch:updated"),)


@pytest.mark.parametrize(
    "metadata",
    (
        None,
        b'"tag"\nTue, 01 Jan 2030 00:00:00 GMT\n',
        b'"tag"\nTue, 01 Jan 2030 00:00:00 GMT\nnot-a-digest\n',
        (
            f'"tag"\nTue, 01 Jan 2030 00:00:00 GMT\n{hashlib.sha256(b"other").hexdigest()}\n'.encode()
        ),
    ),
)
def test_confirmed_feed_requires_digest_bound_transport_metadata(
    storage: Storage, metadata: bytes | None
) -> None:
    # Given: matching semantic and transport bytes without trustworthy metadata.
    body = b"{}"
    assert storage.write_last_good_feed(FeedName.ARCH_SECURITY, body, lambda _: True)
    transport = storage.endpoint_cache(FeedName.ARCH_SECURITY)
    transport.body_path.parent.mkdir(parents=True, exist_ok=True)
    _ = transport.body_path.write_bytes(body)
    if metadata is not None:
        _ = transport.metadata_path.write_bytes(metadata)

    # When: 304 recovery reads current cache evidence.
    confirmed = storage.read_confirmed_feed(FeedName.ARCH_SECURITY, lambda _: True)

    # Then: unbound metadata prevents current-cache promotion.
    assert confirmed is None


def test_malformed_inventory_cache_is_discarded(storage: Storage) -> None:
    cache_file = storage.cache_path / "inventory-arch.json"
    cache_file.parent.mkdir(parents=True)
    _ = cache_file.write_bytes(b"{torn")

    assert storage.load_inventory(ItemSource.ARCH) is None
    assert not cache_file.exists()


def test_inventory_cache_round_trips_only_validated_protocol(storage: Storage) -> None:
    response = inventory()

    storage.save_inventory(response)

    assert storage.load_inventory(ItemSource.ARCH) == response


def test_missing_or_wrong_kind_protocol_caches_are_unavailable(
    storage: Storage,
) -> None:
    assert storage.load_snapshot() is None
    assert storage.load_inventory(ItemSource.ARCH) is None
    snapshot_file = storage.cache_path / "snapshot.json"
    snapshot_file.parent.mkdir(parents=True)
    _ = snapshot_file.write_bytes(encode_response(inventory()))

    assert storage.load_snapshot() is None
    assert not snapshot_file.exists()


def test_v1_state_decodes_watch_ledger_and_source_metadata(storage: Storage) -> None:
    storage.state_path.parent.mkdir(parents=True)
    _ = storage.state_path.write_bytes(
        b'{"ledger":[{"fingerprint":"notice","recordedAt":"2026-08-25T12:00:00.000000Z","status":"delivered"}],"schemaVersion":1,"sources":[{"backoffUntil":null,"lastSuccess":"2026-08-25T12:00:00.000000Z","source":"arch"}],"watches":[{"armed":true,"candidateFingerprint":"candidate","installedFingerprint":"installed","itemId":"arch:demo","mode":"temporary"}]}'
    )

    loaded = storage.load_state().state

    assert loaded.watches[0].armed
    assert loaded.ledger[0].recorded_at == NOW
    assert loaded.sources[0].last_success == NOW


def test_ledger_lease_round_trips_with_legacy_entries(storage: Storage) -> None:
    # Given: a legacy entry and an in-flight pending notification lease.
    legacy = LedgerEntry(
        NotificationFingerprint("legacy"), NotificationStatus.DELIVERED, NOW
    )
    claimed = LedgerEntry(
        NotificationFingerprint("claimed"),
        NotificationStatus.PENDING,
        NOW,
        "claim-token",
        NOW + timedelta(seconds=30),
    )

    # When: the state is persisted and reloaded.
    storage.save_state(PersistentState((), (legacy, claimed), ()))
    restored = storage.load_state().state.ledger

    # Then: leases survive while old entries remain valid without a lease.
    assert restored == (claimed, legacy)


@pytest.mark.parametrize(
    "raw",
    (
        b'{"schemaVersion":-1,"watches":[]}',
        b'{"schemaVersion":true,"watches":[]}',
        b'{"schemaVersion":1,"watches":[{"armed":false,"candidateFingerprint":null,"installedFingerprint":null,"itemId":"arch:duplicate","mode":"permanent"},{"armed":false,"candidateFingerprint":null,"installedFingerprint":null,"itemId":"arch:duplicate","mode":"permanent"}],"ledger":[],"sources":[]}',
        b'{"schemaVersion":1,"watches":[],"ledger":[{"fingerprint":"notice","recordedAt":"not-a-time","status":"delivered"}],"sources":[]}',
        b'{"schemaVersion":1,"watches":[],"ledger":[],"sources":[{"backoffUntil":null,"lastSuccess":null,"source":"unknown"}]}',
    ),
)
def test_invalid_current_state_is_quarantined(storage: Storage, raw: bytes) -> None:
    storage.state_path.parent.mkdir(parents=True)
    _ = storage.state_path.write_bytes(raw)

    loaded = storage.load_state()

    assert loaded.warning is StorageWarning.STATE_CORRUPT
    assert not storage.state_path.exists()


def test_future_state_is_preserved_and_never_overwritten(storage: Storage) -> None:
    future = b'{"schemaVersion":999,"watches":[]}'
    storage.state_path.parent.mkdir(parents=True)
    _ = storage.state_path.write_bytes(future)

    with pytest.raises(StateSchemaIncompatible) as raised:
        _ = storage.load_state()

    assert raised.value.schema_version == 999
    assert storage.state_path.read_bytes() == future
    with pytest.raises(StateSchemaIncompatible):
        storage.save_state(PersistentState.empty())
    assert storage.state_path.read_bytes() == future


def test_ledger_pruning_keeps_active_and_bounds_inactive_entries(
    storage: Storage,
) -> None:
    active = LedgerEntry(
        NotificationFingerprint("active"),
        NotificationStatus.PENDING,
        NOW - timedelta(days=999),
    )
    stale = LedgerEntry(
        NotificationFingerprint("stale"),
        NotificationStatus.DELIVERED,
        NOW - timedelta(days=181),
    )
    recent = tuple(
        LedgerEntry(
            NotificationFingerprint(f"recent-{index}"),
            NotificationStatus.DELIVERED,
            NOW - timedelta(days=1),
        )
        for index in range(5_001)
    )

    storage.save_state(PersistentState((), (active, stale, *recent), ()))
    ledger = storage.load_state().state.ledger

    assert active in ledger
    assert stale not in ledger
    assert (
        len(
            [
                entry
                for entry in ledger
                if entry.status is not NotificationStatus.PENDING
            ]
        )
        == 5_000
    )


def test_loaded_ledger_is_pruned_and_rewritten(storage: Storage) -> None:
    entries = ",".join(
        f'{{"fingerprint":"notice-{index}","recordedAt":"2026-08-24T12:00:00.000000Z","status":"delivered"}}'
        for index in range(5_001)
    )
    raw = (
        f'{{"ledger":[{entries}],"schemaVersion":1,"sources":[],"watches":[]}}'.encode()
    )
    storage.state_path.parent.mkdir(parents=True)
    _ = storage.state_path.write_bytes(raw)

    loaded = storage.load_state().state

    assert len(loaded.ledger) == 5_000
    assert storage.state_path.read_bytes() != raw


def _blocked_writer(
    state_home: str, cache_home: str, queue: multiprocessing.Queue[str]
) -> None:
    os.environ["XDG_STATE_HOME"] = state_home
    os.environ["XDG_CACHE_HOME"] = cache_home
    store = Storage.from_environment(clock=lambda: NOW)
    _ = store.update_state(lambda state: replace(state, watches=(watch("arch:child"),)))
    queue.put("written")


def test_concurrent_writers_serialize_with_flock(storage: Storage) -> None:
    state_home = str(storage.state_path.parents[1])
    cache_home = str(storage.cache_path.parents[1])
    queue: multiprocessing.Queue[str] = multiprocessing.Queue()

    _ = storage.load_state()
    with (storage.state_path.parent / "state.lock").open("r+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        process = multiprocessing.Process(
            target=_blocked_writer, args=(state_home, cache_home, queue)
        )
        process.start()
        process.join(0.2)
        assert process.is_alive()
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    process.join(5)

    assert process.exitcode == 0
    try:
        assert queue.get(timeout=1) == "written"
    except Empty as error:
        pytest.fail(str(error))
    assert storage.load_state().state.watches == (watch("arch:child"),)


def test_locked_mutations_reject_simultaneous_read_modify_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: the first mutation is held after lock acquisition and before its write.
    first_entered = Event()
    second_requested = Event()
    second_entered = Event()
    release_first = Event()
    requests = 0
    requests_lock = Lock()

    def hold_first_mutation() -> None:
        if first_entered.is_set():
            second_entered.set()
            return
        first_entered.set()
        assert release_first.wait(timeout=5)

    store = Storage(
        tmp_path / "state" / "opatchy" / "state.json",
        tmp_path / "cache" / "opatchy",
        lambda: NOW,
        SystemAtomicOperations(),
        before_mutation=hold_first_mutation,
    )

    @contextmanager
    def observed_state_lock(instance: Storage) -> Generator[None, None, None]:
        nonlocal requests
        with requests_lock:
            requests += 1
            if requests == 2:
                second_requested.set()
        with state_lock(instance.state_path):
            yield

    monkeypatch.setattr(Storage, "_state_lock", observed_state_lock)

    def add_watch(item_id: str) -> None:
        _ = store.update_state(
            lambda state: replace(state, watches=(*state.watches, watch(item_id)))
        )

    # When: a second read-modify-write reaches the lock while the first remains held.
    first = Thread(target=add_watch, args=("arch:first",))
    first.start()
    assert first_entered.wait(timeout=5)
    second = Thread(target=add_watch, args=("arch:second",))
    second.start()
    assert second_requested.wait(timeout=5)

    # Then: it cannot enter the mutation until release; a lockless path would enter.
    assert not second_entered.is_set()
    release_first.set()
    first.join(timeout=5)
    second.join(timeout=5)
    assert not first.is_alive()
    assert not second.is_alive()
    assert second_entered.is_set()
    assert {record.item_id for record in store.load_state().state.watches} == {
        ItemId("arch:first"),
        ItemId("arch:second"),
    }
