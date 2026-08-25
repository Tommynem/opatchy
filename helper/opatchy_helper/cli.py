from collections.abc import Sequence
import sys
from typing import Final
from uuid import uuid4

from .models import ErrorCode, ErrorInfo, ErrorResponse, GenerationId, WatchMode
from .protocol import encode_response, utc_now


EXIT_ERROR: Final = 2


def main(arguments: Sequence[str]) -> int:
    response = _dispatch(tuple(arguments))
    sys.stdout.buffer.write(encode_response(response))
    return EXIT_ERROR


def _dispatch(arguments: tuple[str, ...]) -> ErrorResponse:
    match arguments:
        case ("snapshot",) | ("scan",) | ("scan", "--force"):
            return _error(ErrorCode.STATE_UNAVAILABLE, "validated snapshot storage is not available yet")
        case ("inventory", "--source", source, "--query", _, "--limit", limit, "--offset", offset):
            return _inventory_result(source, limit, offset)
        case ("set-star", "--item-id", item_id, "--mode", mode):
            return _star_result(item_id, mode)
        case _:
            return _error(ErrorCode.CLI_USAGE, "unsupported helper command or arguments")


def _inventory_result(source: str, limit: str, offset: str) -> ErrorResponse:
    match source:
        case "arch" | "aur" | "flatpak" | "mise":
            return _inventory_pagination(limit, offset)
        case _:
            return _error(ErrorCode.CLI_USAGE, "inventory source is unsupported")


def _inventory_pagination(limit: str, offset: str) -> ErrorResponse:
    parsed_limit = _nonnegative_decimal(limit)
    parsed_offset = _nonnegative_decimal(offset)
    if parsed_limit is None or parsed_offset is None or parsed_limit < 1 or parsed_limit > 100:
        return _error(ErrorCode.CLI_USAGE, "inventory pagination is invalid")
    return _error(ErrorCode.STATE_UNAVAILABLE, "validated inventory storage is not available yet")


def _star_result(item_id: str, mode: str) -> ErrorResponse:
    if not item_id or len(item_id) > 128:
        return _error(ErrorCode.CLI_USAGE, "item ID is invalid")
    match mode:
        case WatchMode.OFF | WatchMode.TEMPORARY | WatchMode.PERMANENT:
            return _error(ErrorCode.STATE_UNAVAILABLE, "validated watch storage is not available yet")
        case _:
            return _error(ErrorCode.CLI_USAGE, "watch mode is invalid")


def _nonnegative_decimal(value: str) -> int | None:
    if value.isdecimal():
        return int(value)
    return None


def _error(code: ErrorCode, message: str) -> ErrorResponse:
    return ErrorResponse(utc_now(), GenerationId(f"cli-{uuid4().hex}"), ErrorInfo(code, message))
