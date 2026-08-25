import json
from typing import NoReturn, TypeAlias, TypeGuard, cast

from .models import ErrorCode, ErrorInfo, ProtocolError


JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


def decode_json(text: str) -> JsonValue:
    try:
        raw = cast(object, json.loads(text))  # noqa: OBJECT_OK - sole raw JSON boundary
    except json.JSONDecodeError:
        _fail(ErrorCode.MALFORMED_JSON, "input is not valid JSON")
    return _normalize(raw)


def is_exact_bool(value: object) -> TypeGuard[bool]:  # noqa: OBJECT_OK - raw JSON boundary
    return type(value) is bool


def is_exact_int(value: object) -> TypeGuard[int]:  # noqa: OBJECT_OK - raw JSON boundary
    return type(value) is int


def is_exact_string(value: object) -> TypeGuard[str]:  # noqa: OBJECT_OK - raw JSON boundary
    return type(value) is str


def is_json_list(value: JsonValue) -> TypeGuard[list[JsonValue]]:
    return type(value) is list


def is_json_object(value: JsonValue) -> TypeGuard[JsonObject]:
    return type(value) is dict


def _normalize(value: object) -> JsonValue:  # noqa: OBJECT_OK - raw JSON boundary
    if value is None:
        return None
    if is_exact_bool(value):
        return value
    if is_exact_int(value):
        return value
    if is_exact_string(value):
        return value
    if _is_exact_float(value):
        return value
    if _is_raw_list(value):
        return [_normalize(item) for item in value]
    if _is_raw_object(value):
        return _normalize_object(value)
    _fail(ErrorCode.INVALID_TYPE, "JSON contains an unsupported value")  # pragma: no cover - json.loads produces only JSON values


def _normalize_object(value: dict[object, object]) -> JsonObject:  # noqa: OBJECT_OK - raw JSON boundary
    normalized: JsonObject = {}
    for key, item in value.items():
        if is_exact_string(key):
            normalized[key] = _normalize(item)
            continue
        _fail(ErrorCode.INVALID_TYPE, "JSON object keys must be strings")  # pragma: no cover - json.loads produces only string keys
    return normalized


def _is_exact_float(value: object) -> TypeGuard[float]:  # noqa: OBJECT_OK - raw JSON boundary
    return type(value) is float


def _is_raw_list(value: object) -> TypeGuard[list[object]]:  # noqa: OBJECT_OK - raw JSON boundary
    return type(value) is list


def _is_raw_object(value: object) -> TypeGuard[dict[object, object]]:  # noqa: OBJECT_OK - raw JSON boundary
    return type(value) is dict


def _fail(code: ErrorCode, message: str) -> NoReturn:
    raise ProtocolError(ErrorInfo(code, message))
