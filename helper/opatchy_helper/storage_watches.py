import re
from typing import Final, NoReturn, assert_never

from .json_value import JsonObject, JsonValue
from .models import ItemId, WatchMode
from .storage_types import SecurityFixCondition, StateCorruptError, WatchRecord

_MAX_VERSION_LENGTH: Final = 256
_MAX_CVE_IDS: Final = 16
_ARCH_ITEM_ID: Final[re.Pattern[str]] = re.compile(
    r"^arch:[A-Za-z0-9@_+][A-Za-z0-9@._+-]{0,127}$"
)
_ADVISORY_ID: Final[re.Pattern[str]] = re.compile(r"^AVG-[0-9]{1,120}$")
_CVE_ID: Final[re.Pattern[str]] = re.compile(r"^CVE-[0-9]{4}-[0-9]{4,19}$")


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


def parse_v1_watch(value: JsonValue) -> WatchRecord:
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


def parse_watch(value: JsonValue) -> WatchRecord:
    document = _object(value, "watch")
    condition = _condition(_field(document, "condition"))
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
        condition,
    )


def security_fix_condition(
    advisory_id: str, cve_ids: tuple[str, ...], fixed_version: str
) -> SecurityFixCondition:
    condition = SecurityFixCondition(advisory_id, cve_ids, fixed_version)
    _validate_condition(condition)
    return condition


def validate_watch(watch: WatchRecord) -> None:
    match watch.mode:
        case WatchMode.PERMANENT:
            if (
                watch.installed_fingerprint is not None
                or watch.candidate_fingerprint is not None
                or watch.armed
                or watch.condition is not None
            ):
                _corrupt("permanent watches must not retain temporary internals")
            return
        case WatchMode.TEMPORARY:
            if watch.installed_fingerprint is None:
                _corrupt("temporary watches require an installed baseline")
            if watch.armed != (watch.candidate_fingerprint is not None):
                _corrupt("temporary watch candidate and arming are inconsistent")
            match watch.condition:
                case None:
                    return
                case condition:
                    if _ARCH_ITEM_ID.fullmatch(str(watch.item_id)) is None:
                        _corrupt("conditional watches require a canonical Arch item ID")
                    _validate_condition(condition)
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
        "condition": _condition_value(watch.condition),
    }


def _condition(value: JsonValue) -> SecurityFixCondition | None:
    if value is None:
        return None
    document = _object(value, "watch.condition")
    if set(document) != {"advisoryId", "cveIds", "fixedVersion"}:
        _corrupt("watch.condition fields are invalid")
    return security_fix_condition(
        _string(_field(document, "advisoryId"), "watch.condition.advisoryId"),
        _cve_ids(_field(document, "cveIds")),
        _string(_field(document, "fixedVersion"), "watch.condition.fixedVersion"),
    )


def _condition_value(condition: SecurityFixCondition | None) -> JsonObject | None:
    match condition:
        case None:
            return None
        case SecurityFixCondition():
            return {
                "advisoryId": condition.advisory_id,
                "cveIds": list(condition.cve_ids),
                "fixedVersion": condition.fixed_version,
            }


def _validate_condition(condition: SecurityFixCondition) -> None:
    if _ADVISORY_ID.fullmatch(condition.advisory_id) is None:
        _corrupt("watch.condition advisory is invalid")
    if (
        not condition.cve_ids
        or len(condition.cve_ids) > _MAX_CVE_IDS
        or len(set(condition.cve_ids)) != len(condition.cve_ids)
        or any(_CVE_ID.fullmatch(cve_id) is None for cve_id in condition.cve_ids)
    ):
        _corrupt("watch.condition CVE evidence is invalid")
    if (
        not condition.fixed_version
        or len(condition.fixed_version) > _MAX_VERSION_LENGTH
        or not condition.fixed_version.isascii()
        or not condition.fixed_version.isprintable()
    ):
        _corrupt("watch.condition fixed version is invalid")


def _cve_ids(value: JsonValue) -> tuple[str, ...]:
    if type(value) is not list:
        _corrupt("watch.condition.cveIds must be an array")
    return tuple(_string(entry, "watch.condition.cveIds") for entry in value)


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
