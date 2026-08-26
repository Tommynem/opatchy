import sys
from collections.abc import Sequence
from typing import Final
from uuid import uuid4

from .cli_operations import execute
from .cli_requests import CliUnavailableError, CliUsageError, parse_command
from .models import ErrorCode, ErrorInfo, ErrorResponse, GenerationId, Response
from .protocol import ProtocolError, encode_response, utc_now
from .stars import WatchTransitionError
from .storage import StateSchemaIncompatible, StoragePathError

EXIT_ERROR: Final = 2


def main(arguments: Sequence[str]) -> int:
    response = _response(tuple(arguments))
    _ = sys.stdout.buffer.write(encode_response(response))
    return EXIT_ERROR if isinstance(response, ErrorResponse) else 0


def _response(arguments: tuple[str, ...]) -> Response:
    try:
        return execute(parse_command(arguments))
    except CliUsageError as error:
        return _error(ErrorCode.CLI_USAGE, error.message)
    except (
        CliUnavailableError,
        StateSchemaIncompatible,
        StoragePathError,
        WatchTransitionError,
    ):
        return _error(ErrorCode.STATE_UNAVAILABLE, "validated state is unavailable")
    except ProtocolError:
        return _error(ErrorCode.STATE_UNAVAILABLE, "validated state is unavailable")
    except Exception:  # noqa: BLE001 - the CLI boundary must never emit tracebacks
        return _error(ErrorCode.STATE_UNAVAILABLE, "helper operation failed")


def _error(code: ErrorCode, message: str) -> ErrorResponse:
    return ErrorResponse(
        utc_now(), GenerationId(f"cli-{uuid4().hex}"), ErrorInfo(code, message)
    )
