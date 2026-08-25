from datetime import datetime, timedelta
from typing import NoReturn, TypeAlias, assert_never

from .models import (
    PROTOCOL_VERSION,
    ErrorCode,
    ErrorInfo,
    ErrorResponse,
    InventoryPayload,
    InventoryResponse,
    NormalizedItem,
    NotificationOutcome,
    ProtocolError,
    ProtocolVersion,
    Response,
    ResponseKind,
    SecurityFinding,
    SecurityFindingGroup,
    SnapshotPayload,
    SnapshotResponse,
    SourceHealth,
    StarResultPayload,
    StarResultResponse,
    Summary,
)

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


def response_value(response: Response) -> JsonObject:
    match response:
        case SnapshotResponse(generated_at, generation_id, payload, protocol_version):
            return {"generatedAt": _timestamp(generated_at), "generationId": str(generation_id), "kind": ResponseKind.SNAPSHOT, "payload": _snapshot(payload), "protocolVersion": _version(protocol_version)}
        case InventoryResponse(generated_at, generation_id, payload, protocol_version):
            return {"generatedAt": _timestamp(generated_at), "generationId": str(generation_id), "kind": ResponseKind.INVENTORY, "payload": _inventory(payload), "protocolVersion": _version(protocol_version)}
        case StarResultResponse(generated_at, generation_id, payload, protocol_version):
            return {"generatedAt": _timestamp(generated_at), "generationId": str(generation_id), "kind": ResponseKind.STAR_RESULT, "payload": _star_result(payload), "protocolVersion": _version(protocol_version)}
        case ErrorResponse(generated_at, generation_id, error, protocol_version):
            return {"error": _error(error), "generatedAt": _timestamp(generated_at), "generationId": str(generation_id), "kind": ResponseKind.ERROR, "protocolVersion": _version(protocol_version)}
        case unreachable:
            assert_never(unreachable)


def _snapshot(payload: SnapshotPayload) -> JsonObject:
    return {"findings": [_finding_group(group) for group in payload.findings], "items": [_item(item) for item in payload.items], "notifications": [_notification(outcome) for outcome in payload.notifications], "scanState": payload.scan_state, "sources": [_source(source) for source in payload.sources], "summary": _summary(payload.summary)}


def _inventory(payload: InventoryPayload) -> JsonObject:
    return {"items": [_item(item) for item in payload.items], "source": payload.source, "total": payload.total}


def _star_result(payload: StarResultPayload) -> JsonObject:
    return {"itemId": str(payload.item_id), "mode": payload.mode}


def _source(source: SourceHealth) -> JsonObject:
    return {"cause": None if source.cause is None else _error(source.cause), "freshUntil": _timestamp(source.fresh_until), "observedAt": _timestamp(source.observed_at), "provenance": source.provenance, "source": source.source, "status": source.status}


def _summary(summary: Summary) -> JsonObject:
    return {"degradedSources": summary.degraded_sources, "securityFindings": summary.security_findings, "totalUpdates": summary.total_updates, "watchedUpdates": summary.watched_updates}


def _item(item: NormalizedItem) -> JsonObject:
    return {"candidate": item.candidate, "id": str(item.item_id), "installed": item.installed, "label": item.label, "provenance": item.provenance, "source": item.source, "watchMode": item.watch_mode, "watchable": item.watchable}


def _finding(finding: SecurityFinding) -> JsonObject:
    return {"advisoryId": finding.advisory_id, "cveIds": list(finding.cve_ids), "fixedVersion": finding.fixed_version, "id": str(finding.finding_id), "itemId": str(finding.item_id), "knownExploited": finding.known_exploited, "provenance": finding.provenance, "severity": finding.severity}


def _finding_group(group: SecurityFindingGroup) -> JsonObject:
    return {"findings": [_finding(finding) for finding in group.findings], "itemId": str(group.item_id)}


def _notification(outcome: NotificationOutcome) -> JsonObject:
    return {"fingerprint": str(outcome.fingerprint), "status": outcome.status}


def _error(error: ErrorInfo) -> JsonObject:
    return {"code": error.code, "message": error.message}


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timedelta():
        _fail(ErrorCode.INVALID_TIMESTAMP, "timestamps must be UTC")
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _version(value: ProtocolVersion) -> int:
    if type(value) is not int:
        _fail(ErrorCode.PROTOCOL_VERSION_INVALID, "protocolVersion must be an exact integer")
    if value > int(PROTOCOL_VERSION):
        _fail(ErrorCode.PROTOCOL_VERSION_FUTURE, "protocolVersion is newer than this helper")
    if value != int(PROTOCOL_VERSION):
        _fail(ErrorCode.PROTOCOL_VERSION_INVALID, "protocolVersion is unsupported")
    return value


def _fail(code: ErrorCode, message: str) -> NoReturn:
    raise ProtocolError(ErrorInfo(code, message))
