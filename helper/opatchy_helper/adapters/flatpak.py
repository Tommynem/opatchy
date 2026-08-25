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
    kind: str
    application_id: str
    arch: str
    branch: str
    origin: str
    candidate_ref: str | None
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
    inventory: CommandName
    updates: CommandName


@dataclass(frozen=True, slots=True)
class _CommandText:
    stdout: bytes


@dataclass(frozen=True, slots=True)
class _CommandFailure:
    status: FlatpakScopeStatus
    diagnostic: str


type FlatpakRunner = Callable[[CommandName], CommandResult]
type _CommandOutcome = _CommandText | _CommandFailure

_SCOPES: Final[tuple[_ScopeCommands, _ScopeCommands]] = (
    _ScopeCommands(
        FlatpakScope.USER,
        CommandName.FLATPAK_USER_LIST,
        CommandName.FLATPAK_USER_UPDATES,
    ),
    _ScopeCommands(
        FlatpakScope.SYSTEM,
        CommandName.FLATPAK_SYSTEM_LIST,
        CommandName.FLATPAK_SYSTEM_UPDATES,
    ),
)
_DIAGNOSTIC_LIMIT: Final[int] = 512


def collect_flatpak(run: FlatpakRunner = run_command) -> FlatpakResult:
    user_commands, system_commands = _SCOPES
    return FlatpakResult(
        (_collect_scope(user_commands, run), _collect_scope(system_commands, run))
    )


def _collect_scope(commands: _ScopeCommands, run: FlatpakRunner) -> FlatpakScopeResult:
    inventory_command = _command_outcome(run(commands.inventory))
    match inventory_command:
        case _CommandFailure(status=status, diagnostic=diagnostic):
            return FlatpakScopeResult(commands.scope, status, (), diagnostic)
        case _CommandText(stdout=stdout):
            return _collect_inventory(commands, stdout, run)
    assert_never(inventory_command)


def _collect_inventory(
    commands: _ScopeCommands, stdout: bytes, run: FlatpakRunner
) -> FlatpakScopeResult:
    inventory = parse_inventory(stdout)
    match inventory:
        case FlatpakParseFailure(diagnostic=diagnostic):
            return FlatpakScopeResult(
                commands.scope, FlatpakScopeStatus.INVALID, (), diagnostic
            )
        case ():
            return FlatpakScopeResult(
                commands.scope, FlatpakScopeStatus.NOT_APPLICABLE, (), None
            )
        case tuple() as inventory:
            return _collect_updates(commands, _records(commands.scope, inventory), run)
    assert_never(inventory)


def _collect_updates(
    commands: _ScopeCommands,
    records: tuple[FlatpakRecord, ...],
    run: FlatpakRunner,
) -> FlatpakScopeResult:
    updates_command = _command_outcome(run(commands.updates))
    match updates_command:
        case _CommandFailure(status=status, diagnostic=diagnostic):
            return FlatpakScopeResult(commands.scope, status, records, diagnostic)
        case _CommandText(stdout=stdout):
            return _join_updates(commands, records, stdout)
    assert_never(updates_command)


def _join_updates(
    commands: _ScopeCommands, records: tuple[FlatpakRecord, ...], stdout: bytes
) -> FlatpakScopeResult:
    updates = parse_updates(stdout)
    match updates:
        case FlatpakParseFailure(diagnostic=diagnostic):
            return FlatpakScopeResult(
                commands.scope, FlatpakScopeStatus.INVALID, records, diagnostic
            )
        case tuple() as candidates:
            candidates_by_ref = {candidate.ref: candidate for candidate in candidates}
            joined = tuple(
                _with_candidate(record, candidates_by_ref.get(record.ref))
                for record in records
            )
            return FlatpakScopeResult(
                commands.scope, FlatpakScopeStatus.OK, joined, None
            )
    assert_never(updates)


def _command_outcome(result: CommandResult) -> _CommandOutcome:
    match result:
        case CommandSucceeded(stdout=stdout):
            return _CommandText(stdout)
        case CommandMissing(diagnostic=diagnostic):
            return _CommandFailure(
                FlatpakScopeStatus.MISSING_DEPENDENCY, _bound_diagnostic(diagnostic)
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
                FlatpakScopeStatus.ERROR, _bound_diagnostic(diagnostic)
            )
    assert_never(result)


def _records(
    scope: FlatpakScope, inventory: tuple[FlatpakInventoryRow, ...]
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
        for row in inventory
    )


def _with_candidate(
    record: FlatpakRecord, candidate: FlatpakUpdate | None
) -> FlatpakRecord:
    if candidate is None:
        return record
    if candidate.version is None:
        return replace(record, candidate_ref=candidate.ref)
    return replace(
        record,
        candidate_ref=candidate.ref,
        item=replace(record.item, candidate=candidate.version),
    )


def _bound_diagnostic(value: str) -> str:
    return value[:_DIAGNOSTIC_LIMIT]
