from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique


@unique
class FlatpakKind(StrEnum):
    APP = "app"
    RUNTIME = "runtime"


@dataclass(frozen=True, slots=True)
class FlatpakInventoryRow:
    ref: str
    kind: FlatpakKind
    application_id: str
    arch: str
    branch: str
    installed: str | None
    origin: str


@dataclass(frozen=True, slots=True)
class FlatpakParseFailure:
    diagnostic: str


@dataclass(frozen=True, slots=True)
class FlatpakUpdate:
    ref: str
    version: str | None
    origin: str
    row_number: int


type InventoryParseResult = tuple[FlatpakInventoryRow, ...] | FlatpakParseFailure
type UpdatesParseResult = tuple[FlatpakUpdate, ...] | FlatpakParseFailure


def parse_inventory(stdout: bytes, kind: FlatpakKind) -> InventoryParseResult:
    try:
        decoded = stdout.decode("utf-8")
    except UnicodeDecodeError:
        return FlatpakParseFailure("Flatpak inventory output is not valid UTF-8")
    inventory: list[FlatpakInventoryRow] = []
    seen_refs: set[str] = set()
    for row_number, row in enumerate(decoded.splitlines(), start=1):
        columns = row.split("\t")
        if len(columns) != 5:
            return FlatpakParseFailure(
                f"Flatpak inventory row {row_number} has {len(columns)} columns; expected 5"
            )
        application_id, arch, branch, installed, origin = columns
        if not all(_valid_component(value) for value in (application_id, arch, branch)):
            return FlatpakParseFailure(
                f"Flatpak inventory row {row_number} has an invalid component"
            )
        ref = f"{kind}/{application_id}/{arch}/{branch}"
        if ref in seen_refs:
            return FlatpakParseFailure(
                f"Flatpak inventory contains duplicate ref at row {row_number}"
            )
        seen_refs.add(ref)
        inventory.append(
            FlatpakInventoryRow(
                ref, kind, application_id, arch, branch, installed or None, origin
            )
        )
    return tuple(inventory)


def parse_updates(stdout: bytes) -> UpdatesParseResult:
    try:
        decoded = stdout.decode("utf-8")
    except UnicodeDecodeError:
        return FlatpakParseFailure("Flatpak updates output is not valid UTF-8")
    updates: list[FlatpakUpdate] = []
    seen_refs: set[str] = set()
    for row_number, row in enumerate(decoded.splitlines(), start=1):
        columns = row.split("\t")
        if len(columns) != 3:
            return FlatpakParseFailure(
                f"Flatpak updates row {row_number} has {len(columns)} columns; expected 3"
            )
        ref, version, origin = columns
        if not _valid_ref(ref):
            return FlatpakParseFailure(
                f"Flatpak updates row {row_number} has an invalid ref"
            )
        if ref in seen_refs:
            return FlatpakParseFailure(
                f"Flatpak updates contains duplicate ref at row {row_number}"
            )
        seen_refs.add(ref)
        updates.append(FlatpakUpdate(ref, version or None, origin, row_number))
    return tuple(updates)


def _valid_ref(ref: str) -> bool:
    parts = ref.split("/")
    return (
        len(parts) == 4
        and parts[0] in FlatpakKind
        and all(_valid_component(part) for part in parts)
    )


def _valid_component(value: str) -> bool:
    return bool(value) and value.isprintable() and "/" not in value
