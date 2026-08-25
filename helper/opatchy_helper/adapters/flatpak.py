from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum, unique
from typing import Final, assert_never

from ..models import ItemId, ItemSource, NormalizedItem, Provenance, WatchMode
from ..runner import run_command
from ..runner_types import (
    CommandExited,
    CommandMissing,
    CommandName,
    CommandOutputExceeded,
    CommandRejected,
    CommandResult,
    CommandSucceeded,
    CommandTimedOut,
)
from .flatpak_parser import (
    FlatpakInventoryRow,
    FlatpakKind,
    FlatpakParseFailure,
    FlatpakUpdate,
    parse_inventory,
    parse_updates,
)


@unique
class FlatpakScope(StrEnum):
    USER = "user"
    SYSTEM = "system"


@unique
class FlatpakScopeStatus(StrEnum):
    OK = "ok"
    NOT_APPLICABLE = "not_applicable"
    MISSING_DEPENDENCY = "missing_dependency"
    TIMEOUT = "timeout"
    OUTPUT_EXCEEDED = "output_exceeded"
    ERROR = "error"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class FlatpakRecord:
    scope: FlatpakScope
    ref: str
    kind: FlatpakKind
    application_id: str
    arch: str
    branch: str
    origin: str
    candidate_ref: str | None
    candidate_origin: str | None
    item: NormalizedItem


@dataclass(frozen=True, slots=True)
class FlatpakScopeResult:
    scope: FlatpakScope
    status: FlatpakScopeStatus
    records: tuple[FlatpakRecord, ...]
    diagnostic: str | None


@dataclass(frozen=True, slots=True)
class FlatpakResult:
    scopes: tuple[FlatpakScopeResult, FlatpakScopeResult]


@dataclass(frozen=True, slots=True)
class _ScopeCommands:
    scope: FlatpakScope
    apps: CommandName
    runtimes: CommandName
    updates: CommandName


@dataclass(frozen=True, slots=True)
class _CommandText:
    stdout: bytes


@dataclass(frozen=True, slots=True)
class _CommandFailure:
    status: FlatpakScopeStatus
    diagnostic: str


@dataclass(frozen=True, slots=True)
class _InventorySuccess:
    rows: tuple[FlatpakInventoryRow, ...]


type FlatpakRunner = Callable[[CommandName], CommandResult]
type _CommandOutcome = _CommandText | _CommandFailure
type _InventoryOutcome = _InventorySuccess | _CommandFailure

_SCOPES: Final[tuple[_ScopeCommands, _ScopeCommands]] = (
    _ScopeCommands(
        FlatpakScope.USER,
        CommandName.FLATPAK_USER_APP_LIST,
        CommandName.FLATPAK_USER_RUNTIME_LIST,
        CommandName.FLATPAK_USER_UPDATES,
    ),
    _ScopeCommands(
        FlatpakScope.SYSTEM,
        CommandName.FLATPAK_SYSTEM_APP_LIST,
        CommandName.FLATPAK_SYSTEM_RUNTIME_LIST,
        CommandName.FLATPAK_SYSTEM_UPDATES,
    ),
)
_DIAGNOSTIC_LIMIT: Final[int] = 512


def collect_flatpak(run: FlatpakRunner = run_command) -> FlatpakResult:
    user, system = _SCOPES
    return FlatpakResult((_collect_scope(user, run), _collect_scope(system, run)))


def _collect_scope(commands: _ScopeCommands, run: FlatpakRunner) -> FlatpakScopeResult:
    apps = _inventory_outcome(run(commands.apps), FlatpakKind.APP)
    runtimes = _inventory_outcome(run(commands.runtimes), FlatpakKind.RUNTIME)
    match apps:
        case _CommandFailure() as failure:
            return _inventory_failure(commands.scope, failure, runtimes)
        case _InventorySuccess(rows=app_rows):
            match runtimes:
                case _CommandFailure() as failure:
                    return _inventory_failure(commands.scope, failure, apps)
                case _InventorySuccess(rows=runtime_rows):
                    records = _records(commands.scope, app_rows + runtime_rows)
                    if not records:
                        return FlatpakScopeResult(
                            commands.scope, FlatpakScopeStatus.NOT_APPLICABLE, (), None
                        )
                    return _collect_updates(commands, records, run)
            assert_never(runtimes)
    assert_never(apps)


def _inventory_outcome(result: CommandResult, kind: FlatpakKind) -> _InventoryOutcome:
    outcome = _command_outcome(result)
    match outcome:
        case _CommandFailure():
            return outcome
        case _CommandText(stdout=stdout):
            parsed = parse_inventory(stdout, kind)
            match parsed:
                case FlatpakParseFailure(diagnostic=diagnostic):
                    return _CommandFailure(FlatpakScopeStatus.INVALID, diagnostic)
                case tuple() as rows:
                    return _InventorySuccess(rows)
            assert_never(parsed)
    assert_never(outcome)


def _inventory_failure(
    scope: FlatpakScope,
    failure: _CommandFailure,
    other: _InventoryOutcome,
) -> FlatpakScopeResult:
    match other:
        case _CommandFailure():
            return FlatpakScopeResult(scope, failure.status, (), failure.diagnostic)
        case _InventorySuccess(rows=rows):
            return FlatpakScopeResult(
                scope, failure.status, _records(scope, rows), failure.diagnostic
            )
    assert_never(other)


def _collect_updates(
    commands: _ScopeCommands, records: tuple[FlatpakRecord, ...], run: FlatpakRunner
) -> FlatpakScopeResult:
    outcome = _command_outcome(run(commands.updates))
    match outcome:
        case _CommandFailure(status=status, diagnostic=diagnostic):
            return FlatpakScopeResult(commands.scope, status, records, diagnostic)
        case _CommandText(stdout=stdout):
            parsed = parse_updates(stdout)
            match parsed:
                case FlatpakParseFailure(diagnostic=diagnostic):
                    return FlatpakScopeResult(
                        commands.scope, FlatpakScopeStatus.INVALID, records, diagnostic
                    )
                case tuple() as updates:
                    return _reconcile_updates(commands.scope, records, updates)
            assert_never(parsed)
    assert_never(outcome)


def _reconcile_updates(
    scope: FlatpakScope,
    records: tuple[FlatpakRecord, ...],
    updates: tuple[FlatpakUpdate, ...],
) -> FlatpakScopeResult:
    record_refs = {record.ref for record in records}
    for update in updates:
        if update.ref not in record_refs:
            return FlatpakScopeResult(
                scope,
                FlatpakScopeStatus.INVALID,
                records,
                f"Flatpak updates contains unmatched ref at row {update.row_number}",
            )
    updates_by_ref = {update.ref: update for update in updates}
    joined = tuple(
        _with_candidate(record, updates_by_ref.get(record.ref)) for record in records
    )
    return FlatpakScopeResult(scope, FlatpakScopeStatus.OK, joined, None)


def _command_outcome(result: CommandResult) -> _CommandOutcome:
    match result:
        case CommandSucceeded(stdout=stdout):
            return _CommandText(stdout)
        case CommandMissing(diagnostic=diagnostic):
            return _CommandFailure(
                FlatpakScopeStatus.MISSING_DEPENDENCY, diagnostic[:_DIAGNOSTIC_LIMIT]
            )
        case CommandTimedOut():
            return _CommandFailure(
                FlatpakScopeStatus.TIMEOUT, "Flatpak command timed out"
            )
        case CommandOutputExceeded(stream=stream):
            return _CommandFailure(
                FlatpakScopeStatus.OUTPUT_EXCEEDED,
                f"Flatpak {stream} output exceeded its configured limit",
            )
        case CommandExited(returncode=returncode):
            return _CommandFailure(
                FlatpakScopeStatus.ERROR,
                f"Flatpak command exited with status {returncode}",
            )
        case CommandRejected(diagnostic=diagnostic):
            return _CommandFailure(
                FlatpakScopeStatus.ERROR, diagnostic[:_DIAGNOSTIC_LIMIT]
            )
    assert_never(result)


def _records(
    scope: FlatpakScope, rows: tuple[FlatpakInventoryRow, ...]
) -> tuple[FlatpakRecord, ...]:
    return tuple(
        FlatpakRecord(
            scope,
            row.ref,
            row.kind,
            row.application_id,
            row.arch,
            row.branch,
            row.origin,
            None,
            None,
            NormalizedItem(
                ItemId(f"flatpak:{scope}:{row.ref}"),
                ItemSource.FLATPAK,
                row.application_id,
                row.installed,
                None,
                WatchMode.OFF,
                False,
                Provenance.LIVE,
            ),
        )
        for row in rows
    )


def _with_candidate(
    record: FlatpakRecord, candidate: FlatpakUpdate | None
) -> FlatpakRecord:
    if candidate is None:
        return record
    return replace(
        record,
        candidate_ref=candidate.ref,
        candidate_origin=candidate.origin,
        item=replace(record.item, candidate=candidate.version),
    )
