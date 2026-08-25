from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum, unique

from opatchy_helper.adapters.omarchy import OMARCHY_DUPLICATE_FILTER
from opatchy_helper.models import (
    ItemId,
    ItemSource,
    NormalizedItem,
    Provenance,
    WatchMode,
)
from opatchy_helper.runner_types import (
    CommandExited,
    CommandMissing,
    CommandName,
    CommandOutputExceeded,
    CommandRejected,
    CommandResult,
    CommandSucceeded,
    CommandTimedOut,
)


@unique
class ArchFailure(StrEnum):
    COMMAND_EXITED = "command_exited"
    COMMAND_MISSING = "command_missing"
    COMMAND_OUTPUT_EXCEEDED = "command_output_exceeded"
    COMMAND_REJECTED = "command_rejected"
    COMMAND_TIMED_OUT = "command_timed_out"
    DUPLICATE_PACKAGE = "duplicate_package"
    INVALID_VERCMP_OUTPUT = "invalid_vercmp_output"
    MALFORMED_ROW = "malformed_row"
    MISSING_NATIVE_PACKAGE = "missing_native_package"
    UNEXPECTED_COMMAND_RESULT = "unexpected_command_result"


@dataclass(frozen=True, slots=True)
class PackageRecord:
    name: str
    installed: str


@dataclass(frozen=True, slots=True)
class UpdateRecord:
    name: str
    installed: str
    candidate: str


@dataclass(frozen=True, slots=True)
class ArchUpdates:
    items: tuple[NormalizedItem, ...]


@dataclass(frozen=True, slots=True)
class ForeignInventory:
    records: tuple[PackageRecord, ...]


@dataclass(frozen=True, slots=True)
class VersionComparison:
    sign: int


@dataclass(frozen=True, slots=True)
class ArchDegraded:
    failure: ArchFailure
    detail: str


type CommandRunner = Callable[[CommandName, tuple[str, ...]], CommandResult]
type ArchUpdatesResult = ArchUpdates | ArchDegraded
type ForeignInventoryResult = ForeignInventory | ArchDegraded
type VersionComparisonResult = VersionComparison | ArchDegraded


def collect_official_updates(command_runner: CommandRunner) -> ArchUpdatesResult:
    """Collect native Arch updates joined to the official local inventory."""
    inventory_result = command_runner(CommandName.PACMAN_NATIVE, ())
    match inventory_result:
        case CommandSucceeded(stdout=stdout):
            inventory = _parse_package_rows(stdout)
        case _:
            return _command_degraded(inventory_result, "pacman -Qn")
    match inventory:
        case ArchDegraded():
            return inventory
        case tuple():
            inventory_by_name = {record.name: record for record in inventory}

    updates_result = command_runner(CommandName.CHECKUPDATES, ())
    match updates_result:
        case CommandSucceeded(stdout=stdout):
            updates = _parse_update_rows(stdout)
        case CommandExited(returncode=2):
            return ArchUpdates(())
        case _:
            return _command_degraded(updates_result, "checkupdates")
    match updates:
        case ArchDegraded():
            return updates
        case ():
            return ArchDegraded(ArchFailure.MALFORMED_ROW, "empty checkupdates output")
        case tuple():
            return _join_official_updates(inventory_by_name, updates)


def collect_foreign_inventory(command_runner: CommandRunner) -> ForeignInventoryResult:
    """Collect the separate pacman -Qm inventory required by the AUR adapter."""
    result = command_runner(CommandName.PACMAN_FOREIGN, ())
    match result:
        case CommandSucceeded(stdout=stdout):
            records = _parse_package_rows(stdout)
        case _:
            return _command_degraded(result, "pacman -Qm")
    match records:
        case ArchDegraded():
            return records
        case tuple():
            return ForeignInventory(records)


def compare_versions(
    command_runner: CommandRunner, left: str, right: str
) -> VersionComparisonResult:
    """Return only the native vercmp sign for two opaque Arch version strings."""
    result = command_runner(CommandName.VERCMP, (left, right))
    match result:
        case CommandSucceeded(stdout=stdout):
            try:
                output = stdout.decode("utf-8").strip()
            except UnicodeDecodeError:
                return ArchDegraded(
                    ArchFailure.INVALID_VERCMP_OUTPUT, "non-UTF-8 output"
                )
            match output:
                case "-1":
                    return VersionComparison(-1)
                case "0":
                    return VersionComparison(0)
                case "1":
                    return VersionComparison(1)
                case invalid:
                    return ArchDegraded(ArchFailure.INVALID_VERCMP_OUTPUT, invalid)
        case _:
            return _command_degraded(result, "vercmp")


def _parse_package_rows(output: bytes) -> tuple[PackageRecord, ...] | ArchDegraded:
    try:
        lines = output.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return ArchDegraded(ArchFailure.MALFORMED_ROW, "non-UTF-8 output")
    records: list[PackageRecord] = []
    names: set[str] = set()
    for line in lines:
        fields = line.split()
        if len(fields) != 2:
            return ArchDegraded(ArchFailure.MALFORMED_ROW, line)
        name, installed = fields
        if name in names:
            return ArchDegraded(ArchFailure.DUPLICATE_PACKAGE, name)
        names.add(name)
        records.append(PackageRecord(name, installed))
    return tuple(records)


def _parse_update_rows(output: bytes) -> tuple[UpdateRecord, ...] | ArchDegraded:
    try:
        lines = output.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return ArchDegraded(ArchFailure.MALFORMED_ROW, "non-UTF-8 output")
    records: list[UpdateRecord] = []
    names: set[str] = set()
    for line in lines:
        fields = line.split(" -> ")
        if len(fields) != 2:
            return ArchDegraded(ArchFailure.MALFORMED_ROW, line)
        installed_fields = fields[0].split()
        candidate_fields = fields[1].split()
        if len(installed_fields) != 2 or len(candidate_fields) != 1:
            return ArchDegraded(ArchFailure.MALFORMED_ROW, line)
        name, installed = installed_fields
        candidate = candidate_fields[0]
        if name in names:
            return ArchDegraded(ArchFailure.DUPLICATE_PACKAGE, name)
        names.add(name)
        records.append(UpdateRecord(name, installed, candidate))
    return tuple(records)


def _join_official_updates(
    inventory_by_name: dict[str, PackageRecord], updates: tuple[UpdateRecord, ...]
) -> ArchUpdatesResult:
    items: list[NormalizedItem] = []
    for update in updates:
        if update.name not in inventory_by_name:
            return ArchDegraded(ArchFailure.MISSING_NATIVE_PACKAGE, update.name)
        if update.name not in OMARCHY_DUPLICATE_FILTER:
            items.append(
                NormalizedItem(
                    ItemId(f"arch:{update.name}"),
                    ItemSource.ARCH,
                    update.name,
                    update.installed,
                    update.candidate,
                    WatchMode.OFF,
                    True,
                    Provenance.LIVE,
                )
            )
    return ArchUpdates(tuple(items))


def _command_degraded(result: CommandResult, command: str) -> ArchDegraded:
    match result:
        case CommandExited(returncode=returncode):
            return ArchDegraded(
                ArchFailure.COMMAND_EXITED, f"{command}: exit {returncode}"
            )
        case CommandMissing(diagnostic=diagnostic):
            return ArchDegraded(ArchFailure.COMMAND_MISSING, diagnostic)
        case CommandOutputExceeded(stream=stream):
            return ArchDegraded(
                ArchFailure.COMMAND_OUTPUT_EXCEEDED, f"{command}: {stream}"
            )
        case CommandRejected(diagnostic=diagnostic):
            return ArchDegraded(ArchFailure.COMMAND_REJECTED, diagnostic)
        case CommandTimedOut():
            return ArchDegraded(ArchFailure.COMMAND_TIMED_OUT, command)
        case CommandSucceeded():
            return ArchDegraded(ArchFailure.UNEXPECTED_COMMAND_RESULT, command)
