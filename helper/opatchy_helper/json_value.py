import re
from typing import Final, NoReturn, TypeAlias

from .models import ErrorCode, ErrorInfo, ProtocolError

MAX_JSON_DEPTH: Final = 100
NUMBER_PATTERN: Final = re.compile(
    r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"
)
JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
JsonObject: TypeAlias = dict[str, JsonValue]


def decode_json(text: str) -> JsonValue:
    value, index = _parse_value(text, 0, 0)
    if _skip_whitespace(text, index) != len(text):
        _fail(ErrorCode.MALFORMED_JSON, "input is not valid JSON")
    return value


def _parse_value(text: str, index: int, depth: int) -> tuple[JsonValue, int]:
    if depth > MAX_JSON_DEPTH:
        _fail(ErrorCode.MALFORMED_JSON, "input exceeds the JSON nesting limit")
    cursor = _skip_whitespace(text, index)
    if cursor >= len(text):
        _fail(ErrorCode.MALFORMED_JSON, "input is not valid JSON")
    token = text[cursor]
    if token == '"':
        return _parse_string(text, cursor)
    if token == "[":
        return _parse_array(text, cursor + 1, depth)
    if token == "{":
        return _parse_object(text, cursor + 1, depth)
    if text.startswith("true", cursor):
        return True, cursor + 4
    if text.startswith("false", cursor):
        return False, cursor + 5
    if text.startswith("null", cursor):
        return None, cursor + 4
    return _parse_number(text, cursor)


def _parse_array(text: str, index: int, depth: int) -> tuple[list[JsonValue], int]:
    cursor = _skip_whitespace(text, index)
    if cursor < len(text) and text[cursor] == "]":
        return [], cursor + 1
    values: list[JsonValue] = []
    while True:
        value, cursor = _parse_value(text, cursor, depth + 1)
        values.append(value)
        cursor = _skip_whitespace(text, cursor)
        if cursor >= len(text):
            _fail(ErrorCode.MALFORMED_JSON, "input is not valid JSON")
        if text[cursor] == "]":
            return values, cursor + 1
        if text[cursor] != ",":
            _fail(ErrorCode.MALFORMED_JSON, "input is not valid JSON")
        cursor = _skip_whitespace(text, cursor + 1)


def _parse_object(text: str, index: int, depth: int) -> tuple[JsonObject, int]:
    cursor = _skip_whitespace(text, index)
    if cursor < len(text) and text[cursor] == "}":
        return {}, cursor + 1
    fields: JsonObject = {}
    while True:
        if cursor >= len(text) or text[cursor] != '"':
            _fail(ErrorCode.MALFORMED_JSON, "input is not valid JSON")
        key, cursor = _parse_string(text, cursor)
        cursor = _skip_whitespace(text, cursor)
        if cursor >= len(text) or text[cursor] != ":":
            _fail(ErrorCode.MALFORMED_JSON, "input is not valid JSON")
        value, cursor = _parse_value(text, cursor + 1, depth + 1)
        if key in fields:
            _fail(ErrorCode.MALFORMED_JSON, "input contains a duplicate object key")
        fields[key] = value
        cursor = _skip_whitespace(text, cursor)
        if cursor >= len(text):
            _fail(ErrorCode.MALFORMED_JSON, "input is not valid JSON")
        if text[cursor] == "}":
            return fields, cursor + 1
        if text[cursor] != ",":
            _fail(ErrorCode.MALFORMED_JSON, "input is not valid JSON")
        cursor = _skip_whitespace(text, cursor + 1)


def _parse_number(text: str, index: int) -> tuple[int | float, int]:
    match = NUMBER_PATTERN.match(text, index)
    if match is None:
        _fail(ErrorCode.MALFORMED_JSON, "input is not valid JSON")
    token = match.group()
    if "." in token or "e" in token or "E" in token:
        return float(token), match.end()
    return int(token), match.end()


def _parse_string(text: str, index: int) -> tuple[str, int]:
    characters: list[str] = []
    cursor = index + 1
    while cursor < len(text):
        token = text[cursor]
        cursor += 1
        if token == '"':
            return "".join(characters), cursor
        if ord(token) < 0x20:
            _fail(ErrorCode.MALFORMED_JSON, "input is not valid JSON")
        if token != "\\":
            characters.append(token)
            continue
        if cursor >= len(text):
            _fail(ErrorCode.MALFORMED_JSON, "input is not valid JSON")
        escape = text[cursor]
        cursor += 1
        if escape == '"' or escape == "\\" or escape == "/":
            characters.append(escape)
            continue
        if escape == "b":
            characters.append("\b")
            continue
        if escape == "f":
            characters.append("\f")
            continue
        if escape == "n":
            characters.append("\n")
            continue
        if escape == "r":
            characters.append("\r")
            continue
        if escape == "t":
            characters.append("\t")
            continue
        if escape != "u":
            _fail(ErrorCode.MALFORMED_JSON, "input is not valid JSON")
        codepoint, cursor = _parse_unicode_escape(text, cursor)
        if 0xD800 <= codepoint <= 0xDBFF:
            if cursor + 6 > len(text) or text[cursor : cursor + 2] != "\\u":
                _fail(ErrorCode.MALFORMED_JSON, "input contains an unpaired surrogate")
            low_surrogate, cursor = _parse_unicode_escape(text, cursor + 2)
            if not 0xDC00 <= low_surrogate <= 0xDFFF:
                _fail(ErrorCode.MALFORMED_JSON, "input contains an unpaired surrogate")
            characters.append(
                chr(0x10000 + (codepoint - 0xD800) * 0x400 + low_surrogate - 0xDC00)
            )
            continue
        if 0xDC00 <= codepoint <= 0xDFFF:
            _fail(ErrorCode.MALFORMED_JSON, "input contains an unpaired surrogate")
        characters.append(chr(codepoint))
    _fail(ErrorCode.MALFORMED_JSON, "input is not valid JSON")


def _parse_unicode_escape(text: str, index: int) -> tuple[int, int]:
    if index + 4 > len(text):
        _fail(ErrorCode.MALFORMED_JSON, "input is not valid JSON")
    value = 0
    for token in text[index : index + 4]:
        if "0" <= token <= "9":
            digit = ord(token) - ord("0")
        elif "a" <= token <= "f":
            digit = ord(token) - ord("a") + 10
        elif "A" <= token <= "F":
            digit = ord(token) - ord("A") + 10
        else:
            _fail(ErrorCode.MALFORMED_JSON, "input is not valid JSON")
        value = value * 16 + digit
    return value, index + 4


def _skip_whitespace(text: str, index: int) -> int:
    cursor = index
    while cursor < len(text) and text[cursor] in " \t\r\n":
        cursor += 1
    return cursor


def _fail(code: ErrorCode, message: str) -> NoReturn:
    raise ProtocolError(ErrorInfo(code, message))
