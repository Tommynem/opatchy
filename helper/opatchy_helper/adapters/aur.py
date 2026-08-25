from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Protocol, assert_never

from opatchy_helper.adapters.arch import (
    ArchDegraded,
    ArchFailure,
    ForeignInventory,
    PackageRecord,
    collect_foreign_inventory,
)
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
class AurHelper(StrEnum):
    YAY = "yay"
    PARU = "paru"


class CommandRunner(Protocol):
    def __call__(
        self, name: CommandName, arguments: tuple[str, ...], /
    ) -> CommandResult: ...


@dataclass(frozen=True, slots=True)
class AurCollected:
    helper: AurHelper
    items: tuple[NormalizedItem, ...]


@dataclass(frozen=True, slots=True)
class AurNotApplicable:
    pass


@dataclass(frozen=True, slots=True)
class AurMissingDependency:
    pass


@dataclass(frozen=True, slots=True)
class AurInvalid:
    diagnostic: str


@dataclass(frozen=True, slots=True)
class AurTimedOut:
    helper: AurHelper


@dataclass(frozen=True, slots=True)
class AurOutputExceeded:
    helper: AurHelper
    stream: str


@dataclass(frozen=True, slots=True)
class AurCommandFailed:
    helper: AurHelper
    returncode: int


@dataclass(frozen=True, slots=True)
class AurCommandRejected:
    helper: AurHelper
    diagnostic: str


@dataclass(frozen=True, slots=True)
class AurForeignInventoryDegraded:
    failure: ArchFailure
    detail: str


type AurResult = (
    AurCollected
    | AurNotApplicable
    | AurMissingDependency
    | AurInvalid
    | AurTimedOut
    | AurOutputExceeded
    | AurCommandFailed
    | AurCommandRejected
    | AurForeignInventoryDegraded
)


def collect_aur_updates(run: CommandRunner) -> AurResult:
    """Collect AUR update evidence only for the trusted foreign-package inventory."""
    inventory_result = collect_foreign_inventory(run)
    match inventory_result:
        case ForeignInventory(records=()):
            return AurNotApplicable()
        case ForeignInventory(records=records):
            return _collect_with_yay_or_paru(run, records)
        case ArchDegraded(failure=failure, detail=detail):
            return AurForeignInventoryDegraded(failure, detail)
    assert_never(inventory_result)


def _collect_with_yay_or_paru(
    run: CommandRunner, inventory: tuple[PackageRecord, ...]
) -> AurResult:
    yay_result = run(CommandName.YAY_UPDATES, ())
    match yay_result:
        case CommandMissing():
            return _collect_from_paru(run, inventory)
        case _:
            return _collect_from_result(AurHelper.YAY, yay_result, inventory)


def _collect_from_paru(
    run: CommandRunner, inventory: tuple[PackageRecord, ...]
) -> AurResult:
    return _collect_from_result(
        AurHelper.PARU, run(CommandName.PARU_UPDATES, ()), inventory
    )


def _collect_from_result(
    helper: AurHelper, result: CommandResult, inventory: tuple[PackageRecord, ...]
) -> AurResult:
    match result:
        case CommandSucceeded(stdout=stdout):
            return _parse_helper_output(helper, stdout, inventory)
        case CommandMissing():
            return AurMissingDependency()
        case CommandTimedOut():
            return AurTimedOut(helper)
        case CommandOutputExceeded(stream=stream):
            return AurOutputExceeded(helper, stream)
        case CommandExited(returncode=returncode):
            return AurCommandFailed(helper, returncode)
        case CommandRejected(diagnostic=diagnostic):
            return AurCommandRejected(helper, diagnostic)
    assert_never(result)


def _parse_helper_output(
    helper: AurHelper, output: bytes, inventory: tuple[PackageRecord, ...]
) -> AurCollected | AurInvalid:
    try:
        lines = output.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return AurInvalid("non-UTF-8 output")
    inventory_by_name = {record.name: record for record in inventory}
    items: list[NormalizedItem] = []
    names: set[str] = set()
    for line in lines:
        fields = line.split(" -> ")
        if len(fields) != 2:
            return AurInvalid(line)
        installed_fields = fields[0].split()
        candidate_fields = fields[1].split()
        if len(installed_fields) != 2 or len(candidate_fields) != 1:
            return AurInvalid(line)
        name, installed = installed_fields
        candidate = candidate_fields[0]
        if name in names:
            return AurInvalid(f"duplicate package: {name}")
        if name not in inventory_by_name:
            return AurInvalid(f"missing foreign package: {name}")
        names.add(name)
        items.append(
            NormalizedItem(
                ItemId(f"aur:{name}"),
                ItemSource.AUR,
                name,
                installed,
                candidate,
                WatchMode.OFF,
                True,
                Provenance.LIVE,
            )
        )
    return AurCollected(helper, tuple(items))
