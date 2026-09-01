from dataclasses import dataclass
from typing import Final, assert_never, override

from .models import ItemId, ItemSource, Severity, WatchMode
from .notification_types import NotificationSettings
from .storage_types import SecurityFixCondition, StateCorruptError
from .storage_watches import security_fix_condition

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
    notification_settings: NotificationSettings = NotificationSettings()
    enable_cisa_kev: bool = True


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
    condition: SecurityFixCondition | None = None


type CliCommand = ScanCommand | SnapshotCommand | InventoryCommand | SetStarCommand


def parse_command(arguments: tuple[str, ...]) -> CliCommand:
    match arguments:
        case ("scan", *_):
            return _scan_command(arguments)
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
        case (
            "set-star",
            "--item-id",
            item_id,
            "--mode",
            "temporary",
            "--security-advisory",
            advisory_id,
            "--fixed-version",
            fixed_version,
            "--cve-ids",
            cve_ids,
        ):
            return SetStarCommand(
                _arch_item_id(item_id),
                WatchMode.TEMPORARY,
                _security_condition(advisory_id, cve_ids, fixed_version),
            )
        case _:
            raise CliUsageError("unsupported helper command or arguments")


def _scan_command(arguments: tuple[str, ...]) -> ScanCommand:
    force = arguments[1:2] == ("--force",)
    settings = arguments[2:] if force else arguments[1:]
    if not settings:
        return ScanCommand(force)
    match settings:
        case (
            "--notify-permanent",
            notify_permanent,
            "--notify-security",
            notify_security,
            "--security-minimum-severity",
            minimum_severity,
        ):
            return ScanCommand(
                force,
                _notification_settings(
                    notify_permanent, notify_security, minimum_severity
                ),
            )
        case (
            "--notify-permanent",
            notify_permanent,
            "--notify-security",
            notify_security,
            "--security-minimum-severity",
            minimum_severity,
            "--enable-cisa-kev",
            enable_cisa_kev,
        ):
            return ScanCommand(
                force,
                _notification_settings(
                    notify_permanent, notify_security, minimum_severity
                ),
                _boolean(enable_cisa_kev),
            )
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


def _notification_settings(
    notify_permanent: str, notify_security: str, minimum_severity: str
) -> NotificationSettings:
    return NotificationSettings(
        _boolean(notify_permanent),
        _boolean(notify_security),
        _notification_severity(minimum_severity),
    )


def _boolean(value: str) -> bool:
    match value:
        case "true":
            return True
        case "false":
            return False
        case _:
            raise CliUsageError("notification setting is invalid")


def _notification_severity(value: str) -> Severity:
    match value:
        case "high":
            return Severity.HIGH
        case "critical":
            return Severity.CRITICAL
        case _:
            raise CliUsageError("notification severity is invalid")


def _arch_item_id(value: str) -> ItemId:
    item_id = _item_id(value)
    if not str(item_id).startswith("arch:"):
        raise CliUsageError("conditional watch item ID must be canonical Arch")
    return item_id


def _security_condition(
    advisory_id: str, cve_ids: str, fixed_version: str
) -> SecurityFixCondition:
    values = tuple(cve_ids.split(","))
    try:
        return security_fix_condition(advisory_id, values, fixed_version)
    except StateCorruptError as error:
        raise CliUsageError("conditional watch evidence is invalid") from error
