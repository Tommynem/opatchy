import sys
from collections.abc import Sequence
from typing import Final
from uuid import uuid4

from .models import ErrorCode, ErrorInfo, ErrorResponse, GenerationId, WatchMode
from .protocol import encode_response, utc_now

EXIT_ERROR: Final = 2
SUPPORTED_INVENTORY_SOURCES: Final = frozenset(("arch", "aur", "flatpak", "mise"))


def main(arguments: Sequence[str]) -> int:
    response = _dispatch(tuple(arguments))
    _ = sys.stdout.buffer.write(encode_response(response))
    return EXIT_ERROR


def _dispatch(arguments: tuple[str, ...]) -> ErrorResponse:
    if arguments in (("snapshot",), ("scan",), ("scan", "--force")):
        return _error(
            ErrorCode.STATE_UNAVAILABLE,
            "validated snapshot storage is not available yet",
        )
    if (
        len(arguments) == 9
        and arguments[0] == "inventory"
        and arguments[1] == "--source"
        and arguments[3] == "--query"
        and arguments[5] == "--limit"
        and arguments[7] == "--offset"
    ):
        return _inventory_result(arguments[2], arguments[6], arguments[8])
    if (
        len(arguments) == 5
        and arguments[0] == "set-star"
        and arguments[1] == "--item-id"
        and arguments[3] == "--mode"
    ):
        return _star_result(arguments[2], arguments[4])
    return _error(ErrorCode.CLI_USAGE, "unsupported helper command or arguments")


def _inventory_result(source: str, limit: str, offset: str) -> ErrorResponse:
    if source not in SUPPORTED_INVENTORY_SOURCES:
        return _error(ErrorCode.CLI_USAGE, "inventory source is unsupported")
    return _inventory_pagination(limit, offset)


def _inventory_pagination(limit: str, offset: str) -> ErrorResponse:
    parsed_limit = _nonnegative_decimal(limit)
    parsed_offset = _nonnegative_decimal(offset)
    if (
        parsed_limit is None
        or parsed_offset is None
        or parsed_limit < 1
        or parsed_limit > 100
    ):
        return _error(ErrorCode.CLI_USAGE, "inventory pagination is invalid")
    return _error(
        ErrorCode.STATE_UNAVAILABLE, "validated inventory storage is not available yet"
    )


def _star_result(item_id: str, mode: str) -> ErrorResponse:
    if not item_id or len(item_id) > 128:
        return _error(ErrorCode.CLI_USAGE, "item ID is invalid")
    try:
        _ = WatchMode(mode)
    except ValueError:
        return _error(ErrorCode.CLI_USAGE, "watch mode is invalid")
    return _error(
        ErrorCode.STATE_UNAVAILABLE, "validated watch storage is not available yet"
    )


def _nonnegative_decimal(value: str) -> int | None:
    if value.isdecimal():
        return int(value)
    return None


def _error(code: ErrorCode, message: str) -> ErrorResponse:
    return ErrorResponse(
        utc_now(), GenerationId(f"cli-{uuid4().hex}"), ErrorInfo(code, message)
    )
