from dataclasses import dataclass
from typing import Final, assert_never, override

from .models import ItemId, ItemSource, WatchMode

MAX_OFFSET: Final = 100_000
MAX_QUERY_LENGTH: Final = 128


@dataclass(frozen=True, slots=True)
class CliUsageError(Exception):
    message: str

    @override
    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class CliUnavailableError(Exception):
    message: str

    @override
    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class ScanCommand:
    force: bool


@dataclass(frozen=True, slots=True)
class SnapshotCommand:
    pass


@dataclass(frozen=True, slots=True)
class InventoryCommand:
    source: ItemSource
    query: str
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class SetStarCommand:
    item_id: ItemId
    mode: WatchMode


type CliCommand = ScanCommand | SnapshotCommand | InventoryCommand | SetStarCommand


def parse_command(arguments: tuple[str, ...]) -> CliCommand:
    match arguments:
        case ("scan",):
            return ScanCommand(False)
        case ("scan", "--force"):
            return ScanCommand(True)
        case ("snapshot",):
            return SnapshotCommand()
        case (
            "inventory",
            "--source",
            source,
            "--query",
            query,
            "--limit",
            limit,
            "--offset",
            offset,
        ):
            return InventoryCommand(
                _inventory_source(source), _query(query), _limit(limit), _offset(offset)
            )
        case ("set-star", "--item-id", item_id, "--mode", mode):
            return SetStarCommand(_item_id(item_id), _watch_mode(mode))
        case _:
            raise CliUsageError("unsupported helper command or arguments")


def _inventory_source(value: str) -> ItemSource:
    try:
        source = ItemSource(value)
    except ValueError as error:
        raise CliUsageError("inventory source is unsupported") from error
    match source:
        case ItemSource.ARCH | ItemSource.AUR | ItemSource.FLATPAK | ItemSource.MISE:
            return source
        case ItemSource.OMARCHY:
            raise CliUsageError("inventory source is unsupported")
    assert_never(source)


def _query(value: str) -> str:
    if len(value) > MAX_QUERY_LENGTH:
        raise CliUsageError("inventory query is invalid")
    return value


def _limit(value: str) -> int:
    parsed = _decimal(value, "inventory pagination is invalid")
    if parsed < 1 or parsed > 100:
        raise CliUsageError("inventory pagination is invalid")
    return parsed


def _offset(value: str) -> int:
    parsed = _decimal(value, "inventory pagination is invalid")
    if parsed > MAX_OFFSET:
        raise CliUsageError("inventory pagination is invalid")
    return parsed


def _decimal(value: str, message: str) -> int:
    if not value.isascii() or not value.isdecimal() or len(value) > 6:
        raise CliUsageError(message)
    return int(value)


def _item_id(value: str) -> ItemId:
    if not value or len(value) > 128:
        raise CliUsageError("item ID is invalid")
    return ItemId(value)


def _watch_mode(value: str) -> WatchMode:
    try:
        return WatchMode(value)
    except ValueError as error:
        raise CliUsageError("watch mode is invalid") from error
