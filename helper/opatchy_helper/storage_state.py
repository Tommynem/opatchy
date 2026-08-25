import json
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Final, NoReturn

from .json_value import JsonObject, JsonValue, decode_json
from .models import (
    ItemId,
    NotificationFingerprint,
    NotificationStatus,
    SourceName,
    WatchMode,
)
from .storage_types import (
    LedgerEntry,
    PersistentState,
    SourceMetadata,
    StateCorruptError,
    StateSchemaIncompatible,
    WatchRecord,
)

STATE_SCHEMA_VERSION: Final = 1
MAX_INACTIVE_LEDGER_ENTRIES: Final = 5_000
MAX_INACTIVE_LEDGER_AGE: Final = timedelta(days=180)


def encode_state(state: PersistentState, now: datetime) -> bytes:
    validate_state(state)
    normalized = prune_ledger(state, now)
    value: JsonObject = {
        "schemaVersion": STATE_SCHEMA_VERSION,
        "watches": [_watch_value(watch) for watch in normalized.watches],
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
    if version != STATE_SCHEMA_VERSION:
        _corrupt("state.schemaVersion is unsupported")
    return _parse_v1(document)


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
        _parse_v0_watch(value)
        for value in _array(_field(document, "watches"), "watches")
    )
    _unique((str(watch.item_id) for watch in watches), "state has duplicate watches")
    return PersistentState(watches, (), ())


def _parse_v1(document: JsonObject) -> PersistentState:
    watches = tuple(
        _parse_watch(value) for value in _array(_field(document, "watches"), "watches")
    )
    ledger = tuple(
        _parse_ledger(value) for value in _array(_field(document, "ledger"), "ledger")
    )
    sources = tuple(
        _parse_source(value) for value in _array(_field(document, "sources"), "sources")
    )
    _unique((str(watch.item_id) for watch in watches), "state has duplicate watches")
    _unique(
        (str(entry.fingerprint) for entry in ledger),
        "state has duplicate ledger entries",
    )
    _unique(
        (str(source.source) for source in sources),
        "state has duplicate source metadata",
    )
    return PersistentState(watches, ledger, sources)


def _parse_v0_watch(value: JsonValue) -> WatchRecord:
    document = _object(value, "watch")
    return WatchRecord(
        ItemId(_string(_field(document, "itemId"), "watch.itemId")),
        _watch_mode(_field(document, "mode")),
        None,
        None,
        False,
    )


def _parse_watch(value: JsonValue) -> WatchRecord:
    document = _object(value, "watch")
    return WatchRecord(
        ItemId(_string(_field(document, "itemId"), "watch.itemId")),
        _watch_mode(_field(document, "mode")),
        _optional_string(
            _field(document, "installedFingerprint"), "watch.installedFingerprint"
        ),
        _optional_string(
            _field(document, "candidateFingerprint"), "watch.candidateFingerprint"
        ),
        _boolean(_field(document, "armed"), "watch.armed"),
    )


def _parse_ledger(value: JsonValue) -> LedgerEntry:
    document = _object(value, "ledger entry")
    return LedgerEntry(
        NotificationFingerprint(
            _string(_field(document, "fingerprint"), "ledger.fingerprint")
        ),
        _notification_status(_field(document, "status")),
        _timestamp(_field(document, "recordedAt"), "ledger.recordedAt"),
    )


def _parse_source(value: JsonValue) -> SourceMetadata:
    document = _object(value, "source metadata")
    return SourceMetadata(
        _source_name(_field(document, "source")),
        _optional_timestamp(_field(document, "lastSuccess"), "source.lastSuccess"),
        _optional_timestamp(_field(document, "backoffUntil"), "source.backoffUntil"),
    )


def _watch_value(watch: WatchRecord) -> JsonObject:
    return {
        "itemId": str(watch.item_id),
        "mode": watch.mode.value,
        "installedFingerprint": watch.installed_fingerprint,
        "candidateFingerprint": watch.candidate_fingerprint,
        "armed": watch.armed,
    }


def _ledger_value(entry: LedgerEntry) -> JsonObject:
    return {
        "fingerprint": str(entry.fingerprint),
        "status": entry.status.value,
        "recordedAt": _format_timestamp(entry.recorded_at),
    }


def _source_value(source: SourceMetadata) -> JsonObject:
    return {
        "source": source.source.value,
        "lastSuccess": _optional_timestamp_value(source.last_success),
        "backoffUntil": _optional_timestamp_value(source.backoff_until),
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


def _optional_string(value: JsonValue, path: str) -> str | None:
    return None if value is None else _string(value, path)


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


def _watch_mode(value: JsonValue) -> WatchMode:
    try:
        return WatchMode(_string(value, "watch.mode"))
    except ValueError:
        _corrupt("watch.mode is invalid")


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
