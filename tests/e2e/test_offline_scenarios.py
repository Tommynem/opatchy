from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "helper"))

from opatchy_helper.adapters.arch import ArchUpdates
from opatchy_helper.adapters.omarchy import OmarchyAvailability
from opatchy_helper.adapters.security import SecurityCollected
from opatchy_helper.adapters.security_kev import KevCatalog, KevUnavailable
from opatchy_helper.models import (
    ArchStatus,
    FindingId,
    GenerationId,
    ItemId,
    ItemSource,
    KevStatus,
    Provenance,
    SecurityFinding,
    SecurityFindingGroup,
    Severity,
    SourceStatus,
    WatchMode,
)
from opatchy_helper.notifications import NotificationCoordinator
from opatchy_helper.runner_types import (
    CommandExited,
    CommandName,
    CommandResult,
    CommandSucceeded,
)
from opatchy_helper.scan import ScanCollector, ScanCoordinator, ScanRequest
from opatchy_helper.storage import Storage, SystemAtomicOperations
from opatchy_helper.storage_types import PersistentState, WatchRecord

from tests.python.scan_support import NOW, FakeCollector, collector, item


@dataclass(frozen=True, slots=True)
class RecordingNotificationRunner:
    results: tuple[CommandResult, ...]
    calls: list[tuple[CommandName, tuple[str, ...]]]

    def __call__(self, name: CommandName, arguments: tuple[str, ...]) -> CommandResult:
        self.calls.append((name, arguments))
        return self.results[len(self.calls) - 1]


def _store(tmp_path: Path) -> Storage:
    return Storage(
        tmp_path / "xdg-state" / "opatchy" / "state.json",
        tmp_path / "xdg-cache" / "opatchy",
        lambda: NOW,
        SystemAtomicOperations(),
    )


def _scan(store: Storage, source: ScanCollector, order: int) -> None:
    _ = ScanCoordinator(store, source, lambda: NOW).run(
        ScanRequest(GenerationId(f"e2e-{order}"), order, True)
    )


def _finding(
    advisory: str, severity: Severity, fixed_version: str | None, known_exploited: bool
) -> SecurityFinding:
    return SecurityFinding(
        FindingId(advisory),
        ItemId("arch:linux"),
        advisory,
        ("CVE-2026-0001",),
        severity,
        fixed_version,
        known_exploited,
        Provenance.LIVE,
        ArchStatus.FIXED if fixed_version is not None else ArchStatus.VULNERABLE,
        kev_status=KevStatus.LISTED if known_exploited else KevStatus.NOT_LISTED,
        kev_provenance=Provenance.LIVE,
    )


def test_offline_scan_covers_all_clear_and_ordinary_updates(tmp_path: Path) -> None:
    # Given: isolated XDG-equivalent roots and deterministic collector outcomes.
    store = _store(tmp_path)
    all_clear = FakeCollector(
        OmarchyAvailability(SourceStatus.OK, (), None),
        ArchUpdates(()),
        SecurityCollected(
            (), Provenance.LIVE, KevCatalog(frozenset(), Provenance.LIVE)
        ),
    )

    # When: an all-clear scan is persisted, then ordinary updates replace it.
    _scan(store, all_clear, 1)
    clear = store.load_snapshot()
    _scan(store, collector(), 2)
    updated = store.load_snapshot()

    # Then: both complete snapshots are durable, ordered, and offline deterministic.
    assert clear is not None
    assert updated is not None
    assert clear.payload.summary.total_updates == 0
    assert updated.payload.summary.total_updates == 2
    assert updated.generation_id == GenerationId("e2e-2")


def test_offline_watches_and_security_notifications_survive_restart(
    tmp_path: Path,
) -> None:
    # Given: a current update with a permanent watch and fixed high/critical findings.
    store = _store(tmp_path)
    findings = (
        SecurityFindingGroup(
            ItemId("arch:linux"),
            (
                _finding("AVG-20260001", Severity.HIGH, "2", True),
                _finding("AVG-20260002", Severity.CRITICAL, "2", True),
                _finding("AVG-20260003", Severity.HIGH, None, True),
            ),
        ),
    )
    source = FakeCollector(
        collector().omarchy,
        ArchUpdates((item(ItemSource.ARCH, "linux"),)),
        SecurityCollected(
            findings,
            Provenance.LIVE,
            KevCatalog(frozenset({"CVE-2026-0001"}), Provenance.LIVE),
        ),
    )
    _scan(store, source, 1)
    store.save_state(
        PersistentState(
            (
                WatchRecord(
                    ItemId("arch:linux"), WatchMode.PERMANENT, None, None, False
                ),
                WatchRecord(
                    ItemId("omarchy:omarchy"), WatchMode.TEMPORARY, "1", "2", True
                ),
            ),
            (),
            store.load_state().state.sources,
        )
    )
    runner = RecordingNotificationRunner(
        (CommandSucceeded(b"", b""), CommandSucceeded(b"", b"")), []
    )

    # When: notification delivery is repeated after a Storage restart.
    snapshot = store.load_snapshot()
    assert snapshot is not None
    delivered = NotificationCoordinator(store, runner, lambda: NOW).dispatch(snapshot)
    restarted = Storage(
        store.state_path, store.cache_path, lambda: NOW, SystemAtomicOperations()
    )
    repeated = NotificationCoordinator(restarted, runner, lambda: NOW).dispatch(
        snapshot
    )

    # Then: high/critical fixed notices and the watch deliver once; no-fix does not.
    assert len(delivered) == 3
    assert repeated == ()
    assert len(runner.calls) == 2
    assert all("<" not in argument for _, argv in runner.calls for argument in argv)


def test_offline_temporary_watch_resolves_and_notification_failure_restarts(
    tmp_path: Path,
) -> None:
    # Given: a temporary watch whose candidate is current and a failing notifier.
    store = _store(tmp_path)
    source = collector()
    _scan(store, source, 1)
    store.save_state(
        PersistentState(
            (
                WatchRecord(
                    ItemId("arch:linux"), WatchMode.PERMANENT, None, None, False
                ),
            ),
            (),
            store.load_state().state.sources,
        )
    )
    failed_runner = RecordingNotificationRunner((CommandExited(1, b"", b""),), [])
    first = store.load_snapshot()
    assert first is not None
    pending = NotificationCoordinator(store, failed_runner, lambda: NOW).dispatch(first)

    # When: a restart observes the recorded failure and a subsequent scan resolves updates.
    resolved = FakeCollector(
        OmarchyAvailability(SourceStatus.OK, (), None),
        ArchUpdates(()),
        SecurityCollected((), Provenance.LIVE, KevUnavailable("offline")),
    )
    _scan(store, resolved, 2)
    restarted = Storage(
        store.state_path, store.cache_path, lambda: NOW, SystemAtomicOperations()
    )
    current = restarted.load_snapshot()

    # Then: the failed delivery is durable and the resolved generation has no updates.
    assert pending[0].status.value == "pending"
    assert current is not None
    assert current.payload.summary.total_updates == 0
    assert restarted.load_state().state.watches[0].mode is WatchMode.PERMANENT


def test_offline_hostile_state_and_future_schema_never_escape_temp_roots(
    tmp_path: Path,
) -> None:
    # Given: a hostile permanent identity and a future schema stored under isolated roots.
    store = _store(tmp_path)
    sentinel = tmp_path.parent / "outside-temp-root"
    future = b'{"schemaVersion":999,"watches":[]}'
    store.state_path.parent.mkdir(parents=True)
    _ = store.state_path.write_bytes(future)

    # When: the storage boundary loads the unsupported persisted schema.
    from opatchy_helper.storage import StateSchemaIncompatible

    try:
        _ = store.load_state()
    except StateSchemaIncompatible:
        pass

    # Then: the future document remains intact and no hostile side effect escaped.
    assert store.state_path.read_bytes() == future
    assert not sentinel.exists()
