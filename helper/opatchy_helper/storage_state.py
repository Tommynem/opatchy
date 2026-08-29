import json
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from typing import Final, NoReturn

from .json_value import JsonObject, JsonValue, decode_json
from .models import (
    NotificationFingerprint,
    NotificationStatus,
    SourceName,
)
from .storage_types import (
    LedgerEntry,
    PersistentState,
    SourceMetadata,
    StateCorruptError,
    StateSchemaIncompatible,
    WatchRecord,
)
from .storage_watches import (
    parse_v0_watch,
    parse_v1_watch,
    parse_watch,
    validate_watch,
    watch_value,
)

STATE_SCHEMA_VERSION: Final = 2
MAX_INACTIVE_LEDGER_ENTRIES: Final = 5_000
MAX_INACTIVE_LEDGER_AGE: Final = timedelta(days=180)


def encode_state(state: PersistentState, now: datetime) -> bytes:
    validate_state(state)
    normalized = prune_ledger(state, now)
    value: JsonObject = {
        "schemaVersion": STATE_SCHEMA_VERSION,
        "watches": [watch_value(watch) for watch in normalized.watches],
        "ledger": [_ledger_value(entry) for entry in normalized.ledger],
        "sources": [_source_value(source) for source in normalized.sources],
    }
    return (
        json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        + b"\n"
    )


def decode_state(raw: bytes) -> PersistentState:
    try:
        value = decode_json(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise StateCorruptError("state is not UTF-8") from error
    document = _object(value, "state")
    version = _integer(_field(document, "schemaVersion"), "state.schemaVersion")
    if version > STATE_SCHEMA_VERSION:
        raise StateSchemaIncompatible(version)
    if version == 0:
        return _migrate_v0(document)
    if version == 1:
        return _migrate_v1(document)
    if version != STATE_SCHEMA_VERSION:
        _corrupt("state.schemaVersion is unsupported")
    return _parse_v2(document)


def validate_state(state: PersistentState) -> None:
    _unique(
        (str(watch.item_id) for watch in state.watches), "state has duplicate watches"
    )
    _unique(
        (str(entry.fingerprint) for entry in state.ledger),
        "state has duplicate ledger entries",
    )
    _unique(
        (str(source.source) for source in state.sources),
        "state has duplicate source metadata",
    )
    for source in state.sources:
        if type(source.failure_count) is not int or source.failure_count < 0:
            _corrupt("source failure count is invalid")
        if type(source.permanent_failure) is not bool:
            _corrupt("source permanent failure is invalid")
    for watch in state.watches:
        validate_watch(watch)
    for entry in state.ledger:
        if (entry.lease_token is None) != (entry.lease_expires_at is None):
            _corrupt("ledger lease is incomplete")
        if entry.lease_token == "":
            _corrupt("ledger lease token is invalid")


def prune_ledger(state: PersistentState, now: datetime) -> PersistentState:
    cutoff = now - MAX_INACTIVE_LEDGER_AGE
    active = tuple(entry for entry in state.ledger if entry.is_active)
    inactive = sorted(
        (
            entry
            for entry in state.ledger
            if not entry.is_active and entry.recorded_at >= cutoff
        ),
        key=lambda entry: (entry.recorded_at, str(entry.fingerprint)),
        reverse=True,
    )[:MAX_INACTIVE_LEDGER_ENTRIES]
    return PersistentState(state.watches, active + tuple(inactive), state.sources)


def _migrate_v0(document: JsonObject) -> PersistentState:
    watches = tuple(
        parse_v0_watch(value)
        for value in _array(_field(document, "watches"), "watches")
    )
    state = PersistentState(watches, (), ())
    validate_state(state)
    return state


def _migrate_v1(document: JsonObject) -> PersistentState:
    return _parse(document, parse_v1_watch)


def _parse_v2(document: JsonObject) -> PersistentState:
    return _parse(document, parse_watch)


def _parse(
    document: JsonObject, parse_watch_record: Callable[[JsonValue], WatchRecord]
) -> PersistentState:
    watches = tuple(
        parse_watch_record(value)
        for value in _array(_field(document, "watches"), "watches")
    )
    ledger = tuple(
        _parse_ledger(value) for value in _array(_field(document, "ledger"), "ledger")
    )
    sources = tuple(
        _parse_source(value) for value in _array(_field(document, "sources"), "sources")
    )
    state = PersistentState(watches, ledger, sources)
    validate_state(state)
    return state


def _parse_ledger(value: JsonValue) -> LedgerEntry:
    document = _object(value, "ledger entry")
    lease_token = _optional_ledger_string(document, "leaseToken")
    lease_expires_at = _optional_ledger_timestamp(document, "leaseExpiresAt")
    return LedgerEntry(
        NotificationFingerprint(
            _string(_field(document, "fingerprint"), "ledger.fingerprint")
        ),
        _notification_status(_field(document, "status")),
        _timestamp(_field(document, "recordedAt"), "ledger.recordedAt"),
        lease_token,
        lease_expires_at,
    )


def _parse_source(value: JsonValue) -> SourceMetadata:
    document = _object(value, "source metadata")
    return SourceMetadata(
        _source_name(_field(document, "source")),
        _optional_timestamp(_field(document, "lastSuccess"), "source.lastSuccess"),
        _optional_timestamp(_field(document, "backoffUntil"), "source.backoffUntil"),
        _source_failure_count(document),
        _source_permanent_failure(document),
    )


def _ledger_value(entry: LedgerEntry) -> JsonObject:
    return {
        "fingerprint": str(entry.fingerprint),
        "status": entry.status.value,
        "recordedAt": _format_timestamp(entry.recorded_at),
        "leaseToken": entry.lease_token,
        "leaseExpiresAt": _optional_timestamp_value(entry.lease_expires_at),
    }


def _source_value(source: SourceMetadata) -> JsonObject:
    return {
        "source": source.source.value,
        "lastSuccess": _optional_timestamp_value(source.last_success),
        "backoffUntil": _optional_timestamp_value(source.backoff_until),
        "failureCount": source.failure_count,
        "permanentFailure": source.permanent_failure,
    }


def _optional_timestamp_value(value: datetime | None) -> str | None:
    return None if value is None else _format_timestamp(value)


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timedelta():
        _corrupt("state timestamps must be UTC")
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _field(document: JsonObject, name: str) -> JsonValue:
    try:
        return document[name]
    except KeyError:
        _corrupt(f"state is missing {name}")


def _object(value: JsonValue, path: str) -> JsonObject:
    if type(value) is dict:
        return value
    _corrupt(f"{path} must be an object")


def _array(value: JsonValue, path: str) -> list[JsonValue]:
    if type(value) is list:
        return value
    _corrupt(f"{path} must be an array")


def _string(value: JsonValue, path: str) -> str:
    if type(value) is str:
        return value
    _corrupt(f"{path} must be a string")


def _integer(value: JsonValue, path: str) -> int:
    if type(value) is int:
        return value
    _corrupt(f"{path} must be an integer")


def _boolean(value: JsonValue, path: str) -> bool:
    if type(value) is bool:
        return value
    _corrupt(f"{path} must be a boolean")


def _timestamp(value: JsonValue, path: str) -> datetime:
    raw = _string(value, path)
    if not raw.endswith("Z"):
        _corrupt(f"{path} must be UTC RFC3339")
    try:
        parsed = datetime.fromisoformat(f"{raw[:-1]}+00:00")
    except ValueError:
        _corrupt(f"{path} must be UTC RFC3339")
    return parsed


def _optional_timestamp(value: JsonValue, path: str) -> datetime | None:
    return None if value is None else _timestamp(value, path)


def _optional_ledger_string(document: JsonObject, name: str) -> str | None:
    return (
        None
        if name not in document
        else _optional_string(document[name], f"ledger.{name}")
    )


def _optional_string(value: JsonValue, path: str) -> str | None:
    return None if value is None else _string(value, path)


def _optional_ledger_timestamp(document: JsonObject, name: str) -> datetime | None:
    return (
        None
        if name not in document
        else _optional_timestamp(document[name], f"ledger.{name}")
    )


def _source_failure_count(document: JsonObject) -> int:
    if "failureCount" not in document:
        return 0
    return _nonnegative_integer(document["failureCount"], "source.failureCount")


def _source_permanent_failure(document: JsonObject) -> bool:
    if "permanentFailure" not in document:
        return False
    return _boolean(document["permanentFailure"], "source.permanentFailure")


def _nonnegative_integer(value: JsonValue, path: str) -> int:
    integer = _integer(value, path)
    if integer < 0:
        _corrupt(f"{path} must be non-negative")
    return integer


def _notification_status(value: JsonValue) -> NotificationStatus:
    try:
        return NotificationStatus(_string(value, "ledger.status"))
    except ValueError:
        _corrupt("ledger.status is invalid")


def _source_name(value: JsonValue) -> SourceName:
    try:
        return SourceName(_string(value, "source.source"))
    except ValueError:
        _corrupt("source.source is invalid")


def _unique(values: Iterable[str], reason: str) -> None:
    collected = tuple(values)
    if len(collected) != len(set(collected)):
        _corrupt(reason)


def _corrupt(reason: str) -> NoReturn:
    raise StateCorruptError(reason)
