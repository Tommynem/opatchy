from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NoReturn, TypeVar

from .json_value import JsonObject, JsonValue
from .models import (
    PROTOCOL_VERSION,
    ErrorCode,
    ErrorInfo,
    ProtocolError,
    ProtocolVersion,
)

EnumValue = TypeVar("EnumValue", bound=StrEnum)


@dataclass(frozen=True, slots=True)
class Reader:
    value: JsonObject
    path: str

    def field(self, name: str) -> JsonValue:
        try:
            return self.value[name]
        except KeyError:
            fail(ErrorCode.MISSING_FIELD, f"missing {self.path}.{name}")


def reader(value: JsonValue, path: str, fields: frozenset[str]) -> Reader:
    if type(value) is not dict:
        fail(ErrorCode.INVALID_TYPE, f"{path} must be an object")
    unknown_fields = set(value).difference(fields)
    if unknown_fields:
        fail(ErrorCode.UNKNOWN_FIELD, f"unknown {path}.{min(unknown_fields)}")
    return Reader(value, path)


def protocol_version(value: JsonValue) -> ProtocolVersion:
    if type(value) is not int:
        fail(
            ErrorCode.PROTOCOL_VERSION_INVALID,
            "protocolVersion must be an exact integer",
        )
    if value > int(PROTOCOL_VERSION):
        fail(
            ErrorCode.PROTOCOL_VERSION_FUTURE,
            "protocolVersion is newer than this helper",
        )
    if value != int(PROTOCOL_VERSION):
        fail(ErrorCode.PROTOCOL_VERSION_INVALID, "protocolVersion is unsupported")
    return ProtocolVersion(value)


def timestamp(value: JsonValue, path: str) -> datetime:
    raw = string(value, path)
    if len(raw) < 21 or raw[10] != "T" or not raw.endswith("Z"):
        fail(ErrorCode.INVALID_TIMESTAMP, f"{path} must be UTC RFC3339")
    try:
        return datetime.fromisoformat(f"{raw[:-1]}+00:00")
    except ValueError:
        fail(ErrorCode.INVALID_TIMESTAMP, f"{path} must be UTC RFC3339")


def enum(enum_type: type[EnumValue], value: JsonValue, path: str) -> EnumValue:
    try:
        return enum_type(string(value, path))
    except ValueError:
        fail(ErrorCode.UNKNOWN_ENUM, f"unknown enum at {path}")


def optional_string(value: JsonValue, path: str) -> str | None:
    return None if value is None else string(value, path)


def identifier(value: JsonValue, path: str) -> str:
    return string(value, path)


def bounded_string(value: JsonValue, path: str, maximum_length: int) -> str:
    raw = string(value, path)
    if not raw or len(raw) > maximum_length:
        fail(ErrorCode.INVALID_TYPE, f"{path} must be a bounded non-empty string")
    return raw


def string(value: JsonValue, path: str) -> str:
    if type(value) is str:
        return value
    fail(ErrorCode.INVALID_TYPE, f"{path} must be a string")


def boolean(value: JsonValue, path: str) -> bool:
    if type(value) is bool:
        return value
    fail(ErrorCode.INVALID_TYPE, f"{path} must be a boolean")


def nonnegative_int(value: JsonValue, path: str) -> int:
    if type(value) is not int or value < 0:
        fail(ErrorCode.INVALID_TYPE, f"{path} must be a non-negative exact integer")
    return value


def list_value(value: JsonValue, path: str) -> list[JsonValue]:
    if type(value) is list:
        return value
    fail(ErrorCode.INVALID_TYPE, f"{path} must be an array")


def reject_field(reader_value: Reader, name: str) -> None:
    if name in reader_value.value:
        fail(
            ErrorCode.INVALID_ENVELOPE,
            f"response.{name} is incompatible with response.kind",
        )


def fail(code: ErrorCode, message: str) -> NoReturn:
    raise ProtocolError(ErrorInfo(code, message))
