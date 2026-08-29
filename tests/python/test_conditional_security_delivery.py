from dataclasses import dataclass
from pathlib import Path

import pytest
from opatchy_helper import scan as scan_module
from opatchy_helper.models import (
    GenerationId,
    ItemId,
    ItemSource,
    NotificationFingerprint,
    NotificationOutcome,
    NotificationStatus,
    Severity,
    SnapshotResponse,
)
from opatchy_helper.notification_types import NotificationSettings
from opatchy_helper.notifications import NotificationCoordinator
from opatchy_helper.runner_types import (
    CommandExited,
    CommandName,
    CommandResult,
    CommandSucceeded,
)
from opatchy_helper.scan import ScanCoordinator
from opatchy_helper.scan_types import ScanRequest
from opatchy_helper.stars import (
    CachedInventory,
    CachedItem,
    FreshSourceScan,
    transition,
)
from opatchy_helper.storage import Storage
from opatchy_helper.storage_types import PersistentState

from tests.python.conditional_security_support import (
    NOW,
    RecordingDispatcher,
    snapshot,
    store,
    watch,
)
from tests.python.scan_support import collector


def test_conditional_notification_dedupes_after_delivery_without_clearing_watch(
    tmp_path: Path,
) -> None:
    storage = store(tmp_path)
    storage.save_state(PersistentState((watch(),), (), ()))
    calls: list[CommandName] = []

    def run(name: CommandName, arguments: tuple[str, ...]) -> CommandResult:
        _ = arguments
        calls.append(name)
        return (
            CommandSucceeded(b"0\n", b"")
            if name is CommandName.VERCMP
            else CommandSucceeded(b"", b"")
        )

    first = NotificationCoordinator(storage, run, lambda: NOW).dispatch(snapshot())
    repeated = NotificationCoordinator(storage, run, lambda: NOW).dispatch(snapshot())
    assert [outcome.status.value for outcome in first] == ["delivered"]
    assert repeated == ()
    assert calls.count(CommandName.NOTIFY) == 1
    assert storage.load_state().state.watches == (watch(),)


def test_conditional_notification_failure_remains_retryable(tmp_path: Path) -> None:
    storage = store(tmp_path)
    storage.save_state(PersistentState((watch(),), (), ()))
    notifications = iter((CommandExited(1, b"", b""), CommandSucceeded(b"", b"")))

    def run(name: CommandName, arguments: tuple[str, ...]) -> CommandResult:
        _ = arguments
        return (
            CommandSucceeded(b"0\n", b"")
            if name is CommandName.VERCMP
            else next(notifications)
        )

    first = NotificationCoordinator(storage, run, lambda: NOW).dispatch(snapshot())
    second = NotificationCoordinator(storage, run, lambda: NOW).dispatch(snapshot())
    assert [outcome.status.value for outcome in first] == ["pending"]
    assert [outcome.status.value for outcome in second] == ["delivered"]
    assert storage.load_state().state.watches == (watch(),)


def test_fresh_installed_change_clears_conditional_watch_without_delivery() -> None:
    updated = transition(
        PersistentState((watch(),), (), ()),
        FreshSourceScan(
            ItemSource.ARCH,
            CachedInventory(
                (CachedItem(ItemId("arch:demo"), ItemSource.ARCH, "new", None, True),)
            ),
        ),
    )
    assert updated.watches == ()


def test_scan_dispatches_only_after_commit_and_projects_outcomes(
    tmp_path: Path,
) -> None:
    storage = store(tmp_path)
    outcome = NotificationOutcome(
        NotificationFingerprint("test-outcome"), NotificationStatus.DELIVERED
    )
    dispatcher = RecordingDispatcher(storage, [], (outcome,))
    coordinator = ScanCoordinator(storage, collector(), lambda: NOW, dispatcher)
    request = ScanRequest(GenerationId("scan-conditional"), 0, True)
    first = coordinator.run(request)
    second = coordinator.run(request)
    assert first.committed
    assert not second.committed
    assert dispatcher.committed_before_dispatch == [True]
    assert first.snapshot.payload.notifications == (outcome,)
    assert second.snapshot.payload.notifications == ()


def test_scan_coordinator_passes_request_settings_to_default_notification_dispatcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[NotificationSettings] = []

    @dataclass(frozen=True, slots=True)
    class CapturingCoordinator:
        settings: NotificationSettings

        def __init__(self, storage: Storage, *, settings: NotificationSettings) -> None:
            _ = storage
            object.__setattr__(self, "settings", settings)
            captured.append(settings)

        def dispatch(
            self, snapshot: SnapshotResponse
        ) -> tuple[NotificationOutcome, ...]:
            _ = snapshot
            return ()

    expected = NotificationSettings(False, True, Severity.CRITICAL)
    monkeypatch.setattr(scan_module, "NotificationCoordinator", CapturingCoordinator)
    _ = ScanCoordinator(store(tmp_path), collector(), lambda: NOW).run(
        ScanRequest(GenerationId("scan-settings"), 0, True, expected)
    )
    assert captured == [expected]
