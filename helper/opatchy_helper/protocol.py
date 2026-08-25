from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
from typing import Final, NoReturn, TypeAlias, TypeGuard, TypeVar, assert_never

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
    ProtocolVersion,
    Provenance,
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
    StarResultResponse,
    StarResultPayload,
    Summary,
    WatchMode,
)
from .models import ProtocolError
from .wire import response_value


MAX_PROTOCOL_BYTES: Final = 5 * 1024 * 1024
MAX_GENERATION_ID_LENGTH: Final = 128
MAX_ERROR_MESSAGE_LENGTH: Final = 512
JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
EnumValue = TypeVar("EnumValue", bound=StrEnum)


@dataclass(frozen=True, slots=True)
class _Reader:
    value: JsonObject
    path: str

    def field(self, name: str) -> JsonValue:
        try:
            return self.value[name]
        except KeyError:
            _fail(ErrorCode.MISSING_FIELD, f"missing {self.path}.{name}")


def encode_response(response: SnapshotResponse | InventoryResponse | StarResultResponse | ErrorResponse) -> bytes:
    encoded = json.dumps(
        response_value(response),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    if len(encoded) >= MAX_PROTOCOL_BYTES:
        _fail(ErrorCode.OUTPUT_TOO_LARGE, "encoded response reaches the five MiB limit")
    return encoded


def decode_response(raw: bytes) -> SnapshotResponse | InventoryResponse | StarResultResponse | ErrorResponse:
    if len(raw) >= MAX_PROTOCOL_BYTES:
        _fail(ErrorCode.PAYLOAD_TOO_LARGE, "input reaches the five MiB limit")
    try:
        decoded_text = raw.decode("utf-8")
    except UnicodeDecodeError:
        _fail(ErrorCode.INVALID_UTF8, "input is not UTF-8")
    try:
        decoded: JsonValue = json.loads(decoded_text)
    except json.JSONDecodeError:
        _fail(ErrorCode.MALFORMED_JSON, "input is not valid JSON")
    root = _reader(decoded, "response", frozenset(("protocolVersion", "kind", "generatedAt", "generationId", "payload", "error")))
    if "protocolVersion" not in root.value:
        _fail(ErrorCode.PROTOCOL_VERSION_MISSING, "protocolVersion is required")
    version = _protocol_version(root.field("protocolVersion"))
    generated_at = _timestamp(root.field("generatedAt"), "response.generatedAt")
    generation_id = GenerationId(_identifier(root.field("generationId"), "response.generationId"))
    kind = _enum(ResponseKind, root.field("kind"), "response.kind")
    match kind:
        case ResponseKind.SNAPSHOT:
            _reject_field(root, "error")
            return SnapshotResponse(generated_at, generation_id, _snapshot(root.field("payload")), version)
        case ResponseKind.INVENTORY:
            _reject_field(root, "error")
            return InventoryResponse(generated_at, generation_id, _inventory(root.field("payload")), version)
        case ResponseKind.STAR_RESULT:
            _reject_field(root, "error")
            return StarResultResponse(generated_at, generation_id, _star_result(root.field("payload")), version)
        case ResponseKind.ERROR:
            _reject_field(root, "payload")
            return ErrorResponse(generated_at, generation_id, _error_info(root.field("error"), "response.error"), version)
        case unreachable:
            assert_never(unreachable)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _snapshot(value: JsonValue) -> SnapshotPayload:
    reader = _reader(value, "snapshot", frozenset(("scanState", "sources", "summary", "items", "findings", "notifications")))
    sources = tuple(_source_health(entry, "snapshot.sources") for entry in _list(reader.field("sources"), "snapshot.sources"))
    items = tuple(_item(entry, "snapshot.items") for entry in _list(reader.field("items"), "snapshot.items"))
    findings = tuple(_finding_group(entry, "snapshot.findings") for entry in _list(reader.field("findings"), "snapshot.findings"))
    notifications = tuple(_notification(entry, "snapshot.notifications") for entry in _list(reader.field("notifications"), "snapshot.notifications"))
    _validate_sources(sources)
    _validate_unique_item_ids(items)
    _validate_security_groups(findings, items)
    return SnapshotPayload(_enum(ScanState, reader.field("scanState"), "snapshot.scanState"), sources, _summary(reader.field("summary")), items, findings, notifications)


def _inventory(value: JsonValue) -> InventoryPayload:
    reader = _reader(value, "inventory", frozenset(("source", "total", "items")))
    items = tuple(_item(entry, "inventory.items") for entry in _list(reader.field("items"), "inventory.items"))
    total = _nonnegative_int(reader.field("total"), "inventory.total")
    if total != len(items):
        _fail(ErrorCode.INVALID_ENVELOPE, "inventory.total does not match inventory.items")
    _validate_unique_item_ids(items)
    return InventoryPayload(_enum(ItemSource, reader.field("source"), "inventory.source"), total, items)


def _star_result(value: JsonValue) -> StarResultPayload:
    reader = _reader(value, "star-result", frozenset(("itemId", "mode")))
    return StarResultPayload(ItemId(_identifier(reader.field("itemId"), "star-result.itemId")), _enum(WatchMode, reader.field("mode"), "star-result.mode"))


def _source_health(value: JsonValue, path: str) -> SourceHealth:
    reader = _reader(value, path, frozenset(("source", "status", "provenance", "observedAt", "freshUntil", "cause")))
    cause_value = reader.field("cause")
    cause = None if cause_value is None else _error_info(cause_value, f"{path}.cause")
    return SourceHealth(_enum(SourceName, reader.field("source"), f"{path}.source"), _enum(SourceStatus, reader.field("status"), f"{path}.status"), _enum(Provenance, reader.field("provenance"), f"{path}.provenance"), _timestamp(reader.field("observedAt"), f"{path}.observedAt"), _timestamp(reader.field("freshUntil"), f"{path}.freshUntil"), cause)


def _summary(value: JsonValue) -> Summary:
    reader = _reader(value, "summary", frozenset(("totalUpdates", "watchedUpdates", "securityFindings", "degradedSources")))
    return Summary(_nonnegative_int(reader.field("totalUpdates"), "summary.totalUpdates"), _nonnegative_int(reader.field("watchedUpdates"), "summary.watchedUpdates"), _nonnegative_int(reader.field("securityFindings"), "summary.securityFindings"), _nonnegative_int(reader.field("degradedSources"), "summary.degradedSources"))


def _item(value: JsonValue, path: str) -> NormalizedItem:
    reader = _reader(value, path, frozenset(("id", "source", "label", "installed", "candidate", "watchMode", "watchable", "provenance")))
    return NormalizedItem(ItemId(_identifier(reader.field("id"), f"{path}.id")), _enum(ItemSource, reader.field("source"), f"{path}.source"), _identifier(reader.field("label"), f"{path}.label"), _optional_string(reader.field("installed"), f"{path}.installed"), _optional_string(reader.field("candidate"), f"{path}.candidate"), _enum(WatchMode, reader.field("watchMode"), f"{path}.watchMode"), _bool(reader.field("watchable"), f"{path}.watchable"), _enum(Provenance, reader.field("provenance"), f"{path}.provenance"))


def _finding(value: JsonValue, path: str) -> SecurityFinding:
    reader = _reader(value, path, frozenset(("id", "itemId", "advisoryId", "cveIds", "severity", "fixedVersion", "knownExploited", "provenance")))
    cve_ids = tuple(_identifier(entry, f"{path}.cveIds") for entry in _list(reader.field("cveIds"), f"{path}.cveIds"))
    return SecurityFinding(FindingId(_identifier(reader.field("id"), f"{path}.id")), ItemId(_identifier(reader.field("itemId"), f"{path}.itemId")), _identifier(reader.field("advisoryId"), f"{path}.advisoryId"), cve_ids, _enum(Severity, reader.field("severity"), f"{path}.severity"), _optional_string(reader.field("fixedVersion"), f"{path}.fixedVersion"), _bool(reader.field("knownExploited"), f"{path}.knownExploited"), _enum(Provenance, reader.field("provenance"), f"{path}.provenance"))


def _finding_group(value: JsonValue, path: str) -> SecurityFindingGroup:
    reader = _reader(value, path, frozenset(("itemId", "findings")))
    return SecurityFindingGroup(ItemId(_identifier(reader.field("itemId"), f"{path}.itemId")), tuple(_finding(entry, f"{path}.findings") for entry in _list(reader.field("findings"), f"{path}.findings")))


def _notification(value: JsonValue, path: str) -> NotificationOutcome:
    reader = _reader(value, path, frozenset(("fingerprint", "status")))
    return NotificationOutcome(NotificationFingerprint(_identifier(reader.field("fingerprint"), f"{path}.fingerprint")), _enum(NotificationStatus, reader.field("status"), f"{path}.status"))


def _error_info(value: JsonValue, path: str) -> ErrorInfo:
    reader = _reader(value, path, frozenset(("code", "message")))
    return ErrorInfo(_enum(ErrorCode, reader.field("code"), f"{path}.code"), _bounded_string(reader.field("message"), f"{path}.message", MAX_ERROR_MESSAGE_LENGTH))


def _reader(value: JsonValue, path: str, fields: frozenset[str]) -> _Reader:
    if not _is_json_object(value):
        _fail(ErrorCode.INVALID_TYPE, f"{path} must be an object")
    unknown_fields = set(value).difference(fields)
    if unknown_fields:
        _fail(ErrorCode.UNKNOWN_FIELD, f"unknown {path}.{min(unknown_fields)}")
    return _Reader(value, path)


def _protocol_version(value: JsonValue) -> ProtocolVersion:
    if not _is_exact_int(value):
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
        parsed = datetime.fromisoformat(f"{raw[:-1]}+00:00")
    except ValueError:
        _fail(ErrorCode.INVALID_TIMESTAMP, f"{path} must be UTC RFC3339")
    return parsed


def _enum(enum_type: type[EnumValue], value: JsonValue, path: str) -> EnumValue:
    raw = _string(value, path)
    try:
        return enum_type(raw)
    except ValueError:
        _fail(ErrorCode.UNKNOWN_ENUM, f"unknown enum at {path}")


def _optional_string(value: JsonValue, path: str) -> str | None:
    return None if value is None else _string(value, path)


def _identifier(value: JsonValue, path: str) -> str:
    return _bounded_string(value, path, MAX_GENERATION_ID_LENGTH)


def _bounded_string(value: JsonValue, path: str, maximum_length: int) -> str:
    raw = _string(value, path)
    if not raw or len(raw) > maximum_length:
        _fail(ErrorCode.INVALID_TYPE, f"{path} must be a bounded non-empty string")
    return raw


def _string(value: JsonValue, path: str) -> str:
    if _is_exact_str(value):
        return value
    _fail(ErrorCode.INVALID_TYPE, f"{path} must be a string")


def _bool(value: JsonValue, path: str) -> bool:
    if _is_exact_bool(value):
        return value
    _fail(ErrorCode.INVALID_TYPE, f"{path} must be a boolean")


def _nonnegative_int(value: JsonValue, path: str) -> int:
    if not _is_exact_int(value) or value < 0:
        _fail(ErrorCode.INVALID_TYPE, f"{path} must be a non-negative exact integer")
    return value


def _list(value: JsonValue, path: str) -> list[JsonValue]:
    if _is_json_list(value):
        return value
    _fail(ErrorCode.INVALID_TYPE, f"{path} must be an array")


def _validate_sources(sources: tuple[SourceHealth, ...]) -> None:
    source_names = {source.source for source in sources}
    if len(source_names) != len(sources) or source_names != set(SourceName):
        _fail(ErrorCode.INVALID_ENVELOPE, "snapshot.sources must contain each source once")


def _validate_unique_item_ids(items: tuple[NormalizedItem, ...]) -> None:
    item_ids = {item.item_id for item in items}
    if len(item_ids) != len(items):
        _fail(ErrorCode.DUPLICATE_ITEM_ID, "item IDs must be unique")


def _validate_security_groups(
    groups: tuple[SecurityFindingGroup, ...],
    items: tuple[NormalizedItem, ...],
) -> None:
    group_ids = {group.item_id for group in groups}
    if len(group_ids) != len(groups):
        _fail(ErrorCode.INVALID_ENVELOPE, "security finding groups must be unique")
    for group in groups:
        matching_items = tuple(item for item in items if item.item_id == group.item_id)
        if len(matching_items) != 1 or not _is_arch_source(matching_items[0].source):
            _fail(ErrorCode.INVALID_ENVELOPE, "security findings must attach to an Arch item")
        if any(finding.item_id != group.item_id for finding in group.findings):
            _fail(ErrorCode.INVALID_ENVELOPE, "security finding ID does not match its group")


def _is_arch_source(source: ItemSource) -> bool:
    match source:
        case ItemSource.ARCH:
            return True
        case ItemSource.OMARCHY | ItemSource.AUR | ItemSource.FLATPAK | ItemSource.MISE:
            return False
        case unreachable:
            assert_never(unreachable)


def _reject_field(reader: _Reader, name: str) -> None:
    if name in reader.value:
        _fail(ErrorCode.INVALID_ENVELOPE, f"response.{name} is incompatible with response.kind")


def _is_json_object(value: JsonValue) -> TypeGuard[JsonObject]:
    return type(value) is dict


def _is_json_list(value: JsonValue) -> TypeGuard[list[JsonValue]]:
    return type(value) is list


def _is_exact_str(value: JsonValue) -> TypeGuard[str]:
    return type(value) is str


def _is_exact_bool(value: JsonValue) -> TypeGuard[bool]:
    return type(value) is bool


def _is_exact_int(value: JsonValue) -> TypeGuard[int]:
    return type(value) is int


def _fail(code: ErrorCode, message: str) -> NoReturn:
    raise ProtocolError(ErrorInfo(code, message))
