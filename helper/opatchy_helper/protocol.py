from datetime import datetime, timezone
from typing import Final, NoReturn

from .json_value import decode_json
from .models import ErrorCode, ErrorInfo, ProtocolError, Response
from .parser import parse_response
from .wire import response_value

MAX_PROTOCOL_BYTES: Final = 5 * 1024 * 1024

__all__ = (
    "MAX_PROTOCOL_BYTES",
    "ProtocolError",
    "decode_response",
    "encode_response",
    "utc_now",
)


def encode_response(response: Response) -> bytes:
    encoded = _encode_json(response)
    if len(encoded) >= MAX_PROTOCOL_BYTES:
        _fail(ErrorCode.OUTPUT_TOO_LARGE, "encoded response reaches the five MiB limit")
    return encoded


def decode_response(raw: bytes) -> Response:
    if len(raw) >= MAX_PROTOCOL_BYTES:
        _fail(ErrorCode.PAYLOAD_TOO_LARGE, "input reaches the five MiB limit")
    try:
        decoded_text = raw.decode("utf-8")
    except UnicodeDecodeError:
        _fail(ErrorCode.INVALID_UTF8, "input is not UTF-8")
    return parse_response(decode_json(decoded_text))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _encode_json(response: Response) -> bytes:
    import json

    return (
        json.dumps(
            response_value(response),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _fail(code: ErrorCode, message: str) -> NoReturn:
    raise ProtocolError(ErrorInfo(code, message))
