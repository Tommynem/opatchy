from __future__ import annotations

import multiprocessing
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta, timezone
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Event
from pathlib import Path
from queue import Empty
from typing import Final

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "helper"))

from opatchy_helper.models import (
    ArchStatus,
    FindingId,
    GenerationId,
    ItemId,
    ItemSource,
    NormalizedItem,
    NotificationFingerprint,
    NotificationStatus,
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
from opatchy_helper.notification_types import NotificationSettings
from opatchy_helper.notifications import (
    NotificationChange,
    NotificationCoordinator,
    failure_status,
    is_dispatchable,
    notification_candidates,
)
from opatchy_helper.runner_registry import COMMAND_SPECS
from opatchy_helper.runner_types import (
    CommandExited,
    CommandName,
    CommandResult,
    CommandSucceeded,
)
from opatchy_helper.storage import Storage, SystemAtomicOperations
from opatchy_helper.storage_state import prune_ledger
from opatchy_helper.storage_types import LedgerEntry, PersistentState, WatchRecord

NOW: Final = datetime(2026, 8, 26, 12, tzinfo=timezone.utc)
FOREIGN_OWNER: Final = "-".join(("other", "owner"))


@dataclass(frozen=True, slots=True)
class RecordingRunner:
    results: list[CommandResult]
    calls: list[tuple[CommandName, tuple[str, ...]]]

    def __call__(self, name: CommandName, arguments: tuple[str, ...]) -> CommandResult:
        self.calls.append((name, arguments))
        return self.results.pop(0)


@dataclass(frozen=True, slots=True)
class BlockingProcessRunner:
    entered: Queue[str]
    release: Event

    def __call__(self, name: CommandName, arguments: tuple[str, ...]) -> CommandResult:
        _ = name, arguments
        self.entered.put("entered")
        assert self.release.wait(timeout=5)
        return CommandSucceeded(b"", b"")


@dataclass(slots=True)
class AdvancingClock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now


@dataclass(slots=True)
class FirstKindAdvancingRunner:
    clock: AdvancingClock
    storage: Storage
    lease_expirations: list[datetime]
    calls: int = 0

    def __call__(self, name: CommandName, arguments: tuple[str, ...]) -> CommandResult:
        _ = name, arguments
        self.calls += 1
        if self.calls == 1:
            self.clock.now += timedelta(seconds=15)
        else:
            self.lease_expirations.extend(
                entry.lease_expires_at
                for entry in self.storage.load_state().state.ledger
                if entry.lease_expires_at is not None
            )
        return CommandSucceeded(b"", b"")


@dataclass(slots=True)
class LeaseReplacingRunner:
    storage: Storage
    calls: int = 0

    def __call__(self, name: CommandName, arguments: tuple[str, ...]) -> CommandResult:
        _ = name, arguments
        self.calls += 1
        _ = self.storage.update_state(
            lambda state: PersistentState(
                state.watches,
                tuple(
                    replace(
                        entry,
                        lease_token=FOREIGN_OWNER,
                        lease_expires_at=NOW + timedelta(seconds=30),
                    )
                    if entry.status is NotificationStatus.PENDING
                    else entry
                    for entry in state.ledger
                ),
                state.sources,
            )
        )
        return CommandSucceeded(b"", b"")


def _health(
    source: SourceName,
    *,
    status: SourceStatus = SourceStatus.OK,
    provenance: Provenance = Provenance.LIVE,
    now: datetime = NOW,
) -> SourceHealth:
    fresh_until = now + timedelta(hours=6) if status is SourceStatus.OK else now
    return SourceHealth(source, status, provenance, now, fresh_until, None)


def _item(
    *,
    item_id: str = "arch:demo",
    label: str = "demo",
    installed: str | None = "1.0",
    candidate: str | None = "2.0",
    source: ItemSource = ItemSource.ARCH,
    provenance: Provenance = Provenance.LIVE,
) -> NormalizedItem:
    return NormalizedItem(
        ItemId(item_id),
        source,
        label,
        installed,
        candidate,
        WatchMode.OFF,
        True,
        provenance,
        None if installed is None else f"installed:{installed}",
        None if candidate is None else f"candidate:{candidate}",
    )


def _finding(
    *,
    advisory: str = "AVG-20260001",
    cve_ids: tuple[str, ...] = (),
    fixed: str | None = "2.0",
    severity: Severity = Severity.HIGH,
    provenance: Provenance = Provenance.LIVE,
    status: ArchStatus = ArchStatus.FIXED,
) -> SecurityFinding:
    return SecurityFinding(
        finding_id=FindingId(f"arch:demo:{advisory}"),
        item_id=ItemId("arch:demo"),
        advisory_id=advisory,
        cve_ids=cve_ids,
        severity=severity,
        fixed_version=fixed,
        known_exploited=False,
        provenance=provenance,
        status=status,
    )


def _snapshot(
    *,
    items: tuple[NormalizedItem, ...] = (),
    findings: tuple[SecurityFindingGroup, ...] = (),
    sources: tuple[SourceHealth, ...] = (),
) -> SnapshotResponse:
    return SnapshotResponse(
        NOW,
        GenerationId("scan-1"),
        SnapshotPayload(
            scan_state=ScanState.COMPLETE,
            sources=sources,
            summary=Summary(0, 0, 0, 0),
            items=items,
            findings=findings,
            notifications=(),
        ),
    )


def _state(*watches: WatchRecord) -> PersistentState:
    return PersistentState(watches, (), ())


def _permanent(item_id: str = "arch:demo") -> WatchRecord:
    return WatchRecord(ItemId(item_id), WatchMode.PERMANENT, None, None, False)


def _store(tmp_path: Path) -> Storage:
    return Storage(
        tmp_path / "state.json",
        tmp_path / "cache",
        lambda: NOW,
        SystemAtomicOperations(),
    )


def _dispatch_in_process(
    state_path: str,
    cache_path: str,
    entered: Queue[str],
    release: Event,
    outcomes: Queue[tuple[NotificationStatus, ...]],
) -> None:
    store = Storage(
        Path(state_path), Path(cache_path), lambda: NOW, SystemAtomicOperations()
    )
    snapshot = _snapshot(
        items=(_item(), _item(item_id="arch:second", label="second")),
        sources=(_health(SourceName.ARCH),),
    )
    dispatched = NotificationCoordinator(
        store, BlockingProcessRunner(entered, release), lambda: NOW
    ).dispatch(snapshot)
    outcomes.put(tuple(outcome.status for outcome in dispatched))


def test_notification_candidates_select_only_fresh_permanent_watches_and_security() -> (
    None
):
    # Given: permanent, temporary, and off watches plus fresh Arch and security evidence.
    fresh_items = (_item(), _item(item_id="arch:temporary"), _item(item_id="arch:off"))
    findings = (SecurityFindingGroup(ItemId("arch:demo"), (_finding(),)),)
    state = _state(
        _permanent(),
        WatchRecord(ItemId("arch:temporary"), WatchMode.TEMPORARY, "i", "c", True),
    )
    snapshot = _snapshot(
        items=fresh_items,
        findings=findings,
        sources=(_health(SourceName.ARCH), _health(SourceName.SECURITY)),
    )

    # When: the policy evaluates this scan.
    candidates = notification_candidates(state, snapshot, NOW)

    # Then: only one permanent watch and one fixed high Arch advisory are eligible.
    assert [(candidate.kind.value, candidate.change) for candidate in candidates] == [
        ("security", NotificationChange.FIRST),
        ("watch", NotificationChange.FIRST),
    ]


@pytest.mark.parametrize(
    "snapshot",
    (
        _snapshot(
            items=(_item(provenance=Provenance.LAST_GOOD),),
            sources=(_health(SourceName.ARCH, provenance=Provenance.LAST_GOOD),),
        ),
        _snapshot(
            items=(_item(),),
            sources=(_health(SourceName.ARCH, status=SourceStatus.STALE),),
        ),
        _snapshot(
            items=(_item(),),
            sources=(_health(SourceName.ARCH, now=NOW - timedelta(hours=7)),),
        ),
    ),
)
def test_notification_candidates_reject_stale_or_expired_watch_evidence(
    snapshot: SnapshotResponse,
) -> None:
    # Given: an otherwise eligible permanent watch with non-current evidence.
    # When: the policy evaluates it.
    candidates = notification_candidates(_state(_permanent()), snapshot, NOW)

    # Then: stale, last-good, and expired evidence cannot notify.
    assert candidates == ()


@pytest.mark.parametrize(
    "finding",
    (
        _finding(fixed=None),
        _finding(severity=Severity.MEDIUM),
        _finding(provenance=Provenance.LAST_GOOD),
        _finding(status=ArchStatus.VULNERABLE),
    ),
)
def test_notification_candidates_reject_ineligible_security_findings(
    finding: SecurityFinding,
) -> None:
    # Given: a security finding missing a policy requirement.
    snapshot = _snapshot(
        findings=(SecurityFindingGroup(ItemId("arch:demo"), (finding,)),),
        sources=(_health(SourceName.SECURITY),),
    )

    # When: the policy evaluates the fresh scan.
    candidates = notification_candidates(PersistentState.empty(), snapshot, NOW)

    # Then: no low-confidence security evidence becomes a desktop notification.
    assert candidates == ()


def test_notification_candidates_model_first_new_and_unchanged_identities() -> None:
    # Given: a permanent watch with a recorded first candidate identity.
    state = _state(_permanent())
    first_snapshot = _snapshot(items=(_item(),), sources=(_health(SourceName.ARCH),))
    first = notification_candidates(state, first_snapshot, NOW)[0]
    delivered = LedgerEntry(first.fingerprint, NotificationStatus.DELIVERED, NOW)
    restored = PersistentState(state.watches, (delivered,), ())

    # When: the same candidate and then a changed candidate are evaluated after restart.
    unchanged = notification_candidates(restored, first_snapshot, NOW)[0]
    changed = notification_candidates(
        restored,
        _snapshot(items=(_item(candidate="3.0"),), sources=(_health(SourceName.ARCH),)),
        NOW,
    )[0]

    # Then: durable identity distinguishes first, unchanged, and changed candidates.
    assert first.change is NotificationChange.FIRST
    assert unchanged.change is NotificationChange.UNCHANGED
    assert changed.change is NotificationChange.NEW
    assert changed.fingerprint != first.fingerprint


def test_security_fix_and_severity_escalation_create_new_identities() -> None:
    # Given: a delivered high-severity fixed advisory.
    first_snapshot = _snapshot(
        findings=(SecurityFindingGroup(ItemId("arch:demo"), (_finding(),)),),
        sources=(_health(SourceName.SECURITY),),
    )
    first = notification_candidates(PersistentState.empty(), first_snapshot, NOW)[0]
    state = PersistentState(
        (), (LedgerEntry(first.fingerprint, NotificationStatus.DELIVERED, NOW),), ()
    )

    # When: its fixed version changes and its severity escalates.
    changed_fix = notification_candidates(
        state,
        _snapshot(
            findings=(
                SecurityFindingGroup(ItemId("arch:demo"), (_finding(fixed="2.1"),)),
            ),
            sources=(_health(SourceName.SECURITY),),
        ),
        NOW,
    )[0]
    escalated = notification_candidates(
        state,
        _snapshot(
            findings=(
                SecurityFindingGroup(
                    ItemId("arch:demo"), (_finding(severity=Severity.CRITICAL),)
                ),
            ),
            sources=(_health(SourceName.SECURITY),),
        ),
        NOW,
    )[0]

    # Then: both changes are independently new notification identities.
    assert changed_fix.change is NotificationChange.NEW
    assert escalated.change is NotificationChange.NEW
    assert len({first.fingerprint, changed_fix.fingerprint, escalated.fingerprint}) == 3


def test_security_cve_evidence_is_canonical_and_creates_new_identity() -> None:
    # Given: a delivered advisory with two CVE identifiers in one source order.
    first_snapshot = _snapshot(
        findings=(
            SecurityFindingGroup(
                ItemId("arch:demo"),
                (_finding(cve_ids=("CVE-2026-2", "CVE-2026-1")),),
            ),
        ),
        sources=(_health(SourceName.SECURITY),),
    )
    first = notification_candidates(PersistentState.empty(), first_snapshot, NOW)[0]
    state = PersistentState(
        (), (LedgerEntry(first.fingerprint, NotificationStatus.DELIVERED, NOW),), ()
    )

    # When: equivalent evidence is reordered and then one CVE changes.
    unchanged = notification_candidates(
        state,
        _snapshot(
            findings=(
                SecurityFindingGroup(
                    ItemId("arch:demo"),
                    (_finding(cve_ids=("CVE-2026-1", "CVE-2026-2")),),
                ),
            ),
            sources=(_health(SourceName.SECURITY),),
        ),
        NOW,
    )[0]
    changed = notification_candidates(
        state,
        _snapshot(
            findings=(
                SecurityFindingGroup(
                    ItemId("arch:demo"),
                    (_finding(cve_ids=("CVE-2026-1", "CVE-2026-3")),),
                ),
            ),
            sources=(_health(SourceName.SECURITY),),
        ),
        NOW,
    )[0]

    # Then: ordering deduplicates, while changed CVE evidence is a new advisory state.
    assert unchanged.change is NotificationChange.UNCHANGED
    assert unchanged.fingerprint == first.fingerprint
    assert changed.change is NotificationChange.NEW
    assert changed.fingerprint != first.fingerprint


def test_watch_identity_changes_when_adapter_installed_evidence_changes() -> None:
    # Given: a permanent watch with a delivered candidate fingerprint.
    state = _state(_permanent())
    initial = _snapshot(items=(_item(),), sources=(_health(SourceName.ARCH),))
    first = notification_candidates(state, initial, NOW)[0]
    restored = PersistentState(
        state.watches,
        (LedgerEntry(first.fingerprint, NotificationStatus.DELIVERED, NOW),),
        (),
    )

    # When: only the adapter-produced installed fingerprint changes.
    changed = notification_candidates(
        restored,
        _snapshot(
            items=(_item(installed="1.1"),),
            sources=(_health(SourceName.ARCH),),
        ),
        NOW,
    )[0]

    # Then: watched identity is new despite the unchanged candidate version.
    assert changed.change is NotificationChange.NEW
    assert changed.fingerprint != first.fingerprint


def test_coordinator_delivers_exact_closed_argv_once_per_kind_and_deduplicates_restart(
    tmp_path: Path,
) -> None:
    # Given: fresh watch and security evidence with hostile labels and a shell sentinel.
    sentinel = Path("/tmp/opatchy-injection-sentinel")
    sentinel.unlink(missing_ok=True)
    store = _store(tmp_path)
    store.save_state(_state(_permanent()))
    hostile = "<b>$(touch /tmp/opatchy-injection-sentinel)</b>& --urgency=critical"
    snapshot = _snapshot(
        items=(_item(label=hostile),),
        findings=(
            SecurityFindingGroup(ItemId("arch:demo"), (_finding(advisory=hostile),)),
        ),
        sources=(_health(SourceName.ARCH), _health(SourceName.SECURITY)),
    )
    runner = RecordingRunner(
        [CommandSucceeded(b"", b""), CommandSucceeded(b"", b"")], []
    )
    coordinator = NotificationCoordinator(store, runner, lambda: NOW)

    # When: the scan is dispatched and then reloaded from durable state.
    first = coordinator.dispatch(snapshot)
    restarted = NotificationCoordinator(store, runner, lambda: NOW).dispatch(snapshot)

    # Then: both fixed notifications succeed once, carrying hostile data only as text args.
    assert COMMAND_SPECS[CommandName.NOTIFY].base_argv == (
        "-a",
        "Opatchy",
        "-u",
        "normal",
    )
    assert [outcome.status for outcome in first] == [
        NotificationStatus.DELIVERED,
        NotificationStatus.DELIVERED,
    ]
    assert restarted == ()
    assert [name for name, _ in runner.calls] == [
        CommandName.NOTIFY,
        CommandName.NOTIFY,
    ]
    assert all(len(arguments) == 2 for _, arguments in runner.calls)
    assert all(
        "-a" not in arguments and "-u" not in arguments for _, arguments in runner.calls
    )
    assert all(
        "<b>" not in argument and "</b>" not in argument
        for _, arguments in runner.calls
        for argument in arguments
    )
    assert not sentinel.exists()


def test_coordinator_keeps_failure_pending_for_one_retry_then_marks_failed(
    tmp_path: Path,
) -> None:
    # Given: one fresh permanent watch and two nonzero notification deliveries.
    store = _store(tmp_path)
    store.save_state(_state(_permanent()))
    snapshot = _snapshot(items=(_item(),), sources=(_health(SourceName.ARCH),))
    runner = RecordingRunner(
        [CommandExited(1, b"", b""), CommandExited(1, b"", b"")], []
    )
    coordinator = NotificationCoordinator(store, runner, lambda: NOW)

    # When: the first delivery fails and the identical pending identity retries once.
    first = coordinator.dispatch(snapshot)
    second = coordinator.dispatch(snapshot)

    # Then: success is never recorded before exit zero, and retry is bounded.
    assert first[0].status is NotificationStatus.PENDING
    assert store.load_state().state.ledger[0].lease_token is None
    assert store.load_state().state.ledger[0].lease_expires_at is None
    assert second[0].status is NotificationStatus.FAILED
    assert store.load_state().state.ledger[0].status is NotificationStatus.FAILED
    assert len(runner.calls) == 2


def test_coordinator_refreshes_each_kind_lease_after_runner_time(
    tmp_path: Path,
) -> None:
    # Given: watch and security batches with a runner that consumes half a lease.
    store = _store(tmp_path)
    store.save_state(_state(_permanent()))
    clock = AdvancingClock(NOW)
    runner = FirstKindAdvancingRunner(clock, store, [])
    snapshot = _snapshot(
        items=(_item(),),
        findings=(SecurityFindingGroup(ItemId("arch:demo"), (_finding(),)),),
        sources=(_health(SourceName.ARCH), _health(SourceName.SECURITY)),
    )

    # When: the first kind advances time before the second kind is reserved.
    outcomes = NotificationCoordinator(store, runner, clock).dispatch(snapshot)

    # Then: the second kind receives its own full 30-second lease.
    assert [outcome.status for outcome in outcomes] == [
        NotificationStatus.DELIVERED,
        NotificationStatus.DELIVERED,
    ]
    assert runner.lease_expirations == [NOW + timedelta(seconds=45)] * 2


def test_coordinator_reports_nothing_after_runner_replaces_batch_leases(
    tmp_path: Path,
) -> None:
    # Given: a claimed watch batch whose leases are reclaimed while its runner returns.
    store = _store(tmp_path)
    store.save_state(_state(_permanent()))
    runner = LeaseReplacingRunner(store)
    snapshot = _snapshot(items=(_item(),), sources=(_health(SourceName.ARCH),))

    # When: completion observes a foreign owner and candidate token after the runner.
    outcomes = NotificationCoordinator(store, runner, lambda: NOW).dispatch(snapshot)

    # Then: the old batch neither reports nor overwrites the reclaimed pending leases.
    assert outcomes == ()
    assert runner.calls == 1
    assert all(
        entry.status is NotificationStatus.PENDING
        and entry.lease_token == FOREIGN_OWNER
        and entry.lease_expires_at == NOW + timedelta(seconds=30)
        for entry in store.load_state().state.ledger
    )


def test_coordinator_reports_nothing_for_foreign_committed_candidate(
    tmp_path: Path,
) -> None:
    # Given: a runner whose candidate lease is finalized differently by another owner.
    store = _store(tmp_path)
    store.save_state(_state(_permanent()))
    snapshot = _snapshot(items=(_item(),), sources=(_health(SourceName.ARCH),))

    def foreign_completion(
        name: CommandName, arguments: tuple[str, ...]
    ) -> CommandResult:
        _ = name, arguments
        _ = store.update_state(
            lambda state: PersistentState(
                state.watches,
                tuple(
                    replace(
                        entry,
                        status=NotificationStatus.FAILED,
                        lease_token=None,
                        lease_expires_at=None,
                    )
                    if str(entry.fingerprint).startswith("watch-v1:")
                    else entry
                    for entry in state.ledger
                ),
                state.sources,
            )
        )
        return CommandSucceeded(b"", b"")

    # When: the old batch completes after the foreign failed state is committed.
    outcomes = NotificationCoordinator(store, foreign_completion, lambda: NOW).dispatch(
        snapshot
    )

    # Then: it does not overwrite or report the other owner’s failed completion.
    assert outcomes == ()
    assert (
        next(iter(store.load_state().state.ledger)).status is NotificationStatus.FAILED
    )


def test_coordinator_default_clock_records_utc_delivery(tmp_path: Path) -> None:
    # Given: a fresh watch candidate and the coordinator's production default clock.
    now = datetime.now(UTC)
    store = _store(tmp_path)
    store.save_state(_state(_permanent()))
    runner = RecordingRunner([CommandSucceeded(b"", b"")], [])
    snapshot = _snapshot(items=(_item(),), sources=(_health(SourceName.ARCH, now=now),))

    # When: successful ordinary delivery is dispatched without injecting a test clock.
    outcome = NotificationCoordinator(store, runner).dispatch(snapshot)

    # Then: durable ledger state has a timezone-safe delivered timestamp.
    assert outcome[0].status is NotificationStatus.DELIVERED
    assert store.load_state().state.ledger[0].recorded_at.tzinfo is UTC


def test_coordinator_supersedes_old_pending_when_candidate_changes(
    tmp_path: Path,
) -> None:
    # Given: a pending old candidate that is superseded by fresh evidence.
    store = _store(tmp_path)
    state = _state(_permanent())
    first = notification_candidates(
        state, _snapshot(items=(_item(),), sources=(_health(SourceName.ARCH),)), NOW
    )[0]
    old = LedgerEntry(first.fingerprint, NotificationStatus.PENDING, NOW)
    store.save_state(PersistentState(state.watches, (old,), ()))
    runner = RecordingRunner([CommandSucceeded(b"", b"")], [])
    coordinator = NotificationCoordinator(store, runner, lambda: NOW)

    # When: the changed candidate is dispatched.
    changed = coordinator.dispatch(
        _snapshot(items=(_item(candidate="3.0"),), sources=(_health(SourceName.ARCH),))
    )

    # Then: the old pending identity is suppressed and the changed candidate delivers.
    assert changed[0].status is NotificationStatus.DELIVERED
    assert (
        next(
            entry.status
            for entry in store.load_state().state.ledger
            if entry.fingerprint == first.fingerprint
        )
        is NotificationStatus.SUPPRESSED
    )
    assert len(runner.calls) == 1


def test_coordinator_does_not_replay_suppressed_history(tmp_path: Path) -> None:
    # Given: a DND-suppressed historical identity for a fresh permanent watch.
    store = _store(tmp_path)
    state = _state(_permanent())
    snapshot = _snapshot(items=(_item(),), sources=(_health(SourceName.ARCH),))
    candidate = notification_candidates(state, snapshot, NOW)[0]
    store.save_state(
        PersistentState(
            state.watches,
            (LedgerEntry(candidate.fingerprint, NotificationStatus.SUPPRESSED, NOW),),
            (),
        )
    )
    runner = RecordingRunner([], [])

    # When: ordinary FreeDesktop delivery runs after restart.
    outcomes = NotificationCoordinator(store, runner, lambda: NOW).dispatch(snapshot)

    # Then: no DND inspection or historical replay occurs.
    assert outcomes == ()
    assert runner.calls == []


def test_pruning_keeps_pending_retry_and_bounds_final_failed_notification() -> None:
    # Given: one active pending retry and one old final failed notification.
    pending = LedgerEntry(
        NotificationFingerprint("pending"),
        NotificationStatus.PENDING,
        NOW - timedelta(days=999),
    )
    failed = LedgerEntry(
        NotificationFingerprint("failed"),
        NotificationStatus.FAILED,
        NOW - timedelta(days=999),
    )

    # When: existing ledger pruning runs.
    pruned = prune_ledger(PersistentState((), (pending, failed), ()), NOW)

    # Then: retry remains active while bounded inactive history is removed.
    assert pruned.ledger == (pending,)


@pytest.mark.parametrize(
    ("source", "source_name"),
    (
        (ItemSource.OMARCHY, SourceName.OMARCHY),
        (ItemSource.AUR, SourceName.AUR),
        (ItemSource.FLATPAK, SourceName.FLATPAK),
        (ItemSource.MISE, SourceName.MISE),
    ),
)
def test_notification_candidates_map_each_supported_item_source_to_fresh_health(
    source: ItemSource, source_name: SourceName
) -> None:
    # Given: a permanent watch with a non-Arch source candidate and its fresh health.
    item_id = f"{source.value}:demo"
    snapshot = _snapshot(
        items=(_item(item_id=item_id, source=source),), sources=(_health(source_name),)
    )

    # When: the policy resolves the source health through its typed mapping.
    candidates = notification_candidates(_state(_permanent(item_id)), snapshot, NOW)

    # Then: the source has one eligible watched candidate.
    assert len(candidates) == 1


@dataclass(frozen=True, slots=True)
class FutureVariant:
    pass


def test_policy_fails_closed_for_future_discriminators() -> None:
    # Given: dynamically widened values at every closed policy boundary.
    health = _health(SourceName.ARCH)
    object.__setattr__(health, "status", FutureVariant())
    item_provenance = _item()
    object.__setattr__(item_provenance, "provenance", FutureVariant())
    item_source = _item()
    object.__setattr__(item_source, "source", FutureVariant())
    finding_status = _finding()
    object.__setattr__(finding_status, "status", FutureVariant())
    finding_severity = _finding()
    object.__setattr__(finding_severity, "severity", FutureVariant())
    entry = LedgerEntry(
        NotificationFingerprint("future"), NotificationStatus.PENDING, NOW
    )
    object.__setattr__(entry, "status", FutureVariant())
    dynamic_failure: Callable[..., NotificationStatus] = failure_status

    # When: each exhaustive matcher receives an unknown discriminator.
    # Then: every branch rejects it rather than broadening notification delivery.
    with pytest.raises(AssertionError):
        _ = notification_candidates(
            _state(_permanent()),
            _snapshot(items=(_item(),), sources=(health,)),
            NOW,
        )
    with pytest.raises(AssertionError):
        _ = notification_candidates(
            _state(_permanent()),
            _snapshot(items=(item_provenance,), sources=(_health(SourceName.ARCH),)),
            NOW,
        )
    with pytest.raises(AssertionError):
        _ = notification_candidates(
            _state(_permanent()),
            _snapshot(items=(item_source,), sources=(_health(SourceName.ARCH),)),
            NOW,
        )
    with pytest.raises(AssertionError):
        _ = notification_candidates(
            PersistentState.empty(),
            _snapshot(
                findings=(
                    SecurityFindingGroup(ItemId("arch:demo"), (finding_status,)),
                ),
                sources=(_health(SourceName.SECURITY),),
            ),
            NOW,
        )
    with pytest.raises(AssertionError):
        _ = notification_candidates(
            PersistentState.empty(),
            _snapshot(
                findings=(
                    SecurityFindingGroup(ItemId("arch:demo"), (finding_severity,)),
                ),
                sources=(_health(SourceName.SECURITY),),
            ),
            NOW,
        )
    with pytest.raises(AssertionError):
        _ = is_dispatchable(entry)
    with pytest.raises(AssertionError):
        _ = dynamic_failure(FutureVariant())


def test_coordinator_fails_closed_for_future_runner_result(tmp_path: Path) -> None:
    # Given: a fresh candidate and a dynamically widened closed-runner result.
    store = _store(tmp_path)
    store.save_state(_state(_permanent()))
    runner = RecordingRunner([], [])
    object.__setattr__(runner, "results", [FutureVariant()])
    snapshot = _snapshot(items=(_item(),), sources=(_health(SourceName.ARCH),))

    # When: the coordinator receives the result after atomically reserving delivery.
    # Then: it raises rather than treating an unknown runner outcome as success or retry.
    with pytest.raises(AssertionError):
        _ = NotificationCoordinator(store, runner, lambda: NOW).dispatch(snapshot)


def test_notification_settings_default_and_disabled_categories_skip_candidates() -> (
    None
):
    # Given: fresh permanent-watch and security evidence under each disabled setting.
    snapshot = _snapshot(
        items=(_item(),),
        findings=(SecurityFindingGroup(ItemId("arch:demo"), (_finding(),)),),
        sources=(_health(SourceName.ARCH), _health(SourceName.SECURITY)),
    )
    state = _state(_permanent())

    # When: category settings are applied before policy candidate construction.
    defaults = NotificationSettings()
    watches_disabled = notification_candidates(
        state, snapshot, NOW, NotificationSettings(notify_permanent=False)
    )
    security_disabled = notification_candidates(
        state, snapshot, NOW, NotificationSettings(notify_security=False)
    )

    # Then: defaults are exact and disabled categories yield no matching candidates.
    assert defaults.notify_permanent
    assert defaults.notify_security
    assert defaults.security_minimum_severity is Severity.HIGH
    assert [candidate.kind.value for candidate in watches_disabled] == ["security"]
    assert [candidate.kind.value for candidate in security_disabled] == ["watch"]


@pytest.mark.parametrize(
    ("minimum", "expected"),
    (
        (Severity.LOW, ("high", "critical")),
        (Severity.MEDIUM, ("high", "critical")),
        (Severity.HIGH, ("high", "critical")),
        (Severity.CRITICAL, ("critical",)),
    ),
)
def test_notification_settings_apply_security_minimum_severity(
    minimum: Severity, expected: tuple[str, ...]
) -> None:
    # Given: otherwise eligible fixed advisories across all policy severities.
    findings = tuple(
        _finding(advisory=f"AVG-{severity.value}", severity=severity)
        for severity in Severity
    )
    snapshot = _snapshot(
        findings=(SecurityFindingGroup(ItemId("arch:demo"), findings),),
        sources=(_health(SourceName.SECURITY),),
    )

    # When: the typed security threshold evaluates the fresh findings.
    candidates = notification_candidates(
        PersistentState.empty(),
        snapshot,
        NOW,
        NotificationSettings(security_minimum_severity=minimum),
    )

    # Then: only fixed Arch advisories at or above that threshold remain eligible.
    assert {candidate.body.rsplit("(", 1)[1][:-2] for candidate in candidates} == set(
        expected
    )


def test_concurrent_coordinators_only_the_claim_winner_invokes_runner(
    tmp_path: Path,
) -> None:
    # Given: two process-isolated coordinators share fresh permanent-watch state.
    store = _store(tmp_path)
    store.save_state(_state(_permanent(), _permanent("arch:second")))
    entered: Queue[str] = multiprocessing.Queue()
    outcomes: Queue[tuple[NotificationStatus, ...]] = multiprocessing.Queue()
    release = multiprocessing.Event()
    first = multiprocessing.Process(
        target=_dispatch_in_process,
        args=(
            str(store.state_path),
            str(store.cache_path),
            entered,
            release,
            outcomes,
        ),
    )
    second = multiprocessing.Process(
        target=_dispatch_in_process,
        args=(
            str(store.state_path),
            str(store.cache_path),
            entered,
            release,
            outcomes,
        ),
    )

    # When: the first runner is held after its durable claim and the second dispatches.
    first.start()
    assert entered.get(timeout=1) == "entered"
    second.start()
    second.join(5)

    # Then: the second coordinator had no delivery and never entered its runner.
    assert second.exitcode == 0
    assert outcomes.get(timeout=1) == ()
    with pytest.raises(Empty):
        _ = entered.get(timeout=0.2)

    release.set()
    first.join(5)
    assert first.exitcode == 0
    assert outcomes.get(timeout=1) == (
        NotificationStatus.DELIVERED,
        NotificationStatus.DELIVERED,
    )


def test_coordinator_does_not_run_when_another_owner_holds_candidate_lease(
    tmp_path: Path,
) -> None:
    # Given: a fresh permanent-watch candidate already leased by another coordinator.
    store = _store(tmp_path)
    state = _state(_permanent())
    snapshot = _snapshot(items=(_item(),), sources=(_health(SourceName.ARCH),))
    candidate = notification_candidates(state, snapshot, NOW)[0]
    store.save_state(
        PersistentState(
            state.watches,
            (
                LedgerEntry(
                    candidate.fingerprint,
                    NotificationStatus.PENDING,
                    NOW,
                    "other-owner",
                    NOW + timedelta(seconds=30),
                ),
            ),
            (),
        )
    )
    runner = RecordingRunner([], [])

    # When: this coordinator dispatches the same fresh candidate.
    outcomes = NotificationCoordinator(store, runner, lambda: NOW).dispatch(snapshot)

    # Then: it cannot claim the lease and never invokes the notification runner.
    assert outcomes == ()
    assert runner.calls == []


def test_coordinator_does_not_run_when_another_owner_holds_kind_lease(
    tmp_path: Path,
) -> None:
    # Given: a fresh watch candidate and another coordinator's live watch batch owner.
    store = _store(tmp_path)
    state = _state(_permanent())
    store.save_state(
        PersistentState(
            state.watches,
            (
                LedgerEntry(
                    NotificationFingerprint("notification-owner-v1:watch"),
                    NotificationStatus.PENDING,
                    NOW,
                    "other-owner",
                    NOW + timedelta(seconds=30),
                ),
            ),
            (),
        )
    )
    runner = RecordingRunner([], [])
    snapshot = _snapshot(items=(_item(),), sources=(_health(SourceName.ARCH),))

    # When: this coordinator reaches the live owner sentinel before reserving entries.
    outcomes = NotificationCoordinator(store, runner, lambda: NOW).dispatch(snapshot)

    # Then: it skips the entire kind without entering the notification runner.
    assert outcomes == ()
    assert runner.calls == []


def test_coordinator_batches_watch_candidates_and_deduplicates_unchanged_restart(
    tmp_path: Path,
) -> None:
    # Given: two eligible permanent watches from one fresh source.
    store = _store(tmp_path)
    store.save_state(_state(_permanent(), _permanent("arch:second")))
    snapshot = _snapshot(
        items=(_item(), _item(item_id="arch:second", label="second")),
        sources=(_health(SourceName.ARCH),),
    )
    runner = RecordingRunner([CommandSucceeded(b"", b"")], [])
    coordinator = NotificationCoordinator(store, runner, lambda: NOW)

    # When: the scan and then its unchanged restart are dispatched.
    first = coordinator.dispatch(snapshot)
    restarted = coordinator.dispatch(snapshot)

    # Then: one summarized handoff accounts for both fingerprints with no trickle.
    assert [outcome.status for outcome in first] == [
        NotificationStatus.DELIVERED,
        NotificationStatus.DELIVERED,
    ]
    assert restarted == ()
    assert len(runner.calls) == 1
    assert "1 additional watched update" in runner.calls[0][1][1]
    assert {entry.status for entry in store.load_state().state.ledger} == {
        NotificationStatus.DELIVERED
    }


def test_coordinator_batches_security_candidates_with_one_runner_call(
    tmp_path: Path,
) -> None:
    # Given: two fresh high/critical fixed Arch advisories.
    store = _store(tmp_path)
    snapshot = _snapshot(
        findings=(
            SecurityFindingGroup(
                ItemId("arch:demo"),
                (
                    _finding(),
                    _finding(advisory="AVG-20260002", severity=Severity.CRITICAL),
                ),
            ),
        ),
        sources=(_health(SourceName.SECURITY),),
    )
    runner = RecordingRunner([CommandSucceeded(b"", b"")], [])

    # When: the coordinator dispatches the eligible security batch.
    outcomes = NotificationCoordinator(store, runner, lambda: NOW).dispatch(snapshot)

    # Then: both fingerprints are delivered after one summarized notification.
    assert [outcome.status for outcome in outcomes] == [
        NotificationStatus.DELIVERED,
        NotificationStatus.DELIVERED,
    ]
    assert len(runner.calls) == 1
    assert "1 additional security update" in runner.calls[0][1][1]


def test_failed_watch_batch_retries_once_and_accounts_for_every_fingerprint(
    tmp_path: Path,
) -> None:
    # Given: two eligible watched updates and two failed batch handoffs.
    store = _store(tmp_path)
    store.save_state(_state(_permanent(), _permanent("arch:second")))
    snapshot = _snapshot(
        items=(_item(), _item(item_id="arch:second", label="second")),
        sources=(_health(SourceName.ARCH),),
    )
    runner = RecordingRunner(
        [CommandExited(1, b"", b""), CommandExited(1, b"", b"")], []
    )
    coordinator = NotificationCoordinator(store, runner, lambda: NOW)

    # When: the original batch fails and its unchanged batch retries.
    first = coordinator.dispatch(snapshot)
    second = coordinator.dispatch(snapshot)

    # Then: every fingerprint follows the bounded pending-to-failed transition.
    assert [outcome.status for outcome in first] == [
        NotificationStatus.PENDING,
        NotificationStatus.PENDING,
    ]
    assert [outcome.status for outcome in second] == [
        NotificationStatus.FAILED,
        NotificationStatus.FAILED,
    ]
    assert len(runner.calls) == 2
    assert {entry.status for entry in store.load_state().state.ledger} == {
        NotificationStatus.FAILED
    }
