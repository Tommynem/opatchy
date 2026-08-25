import json
from typing import Final, NoReturn, TypeAlias, cast

from .models import ErrorCode, ErrorInfo, ProtocolError

MAX_JSON_DEPTH: Final = 100
JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
JsonObject: TypeAlias = dict[str, JsonValue]


def decode_json(text: str) -> JsonValue:
    try:
        # json.loads is the untyped stdlib boundary; normalization follows immediately.
        return _normalize(
            cast(
                JsonValue,
                json.loads(
                    text,
                    object_pairs_hook=_unique_object,
                    parse_constant=_reject_constant,
                ),
            ),
            0,
        )
    except json.JSONDecodeError, RecursionError:
        _fail(ErrorCode.MALFORMED_JSON, "input is not valid JSON")


def _unique_object(pairs: list[tuple[str, JsonValue]]) -> JsonObject:
    value: JsonObject = {}
    for key, item in pairs:
        if key in value:
            _fail(ErrorCode.MALFORMED_JSON, "input contains a duplicate object key")
        value[key] = item
    return value


def _reject_constant(_: str) -> NoReturn:
    _fail(ErrorCode.MALFORMED_JSON, "input is not valid JSON")


def _normalize(value: JsonValue, depth: int) -> JsonValue:
    if depth > MAX_JSON_DEPTH:
        _fail(ErrorCode.MALFORMED_JSON, "input exceeds the JSON nesting limit")
    if type(value) is str:
        _reject_surrogate(value)
        return value
    if type(value) is list:
        return [_normalize(item, depth + 1) for item in value]
    if type(value) is dict:
        normalized: JsonObject = {}
        for key, item in value.items():
            normalized[key] = _normalize(item, depth + 1)
        return normalized
    return value


def _reject_surrogate(value: str) -> None:
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        _fail(ErrorCode.MALFORMED_JSON, "input contains an unpaired surrogate")


def _fail(code: ErrorCode, message: str) -> NoReturn:
    raise ProtocolError(ErrorInfo(code, message))
