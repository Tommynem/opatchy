from datetime import datetime, timedelta
from typing import assert_never

from .json_value import JsonObject
from .models import (
    ErrorCode,
    ErrorInfo,
    ErrorResponse,
    InventoryPayload,
    InventoryResponse,
    NormalizedItem,
    NotificationOutcome,
    ProtocolError,
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
from .validation import validate_response


def response_value(response: Response) -> JsonObject:
    validate_response(response)
    match response:
        case SnapshotResponse(
            generated_at=generated_at,
            generation_id=generation_id,
            payload=payload,
            protocol_version=protocol_version,
        ):
            return _envelope(
                generated_at,
                str(generation_id),
                ResponseKind.SNAPSHOT,
                _snapshot(payload),
                int(protocol_version),
            )
        case InventoryResponse(
            generated_at=generated_at,
            generation_id=generation_id,
            payload=payload,
            protocol_version=protocol_version,
        ):
            return _envelope(
                generated_at,
                str(generation_id),
                ResponseKind.INVENTORY,
                _inventory(payload),
                int(protocol_version),
            )
        case StarResultResponse(
            generated_at=generated_at,
            generation_id=generation_id,
            payload=payload,
            protocol_version=protocol_version,
        ):
            return _envelope(
                generated_at,
                str(generation_id),
                ResponseKind.STAR_RESULT,
                _star_result(payload),
                int(protocol_version),
            )
        case ErrorResponse(
            generated_at=generated_at,
            generation_id=generation_id,
            error=error,
            protocol_version=protocol_version,
        ):
            return _error_envelope(
                generated_at,
                str(generation_id),
                error,
                int(protocol_version),
            )
    assert_never(response)


def _envelope(
    generated_at: datetime,
    generation_id: str,
    kind: ResponseKind,
    payload: JsonObject,
    version: int,
) -> JsonObject:
    return {
        "generatedAt": _timestamp(generated_at),
        "generationId": generation_id,
        "kind": kind,
        "payload": payload,
        "protocolVersion": version,
    }


def _error_envelope(
    generated_at: datetime, generation_id: str, error: ErrorInfo, version: int
) -> JsonObject:
    return {
        "error": _error(error),
        "generatedAt": _timestamp(generated_at),
        "generationId": generation_id,
        "kind": ResponseKind.ERROR,
        "protocolVersion": version,
    }


def _snapshot(payload: SnapshotPayload) -> JsonObject:
    return {
        "findings": [_group(group) for group in payload.findings],
        "items": [_item(item) for item in payload.items],
        "notifications": [_notification(outcome) for outcome in payload.notifications],
        "scanState": payload.scan_state,
        "sources": [_source(source) for source in payload.sources],
        "summary": _summary(payload.summary),
    }


def _inventory(payload: InventoryPayload) -> JsonObject:
    return {
        "items": [_item(item) for item in payload.items],
        "source": payload.source,
        "total": payload.total,
    }


def _star_result(payload: StarResultPayload) -> JsonObject:
    return {"itemId": str(payload.item_id), "mode": payload.mode}


def _source(source: SourceHealth) -> JsonObject:
    return {
        "cause": None if source.cause is None else _error(source.cause),
        "freshUntil": _timestamp(source.fresh_until),
        "observedAt": _timestamp(source.observed_at),
        "provenance": source.provenance,
        "source": source.source,
        "status": source.status,
    }


def _summary(summary: Summary) -> JsonObject:
    return {
        "degradedSources": summary.degraded_sources,
        "securityFindings": summary.security_findings,
        "totalUpdates": summary.total_updates,
        "watchedUpdates": summary.watched_updates,
    }


def _item(item: NormalizedItem) -> JsonObject:
    return {
        "candidate": item.candidate,
        "id": str(item.item_id),
        "installed": item.installed,
        "label": item.label,
        "provenance": item.provenance,
        "source": item.source,
        "watchMode": item.watch_mode,
        "watchable": item.watchable,
    }


def _group(group: SecurityFindingGroup) -> JsonObject:
    return {
        "findings": [_finding(finding) for finding in group.findings],
        "itemId": str(group.item_id),
    }


def _finding(finding: SecurityFinding) -> JsonObject:
    return {
        "advisoryId": finding.advisory_id,
        "cveIds": list(finding.cve_ids),
        "fixedVersion": finding.fixed_version,
        "id": str(finding.finding_id),
        "itemId": str(finding.item_id),
        "knownExploited": finding.known_exploited,
        "provenance": finding.provenance,
        "severity": finding.severity,
    }


def _notification(outcome: NotificationOutcome) -> JsonObject:
    return {"fingerprint": str(outcome.fingerprint), "status": outcome.status}


def _error(error: ErrorInfo) -> JsonObject:
    return {"code": error.code, "message": error.message}


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timedelta():
        raise ProtocolError(
            ErrorInfo(ErrorCode.INVALID_TIMESTAMP, "timestamps must be UTC")
        )
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
