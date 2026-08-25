from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NoReturn, TypeVar

from .json_value import JsonObject, JsonValue, is_exact_bool, is_exact_int, is_exact_string, is_json_list, is_json_object
from .models import (
    PROTOCOL_VERSION,
    ErrorCode,
    ErrorInfo,
    ErrorResponse,
    FindingId,
    GenerationId,
    InventoryPayload,
    InventoryResponse,
    ItemId,
    ItemSource,
    NormalizedItem,
    NotificationFingerprint,
    NotificationOutcome,
    NotificationStatus,
    ProtocolError,
    ProtocolVersion,
    Provenance,
    Response,
    ResponseKind,
    ScanState,
    SecurityFinding,
    SecurityFindingGroup,
    Severity,
    SnapshotPayload,
    SnapshotResponse,
    SourceHealth,
    SourceName,
    SourceStatus,
    StarResultPayload,
    StarResultResponse,
    Summary,
    WatchMode,
)
from .validation import MAX_ERROR_MESSAGE_LENGTH, validate_response


EnumValue = TypeVar("EnumValue", bound=StrEnum)


@dataclass(frozen=True, slots=True)
class Reader:
    value: JsonObject
    path: str

    def field(self, name: str) -> JsonValue:
        try:
            return self.value[name]
        except KeyError:
            _fail(ErrorCode.MISSING_FIELD, f"missing {self.path}.{name}")


def parse_response(value: JsonValue) -> Response:
    reader = _reader(value, "response", frozenset(("protocolVersion", "kind", "generatedAt", "generationId", "payload", "error")))
    if "protocolVersion" not in reader.value:
        _fail(ErrorCode.PROTOCOL_VERSION_MISSING, "protocolVersion is required")
    version = _protocol_version(reader.field("protocolVersion"))
    generated_at = _timestamp(reader.field("generatedAt"), "response.generatedAt")
    generation_id = GenerationId(_identifier(reader.field("generationId"), "response.generationId"))
    kind = _enum(ResponseKind, reader.field("kind"), "response.kind")
    match kind:  # noqa: MATCH_OK - basedpyright proves this closed union exhaustive
        case ResponseKind.SNAPSHOT:
            _reject_field(reader, "error")
            return _validated(SnapshotResponse(generated_at, generation_id, _snapshot(reader.field("payload")), version))
        case ResponseKind.INVENTORY:
            _reject_field(reader, "error")
            return _validated(InventoryResponse(generated_at, generation_id, _inventory(reader.field("payload")), version))
        case ResponseKind.STAR_RESULT:
            _reject_field(reader, "error")
            return _validated(StarResultResponse(generated_at, generation_id, _star_result(reader.field("payload")), version))
        case ResponseKind.ERROR:  # pragma: no branch - final closed-union case has no fallthrough
            _reject_field(reader, "payload")
            return _validated(ErrorResponse(generated_at, generation_id, _error(reader.field("error"), "response.error"), version))


def _validated(response: Response) -> Response:
    validate_response(response)
    return response


def _snapshot(value: JsonValue) -> SnapshotPayload:
    reader = _reader(value, "snapshot", frozenset(("scanState", "sources", "summary", "items", "findings", "notifications")))
    sources = tuple(_source(entry, "snapshot.sources") for entry in _list(reader.field("sources"), "snapshot.sources"))
    items = tuple(_item(entry, "snapshot.items") for entry in _list(reader.field("items"), "snapshot.items"))
    findings = tuple(_group(entry, "snapshot.findings") for entry in _list(reader.field("findings"), "snapshot.findings"))
    notifications = tuple(_notification(entry, "snapshot.notifications") for entry in _list(reader.field("notifications"), "snapshot.notifications"))
    return SnapshotPayload(_enum(ScanState, reader.field("scanState"), "snapshot.scanState"), sources, _summary(reader.field("summary")), items, findings, notifications)


def _inventory(value: JsonValue) -> InventoryPayload:
    reader = _reader(value, "inventory", frozenset(("source", "total", "items")))
    items = tuple(_item(entry, "inventory.items") for entry in _list(reader.field("items"), "inventory.items"))
    return InventoryPayload(_enum(ItemSource, reader.field("source"), "inventory.source"), _nonnegative_int(reader.field("total"), "inventory.total"), items)


def _star_result(value: JsonValue) -> StarResultPayload:
    reader = _reader(value, "star-result", frozenset(("itemId", "mode")))
    return StarResultPayload(ItemId(_identifier(reader.field("itemId"), "star-result.itemId")), _enum(WatchMode, reader.field("mode"), "star-result.mode"))


def _source(value: JsonValue, path: str) -> SourceHealth:
    reader = _reader(value, path, frozenset(("source", "status", "provenance", "observedAt", "freshUntil", "cause")))
    cause_value = reader.field("cause")
    cause = None if cause_value is None else _error(cause_value, f"{path}.cause")
    return SourceHealth(_enum(SourceName, reader.field("source"), f"{path}.source"), _enum(SourceStatus, reader.field("status"), f"{path}.status"), _enum(Provenance, reader.field("provenance"), f"{path}.provenance"), _timestamp(reader.field("observedAt"), f"{path}.observedAt"), _timestamp(reader.field("freshUntil"), f"{path}.freshUntil"), cause)


def _summary(value: JsonValue) -> Summary:
    reader = _reader(value, "summary", frozenset(("totalUpdates", "watchedUpdates", "securityFindings", "degradedSources")))
    return Summary(_nonnegative_int(reader.field("totalUpdates"), "summary.totalUpdates"), _nonnegative_int(reader.field("watchedUpdates"), "summary.watchedUpdates"), _nonnegative_int(reader.field("securityFindings"), "summary.securityFindings"), _nonnegative_int(reader.field("degradedSources"), "summary.degradedSources"))


def _item(value: JsonValue, path: str) -> NormalizedItem:
    reader = _reader(value, path, frozenset(("id", "source", "label", "installed", "candidate", "watchMode", "watchable", "provenance")))
    return NormalizedItem(ItemId(_identifier(reader.field("id"), f"{path}.id")), _enum(ItemSource, reader.field("source"), f"{path}.source"), _identifier(reader.field("label"), f"{path}.label"), _optional_string(reader.field("installed"), f"{path}.installed"), _optional_string(reader.field("candidate"), f"{path}.candidate"), _enum(WatchMode, reader.field("watchMode"), f"{path}.watchMode"), _bool(reader.field("watchable"), f"{path}.watchable"), _enum(Provenance, reader.field("provenance"), f"{path}.provenance"))


def _group(value: JsonValue, path: str) -> SecurityFindingGroup:
    reader = _reader(value, path, frozenset(("itemId", "findings")))
    return SecurityFindingGroup(ItemId(_identifier(reader.field("itemId"), f"{path}.itemId")), tuple(_finding(entry, f"{path}.findings") for entry in _list(reader.field("findings"), f"{path}.findings")))


def _finding(value: JsonValue, path: str) -> SecurityFinding:
    reader = _reader(value, path, frozenset(("id", "itemId", "advisoryId", "cveIds", "severity", "fixedVersion", "knownExploited", "provenance")))
    cve_ids = tuple(_identifier(entry, f"{path}.cveIds") for entry in _list(reader.field("cveIds"), f"{path}.cveIds"))
    return SecurityFinding(FindingId(_identifier(reader.field("id"), f"{path}.id")), ItemId(_identifier(reader.field("itemId"), f"{path}.itemId")), _identifier(reader.field("advisoryId"), f"{path}.advisoryId"), cve_ids, _enum(Severity, reader.field("severity"), f"{path}.severity"), _optional_string(reader.field("fixedVersion"), f"{path}.fixedVersion"), _bool(reader.field("knownExploited"), f"{path}.knownExploited"), _enum(Provenance, reader.field("provenance"), f"{path}.provenance"))


def _notification(value: JsonValue, path: str) -> NotificationOutcome:
    reader = _reader(value, path, frozenset(("fingerprint", "status")))
    return NotificationOutcome(NotificationFingerprint(_identifier(reader.field("fingerprint"), f"{path}.fingerprint")), _enum(NotificationStatus, reader.field("status"), f"{path}.status"))


def _error(value: JsonValue, path: str) -> ErrorInfo:
    reader = _reader(value, path, frozenset(("code", "message")))
    return ErrorInfo(_enum(ErrorCode, reader.field("code"), f"{path}.code"), _bounded_string(reader.field("message"), f"{path}.message", MAX_ERROR_MESSAGE_LENGTH))


def _reader(value: JsonValue, path: str, fields: frozenset[str]) -> Reader:
    if not is_json_object(value):
        _fail(ErrorCode.INVALID_TYPE, f"{path} must be an object")
    unknown_fields = set(value).difference(fields)
    if unknown_fields:
        _fail(ErrorCode.UNKNOWN_FIELD, f"unknown {path}.{min(unknown_fields)}")
    return Reader(value, path)


def _protocol_version(value: JsonValue) -> ProtocolVersion:
    if not is_exact_int(value):
        _fail(ErrorCode.PROTOCOL_VERSION_INVALID, "protocolVersion must be an exact integer")
    if value > int(PROTOCOL_VERSION):
        _fail(ErrorCode.PROTOCOL_VERSION_FUTURE, "protocolVersion is newer than this helper")
    if value != int(PROTOCOL_VERSION):
        _fail(ErrorCode.PROTOCOL_VERSION_INVALID, "protocolVersion is unsupported")
    return ProtocolVersion(value)


def _timestamp(value: JsonValue, path: str) -> datetime:
    raw = _string(value, path)
    if len(raw) < 21 or raw[10] != "T" or not raw.endswith("Z"):
        _fail(ErrorCode.INVALID_TIMESTAMP, f"{path} must be UTC RFC3339")
    try:
        return datetime.fromisoformat(f"{raw[:-1]}+00:00")
    except ValueError:
        _fail(ErrorCode.INVALID_TIMESTAMP, f"{path} must be UTC RFC3339")


def _enum(enum_type: type[EnumValue], value: JsonValue, path: str) -> EnumValue:
    try:
        return enum_type(_string(value, path))
    except ValueError:
        _fail(ErrorCode.UNKNOWN_ENUM, f"unknown enum at {path}")


def _optional_string(value: JsonValue, path: str) -> str | None:
    return None if value is None else _string(value, path)


def _identifier(value: JsonValue, path: str) -> str:
    return _string(value, path)


def _bounded_string(value: JsonValue, path: str, maximum_length: int) -> str:
    raw = _string(value, path)
    if not raw or len(raw) > maximum_length:
        _fail(ErrorCode.INVALID_TYPE, f"{path} must be a bounded non-empty string")
    return raw


def _string(value: JsonValue, path: str) -> str:
    if is_exact_string(value):
        return value
    _fail(ErrorCode.INVALID_TYPE, f"{path} must be a string")


def _bool(value: JsonValue, path: str) -> bool:
    if is_exact_bool(value):
        return value
    _fail(ErrorCode.INVALID_TYPE, f"{path} must be a boolean")


def _nonnegative_int(value: JsonValue, path: str) -> int:
    if not is_exact_int(value) or value < 0:
        _fail(ErrorCode.INVALID_TYPE, f"{path} must be a non-negative exact integer")
    return value


def _list(value: JsonValue, path: str) -> list[JsonValue]:
    if is_json_list(value):
        return value
    _fail(ErrorCode.INVALID_TYPE, f"{path} must be an array")


def _reject_field(reader: Reader, name: str) -> None:
    if name in reader.value:
        _fail(ErrorCode.INVALID_ENVELOPE, f"response.{name} is incompatible with response.kind")


def _fail(code: ErrorCode, message: str) -> NoReturn:
    raise ProtocolError(ErrorInfo(code, message))
