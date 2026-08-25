from typing import assert_never

from .json_value import JsonValue
from .models import (
    ErrorCode,
    ErrorResponse,
    GenerationId,
    InventoryResponse,
    Response,
    ResponseKind,
    SnapshotResponse,
    StarResultResponse,
)
from .parser_fields import (
    enum,
    fail,
    identifier,
    protocol_version,
    reader,
    reject_field,
    timestamp,
)
from .payload_parser import (
    parse_error,
    parse_inventory,
    parse_snapshot,
    parse_star_result,
)
from .validation import validate_response


def parse_response(value: JsonValue) -> Response:
    reader_value = reader(
        value,
        "response",
        frozenset(
            (
                "protocolVersion",
                "kind",
                "generatedAt",
                "generationId",
                "payload",
                "error",
            )
        ),
    )
    if "protocolVersion" not in reader_value.value:
        fail(
            ErrorCode.PROTOCOL_VERSION_MISSING,
            "protocolVersion is required",
        )
    version = protocol_version(reader_value.field("protocolVersion"))
    generated_at = timestamp(reader_value.field("generatedAt"), "response.generatedAt")
    generation_id = GenerationId(
        identifier(reader_value.field("generationId"), "response.generationId")
    )
    kind = enum(ResponseKind, reader_value.field("kind"), "response.kind")
    match kind:
        case ResponseKind.SNAPSHOT:
            reject_field(reader_value, "error")
            return _validated(
                SnapshotResponse(
                    generated_at,
                    generation_id,
                    parse_snapshot(reader_value.field("payload")),
                    version,
                )
            )
        case ResponseKind.INVENTORY:
            reject_field(reader_value, "error")
            return _validated(
                InventoryResponse(
                    generated_at,
                    generation_id,
                    parse_inventory(reader_value.field("payload")),
                    version,
                )
            )
        case ResponseKind.STAR_RESULT:
            reject_field(reader_value, "error")
            return _validated(
                StarResultResponse(
                    generated_at,
                    generation_id,
                    parse_star_result(reader_value.field("payload")),
                    version,
                )
            )
        case ResponseKind.ERROR:
            reject_field(reader_value, "payload")
            return _validated(
                ErrorResponse(
                    generated_at,
                    generation_id,
                    parse_error(reader_value.field("error"), "response.error"),
                    version,
                )
            )
    assert_never(kind)


def _validated(response: Response) -> Response:
    validate_response(response)
    return response
