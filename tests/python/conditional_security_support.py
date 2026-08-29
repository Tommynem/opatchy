from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from opatchy_helper.models import (
    ArchStatus,
    FindingId,
    GenerationId,
    ItemId,
    ItemSource,
    NormalizedItem,
    NotificationOutcome,
    Provenance,
    ScanState,
    SecurityFinding,
    SecurityFindingGroup,
    Severity,
    SnapshotPayload,
    SnapshotResponse,
    SourceHealth,
    SourceName,
    SourceStatus,
    Summary,
    WatchMode,
)
from opatchy_helper.runner_types import CommandExited, CommandName, CommandSucceeded
from opatchy_helper.storage import Storage, SystemAtomicOperations
from opatchy_helper.storage_types import SecurityFixCondition, WatchRecord

NOW = datetime(2026, 8, 29, 12, tzinfo=UTC)
CONDITION = SecurityFixCondition("AVG-20260001", ("CVE-2026-12345",), "2.0")


def watch() -> WatchRecord:
    return WatchRecord(
        ItemId("arch:demo"),
        WatchMode.TEMPORARY,
        "installed",
        "candidate",
        True,
        CONDITION,
    )


def snapshot(
    *,
    candidate: str | None = "2.0",
    fixed: str = "2.0",
    arch_stale: bool = False,
    security_stale: bool = False,
    arch_provenance: Provenance = Provenance.LIVE,
    security_provenance: Provenance = Provenance.LIVE,
    item_provenance: Provenance = Provenance.LIVE,
    finding_provenance: Provenance = Provenance.LIVE,
    item_id: str = "arch:demo",
) -> SnapshotResponse:
    item = NormalizedItem(
        ItemId(item_id),
        ItemSource.ARCH,
        "demo",
        "1.0",
        candidate,
        WatchMode.OFF,
        True,
        item_provenance,
        "installed",
        "candidate",
    )
    finding = SecurityFinding(
        FindingId("arch:demo:AVG-20260001"),
        ItemId("arch:demo"),
        "AVG-20260001",
        ("CVE-2026-12345",),
        Severity.HIGH,
        fixed,
        False,
        finding_provenance,
        ArchStatus.FIXED,
    )
    return SnapshotResponse(
        NOW,
        GenerationId("scan-conditional"),
        SnapshotPayload(
            ScanState.COMPLETE,
            (
                SourceHealth(
                    SourceName.ARCH,
                    SourceStatus.STALE if arch_stale else SourceStatus.OK,
                    arch_provenance,
                    NOW,
                    NOW if arch_stale else NOW + timedelta(hours=1),
                    None,
                ),
                SourceHealth(
                    SourceName.SECURITY,
                    SourceStatus.STALE if security_stale else SourceStatus.OK,
                    security_provenance,
                    NOW,
                    NOW if security_stale else NOW + timedelta(hours=1),
                    None,
                ),
            ),
            Summary(1, 1, 1, 0),
            (item,),
            (SecurityFindingGroup(ItemId("arch:demo"), (finding,)),),
            (),
        ),
    )


def versions(result: CommandSucceeded | CommandExited):
    def run(name: CommandName, arguments: tuple[str, ...]):
        assert name is CommandName.VERCMP
        assert arguments[1] == "2.0"
        return result

    return run


def store(tmp_path: Path) -> Storage:
    return Storage(
        tmp_path / "state.json",
        tmp_path / "cache",
        lambda: NOW,
        SystemAtomicOperations(),
    )


@dataclass(slots=True)
class RecordingDispatcher:
    store: Storage
    committed_before_dispatch: list[bool]
    outcomes: tuple[NotificationOutcome, ...] = ()

    def dispatch(self, snapshot: SnapshotResponse) -> tuple[NotificationOutcome, ...]:
        _ = snapshot
        self.committed_before_dispatch.append(self.store.load_generation() is not None)
        return self.outcomes
