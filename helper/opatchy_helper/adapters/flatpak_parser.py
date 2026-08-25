from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FlatpakInventoryRow:
    ref: str
    kind: str
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


type InventoryParseResult = tuple[FlatpakInventoryRow, ...] | FlatpakParseFailure
type UpdatesParseResult = tuple[FlatpakUpdate, ...] | FlatpakParseFailure


def parse_inventory(stdout: bytes) -> InventoryParseResult:
    try:
        rows = stdout.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return FlatpakParseFailure("Flatpak inventory output is not valid UTF-8")

    inventory: list[FlatpakInventoryRow] = []
    seen_refs: set[str] = set()
    for row_number, row in enumerate(rows, start=1):
        columns = row.split("\t")
        if len(columns) != 4:
            return FlatpakParseFailure(
                f"Flatpak inventory row {row_number} has {len(columns)} columns; expected 4"
            )
        ref, _application, installed, origin = columns
        parsed_ref = _parse_ref(ref)
        if parsed_ref is None:
            return FlatpakParseFailure(
                f"Flatpak inventory row {row_number} has an invalid ref"
            )
        kind, application_id, arch, branch = parsed_ref
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
        rows = stdout.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return FlatpakParseFailure("Flatpak updates output is not valid UTF-8")

    updates: list[FlatpakUpdate] = []
    for row_number, row in enumerate(rows, start=1):
        columns = row.split("\t")
        if len(columns) != 3:
            return FlatpakParseFailure(
                f"Flatpak updates row {row_number} has {len(columns)} columns; expected 3"
            )
        ref, version, _origin = columns
        if _parse_ref(ref) is None:
            return FlatpakParseFailure(
                f"Flatpak updates row {row_number} has an invalid ref"
            )
        updates.append(FlatpakUpdate(ref, version or None))
    return tuple(updates)


def _parse_ref(ref: str) -> tuple[str, str, str, str] | None:
    parts = ref.split("/")
    if len(parts) != 4 or any(not part or not part.isprintable() for part in parts):
        return None
    kind, application_id, arch, branch = parts
    if kind not in {"app", "runtime"}:
        return None
    return kind, application_id, arch, branch
