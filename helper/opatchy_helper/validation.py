from typing import NoReturn

from .models import (
    PROTOCOL_VERSION,
    ErrorCode,
    ErrorInfo,
    ErrorResponse,
    InventoryPayload,
    InventoryResponse,
    ItemId,
    ItemSource,
    NormalizedItem,
    ProtocolError,
    ProtocolVersion,
    Response,
    SecurityFindingGroup,
    SnapshotPayload,
    SnapshotResponse,
    SourceHealth,
    SourceName,
    StarResultResponse,
)


MAX_IDENTIFIER_LENGTH = 128
MAX_ERROR_MESSAGE_LENGTH = 512


def validate_response(response: Response) -> None:
    _validate_metadata(response.protocol_version, response.generation_id)
    match response:  # noqa: MATCH_OK - basedpyright proves this closed union exhaustive
        case SnapshotResponse(payload=payload):
            _validate_snapshot(payload)
        case InventoryResponse(payload=payload):
            _validate_inventory(payload)
        case StarResultResponse(payload=payload):
            _validate_identifier(str(payload.item_id), "star-result.itemId")
        case ErrorResponse():  # pragma: no branch - final closed-union case has no fallthrough
            pass


def _validate_metadata(version: ProtocolVersion, generation_id: str) -> None:
    if version > PROTOCOL_VERSION:
        _fail(ErrorCode.PROTOCOL_VERSION_FUTURE, "protocolVersion is newer than this helper")
    if version != PROTOCOL_VERSION:
        _fail(ErrorCode.PROTOCOL_VERSION_INVALID, "protocolVersion is unsupported")
    _validate_identifier(generation_id, "generationId")


def _validate_snapshot(payload: SnapshotPayload) -> None:
    _validate_sources(payload.sources)
    _validate_items(payload.items)
    _validate_groups(payload.findings, payload.items)
    _validate_nonnegative(payload.summary.total_updates, "summary.totalUpdates")
    _validate_nonnegative(payload.summary.watched_updates, "summary.watchedUpdates")
    _validate_nonnegative(payload.summary.security_findings, "summary.securityFindings")
    _validate_nonnegative(payload.summary.degraded_sources, "summary.degradedSources")


def _validate_inventory(payload: InventoryPayload) -> None:
    match payload.source:  # noqa: MATCH_OK - basedpyright proves this closed enum exhaustive
        case ItemSource.ARCH | ItemSource.AUR | ItemSource.FLATPAK | ItemSource.MISE:
            pass
        case ItemSource.OMARCHY:  # pragma: no branch - _fail never continues to validation
            _fail(ErrorCode.INVALID_ENVELOPE, "inventory source is unsupported")
    _validate_nonnegative(payload.total, "inventory.total")
    if payload.total != len(payload.items):
        _fail(ErrorCode.INVALID_ENVELOPE, "inventory.total does not match inventory.items")
    _validate_items(payload.items)
    if any(item.source is not payload.source for item in payload.items):
        _fail(ErrorCode.INVALID_ENVELOPE, "inventory items must match inventory.source")


def _validate_sources(sources: tuple[SourceHealth, ...]) -> None:
    source_names = {source.source for source in sources}
    if len(source_names) != len(sources) or source_names != set(SourceName):
        _fail(ErrorCode.INVALID_ENVELOPE, "snapshot.sources must contain each source once")


def _validate_items(items: tuple[NormalizedItem, ...]) -> None:
    item_ids = {item.item_id for item in items}
    if len(item_ids) != len(items):
        _fail(ErrorCode.DUPLICATE_ITEM_ID, "item IDs must be unique")
    for item in items:
        _validate_identifier(str(item.item_id), "item.id")
        _validate_identifier(item.label, "item.label")


def _validate_groups(
    groups: tuple[SecurityFindingGroup, ...],
    items: tuple[NormalizedItem, ...],
) -> None:
    group_ids = {group.item_id for group in groups}
    if len(group_ids) != len(groups):
        _fail(ErrorCode.INVALID_ENVELOPE, "security finding groups must be unique")
    source_by_item_id = {item.item_id: item.source for item in items}
    for group in groups:
        _validate_group(group, source_by_item_id)


def _validate_group(group: SecurityFindingGroup, source_by_item_id: dict[ItemId, ItemSource]) -> None:
    source = source_by_item_id.get(group.item_id)
    if source is None or not _is_arch_source(source):
        _fail(ErrorCode.INVALID_ENVELOPE, "security findings must attach to an Arch item")
    if not group.findings:
        _fail(ErrorCode.INVALID_ENVELOPE, "security finding groups cannot be empty")
    for finding in group.findings:
        if finding.item_id != group.item_id:
            _fail(ErrorCode.INVALID_ENVELOPE, "security finding ID does not match its group")
        _validate_identifier(str(finding.finding_id), "finding.id")
        _validate_identifier(finding.advisory_id, "finding.advisoryId")


def _is_arch_source(source: ItemSource) -> bool:
    match source:  # noqa: MATCH_OK - basedpyright proves this closed enum exhaustive
        case ItemSource.ARCH:
            return True
        case ItemSource.OMARCHY | ItemSource.AUR | ItemSource.FLATPAK | ItemSource.MISE:  # pragma: no branch - final enum case exits
            return False


def _validate_identifier(value: str, path: str, maximum_length: int = MAX_IDENTIFIER_LENGTH) -> None:
    if not value or len(value) > maximum_length:
        _fail(ErrorCode.INVALID_TYPE, f"{path} must be a bounded non-empty string")


def _validate_nonnegative(value: int, path: str) -> None:
    if value < 0:
        _fail(ErrorCode.INVALID_TYPE, f"{path} must be a non-negative exact integer")


def _fail(code: ErrorCode, message: str) -> NoReturn:
    raise ProtocolError(ErrorInfo(code, message))
