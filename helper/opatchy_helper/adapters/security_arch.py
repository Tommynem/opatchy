"""Strict parsers for the documented arch-audit and Tracker feed shapes."""

import re
from dataclasses import dataclass
from typing import Final

from ..json_value import JsonValue, decode_json
from ..models import ArchStatus, ProtocolError, Severity

_MAX_RECORDS = 4_096
_MAX_PACKAGES = 128
_MAX_ISSUES = 128
_MAX_IDENTIFIER = 60
_MAX_STRING = 128
_AVG: Final = re.compile(r"AVG-[0-9]+")
_PRIMARY_REQUIRED = frozenset(
    {"name", "packages", "status", "type", "severity", "fixed", "issues"}
)
_TRACKER_REQUIRED = _PRIMARY_REQUIRED | frozenset({"affected", "ticket", "advisories"})


@dataclass(frozen=True, slots=True)
class ArchAdvisory:
    name: str
    packages: tuple[str, ...]
    status: ArchStatus
    advisory_type: str
    severity: Severity
    fixed: str | None
    issues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArchFeedInvalid:
    diagnostic: str


@dataclass(frozen=True, slots=True)
class _DecodedFeed:
    value: JsonValue


def parse_arch_audit(raw: bytes) -> tuple[ArchAdvisory, ...] | ArchFeedInvalid:
    """Parse an arch-audit JSON array without accepting Tracker-only statuses."""
    decoded = _decode(raw)
    match decoded:
        case ArchFeedInvalid():
            return decoded
        case _DecodedFeed(value=value):
            return _parse_records(value, _PRIMARY_REQUIRED, False)


def parse_tracker(raw: bytes) -> tuple[ArchAdvisory, ...] | ArchFeedInvalid:
    """Parse the Arch Security Tracker all.json array with complete core fields."""
    decoded = _decode(raw)
    match decoded:
        case ArchFeedInvalid():
            return decoded
        case _DecodedFeed(value=value):
            return _parse_records(value, _TRACKER_REQUIRED, True)


def _decode(raw: bytes) -> _DecodedFeed | ArchFeedInvalid:
    try:
        return _DecodedFeed(decode_json(raw.decode("utf-8")))
    except UnicodeDecodeError:
        return ArchFeedInvalid("feed is not UTF-8")
    except ProtocolError:
        return ArchFeedInvalid("feed is not valid JSON")


def _parse_records(
    value: JsonValue, required: frozenset[str], tracker: bool
) -> tuple[ArchAdvisory, ...] | ArchFeedInvalid:
    if type(value) is not list or len(value) > _MAX_RECORDS:
        return ArchFeedInvalid("feed root is not a bounded array")
    records: list[ArchAdvisory] = []
    names: set[str] = set()
    for entry in value:
        record = _parse_record(entry, required, tracker)
        match record:
            case ArchFeedInvalid():
                return record
            case ArchAdvisory():
                pass
        if record.name in names:
            return ArchFeedInvalid("feed contains duplicate advisory names")
        names.add(record.name)
        records.append(record)
    return tuple(records)


def _parse_record(
    value: JsonValue, required: frozenset[str], tracker: bool
) -> ArchAdvisory | ArchFeedInvalid:
    if type(value) is not dict or not required.issubset(value):
        return ArchFeedInvalid("feed record omits a required field")
    name = _avg_identifier(value["name"])
    packages = _identifiers(value["packages"], _MAX_PACKAGES)
    advisory_type = _string(value["type"])
    issues = _identifiers(value["issues"], _MAX_ISSUES)
    fixed = _optional_string(value["fixed"])
    if name is None or packages is None or advisory_type is None or issues is None:
        return ArchFeedInvalid("feed record has an invalid field type")
    match fixed:
        case ArchFeedInvalid():
            return fixed
        case str() | None:
            pass
    status = _status(value["status"], tracker)
    severity = _severity(value["severity"])
    if status is None or severity is None:
        return ArchFeedInvalid("feed record has an unsupported status or severity")
    if tracker and not _tracker_fields(value):
        return ArchFeedInvalid("Tracker record has an invalid field type")
    return ArchAdvisory(name, packages, status, advisory_type, severity, fixed, issues)


def _tracker_fields(value: dict[str, JsonValue]) -> bool:
    affected = _identifier(value["affected"])
    ticket = _optional_string(value["ticket"])
    advisories = _avg_identifiers(value["advisories"], _MAX_ISSUES)
    match ticket:
        case ArchFeedInvalid():
            return False
        case str() | None:
            return affected is not None and advisories is not None


def _string(value: JsonValue) -> str | None:
    if (
        type(value) is str
        and 0 < len(value) <= _MAX_STRING
        and value.isprintable()
        and "://" not in value
    ):
        return value
    return None


def _identifier(value: JsonValue) -> str | None:
    if (
        type(value) is str
        and 0 < len(value) <= _MAX_IDENTIFIER
        and value.isprintable()
        and "://" not in value
    ):
        return value
    return None


def _avg_identifier(value: JsonValue) -> str | None:
    identifier = _identifier(value)
    if identifier is None or _AVG.fullmatch(identifier) is None:
        return None
    return identifier


def _optional_string(value: JsonValue) -> str | None | ArchFeedInvalid:
    if value is None:
        return None
    string = _string(value)
    return string if string is not None else ArchFeedInvalid("string field is invalid")


def _identifiers(value: JsonValue, maximum: int) -> tuple[str, ...] | None:
    if type(value) is not list or len(value) > maximum:
        return None
    values = tuple(_identifier(entry) for entry in value)
    if any(entry is None for entry in values):
        return None
    identifiers = tuple(entry for entry in values if entry is not None)
    return identifiers if len(set(identifiers)) == len(identifiers) else None


def _avg_identifiers(value: JsonValue, maximum: int) -> tuple[str, ...] | None:
    identifiers = _identifiers(value, maximum)
    if identifiers is None or any(
        _AVG.fullmatch(identifier) is None for identifier in identifiers
    ):
        return None
    return identifiers


def _status(value: JsonValue, tracker: bool) -> ArchStatus | None:
    if type(value) is not str:
        return None
    try:
        status = ArchStatus(value)
    except ValueError:
        return None
    if status is ArchStatus.NOT_AFFECTED and not tracker:
        return None
    return status


def _severity(value: JsonValue) -> Severity | None:
    if type(value) is not str:
        return None
    try:
        return Severity(value.lower())
    except ValueError:
        return None
