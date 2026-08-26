from typing import NoReturn, assert_never

from .json_value import JsonObject, JsonValue
from .models import ItemId, WatchMode
from .storage_types import StateCorruptError, WatchRecord


def parse_v0_watch(value: JsonValue) -> WatchRecord:
    document = _object(value, "watch")
    item_id = ItemId(_string(_field(document, "itemId"), "watch.itemId"))
    mode = _watch_mode(_field(document, "mode"))
    match mode:
        case WatchMode.PERMANENT | WatchMode.TEMPORARY:
            return WatchRecord(item_id, WatchMode.PERMANENT, None, None, False)
        case WatchMode.OFF:
            _corrupt("v0 off watches are not durable")
    assert_never(mode)


def parse_watch(value: JsonValue) -> WatchRecord:
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


def validate_watch(watch: WatchRecord) -> None:
    match watch.mode:
        case WatchMode.PERMANENT:
            if (
                watch.installed_fingerprint is not None
                or watch.candidate_fingerprint is not None
                or watch.armed
            ):
                _corrupt("permanent watches must not retain temporary internals")
            return
        case WatchMode.TEMPORARY:
            if watch.installed_fingerprint is None:
                _corrupt("temporary watches require an installed baseline")
            if watch.armed != (watch.candidate_fingerprint is not None):
                _corrupt("temporary watch candidate and arming are inconsistent")
            return
        case WatchMode.OFF:
            _corrupt("off watches are not durable")
    assert_never(watch.mode)


def watch_value(watch: WatchRecord) -> JsonObject:
    return {
        "itemId": str(watch.item_id),
        "mode": watch.mode.value,
        "installedFingerprint": watch.installed_fingerprint,
        "candidateFingerprint": watch.candidate_fingerprint,
        "armed": watch.armed,
    }


def _field(document: JsonObject, name: str) -> JsonValue:
    try:
        return document[name]
    except KeyError:
        _corrupt(f"state is missing {name}")


def _object(value: JsonValue, path: str) -> JsonObject:
    if type(value) is dict:
        return value
    _corrupt(f"{path} must be an object")


def _string(value: JsonValue, path: str) -> str:
    if type(value) is str:
        return value
    _corrupt(f"{path} must be a string")


def _optional_string(value: JsonValue, path: str) -> str | None:
    return None if value is None else _string(value, path)


def _boolean(value: JsonValue, path: str) -> bool:
    if type(value) is bool:
        return value
    _corrupt(f"{path} must be a boolean")


def _watch_mode(value: JsonValue) -> WatchMode:
    try:
        return WatchMode(_string(value, "watch.mode"))
    except ValueError:
        _corrupt("watch.mode is invalid")


def _corrupt(reason: str) -> NoReturn:
    raise StateCorruptError(reason)
