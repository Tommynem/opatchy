from .json_value import JsonValue
from .models import (
    ErrorCode,
    ErrorInfo,
    FindingId,
    InventoryPayload,
    ItemId,
    ItemSource,
    NormalizedItem,
    NotificationFingerprint,
    NotificationOutcome,
    NotificationStatus,
    Provenance,
    ScanState,
    SecurityFinding,
    SecurityFindingGroup,
    Severity,
    SnapshotPayload,
    SourceHealth,
    SourceName,
    SourceStatus,
    StarResultPayload,
    Summary,
    WatchMode,
)
from .parser_fields import (
    boolean,
    bounded_string,
    enum,
    identifier,
    list_value,
    nonnegative_int,
    optional_string,
    reader,
    timestamp,
)
from .validation import MAX_ERROR_MESSAGE_LENGTH


def parse_snapshot(value: JsonValue) -> SnapshotPayload:
    reader_value = reader(
        value,
        "snapshot",
        frozenset(
            ("scanState", "sources", "summary", "items", "findings", "notifications")
        ),
    )
    sources = tuple(
        _source(entry, "snapshot.sources")
        for entry in list_value(reader_value.field("sources"), "snapshot.sources")
    )
    items = tuple(
        _item(entry, "snapshot.items")
        for entry in list_value(reader_value.field("items"), "snapshot.items")
    )
    findings = tuple(
        _group(entry, "snapshot.findings")
        for entry in list_value(reader_value.field("findings"), "snapshot.findings")
    )
    notifications = tuple(
        _notification(entry, "snapshot.notifications")
        for entry in list_value(
            reader_value.field("notifications"), "snapshot.notifications"
        )
    )
    return SnapshotPayload(
        enum(ScanState, reader_value.field("scanState"), "snapshot.scanState"),
        sources,
        _summary(reader_value.field("summary")),
        items,
        findings,
        notifications,
    )


def parse_inventory(value: JsonValue) -> InventoryPayload:
    reader_value = reader(value, "inventory", frozenset(("source", "total", "items")))
    items = tuple(
        _item(entry, "inventory.items")
        for entry in list_value(reader_value.field("items"), "inventory.items")
    )
    return InventoryPayload(
        enum(ItemSource, reader_value.field("source"), "inventory.source"),
        nonnegative_int(reader_value.field("total"), "inventory.total"),
        items,
    )


def parse_star_result(value: JsonValue) -> StarResultPayload:
    reader_value = reader(value, "star-result", frozenset(("itemId", "mode")))
    return StarResultPayload(
        ItemId(identifier(reader_value.field("itemId"), "star-result.itemId")),
        enum(WatchMode, reader_value.field("mode"), "star-result.mode"),
    )


def parse_error(value: JsonValue, path: str) -> ErrorInfo:
    reader_value = reader(value, path, frozenset(("code", "message")))
    return ErrorInfo(
        enum(ErrorCode, reader_value.field("code"), f"{path}.code"),
        bounded_string(
            reader_value.field("message"), f"{path}.message", MAX_ERROR_MESSAGE_LENGTH
        ),
    )


def _source(value: JsonValue, path: str) -> SourceHealth:
    reader_value = reader(
        value,
        path,
        frozenset(
            ("source", "status", "provenance", "observedAt", "freshUntil", "cause")
        ),
    )
    cause_value = reader_value.field("cause")
    cause = None if cause_value is None else parse_error(cause_value, f"{path}.cause")
    return SourceHealth(
        enum(SourceName, reader_value.field("source"), f"{path}.source"),
        enum(SourceStatus, reader_value.field("status"), f"{path}.status"),
        enum(Provenance, reader_value.field("provenance"), f"{path}.provenance"),
        timestamp(reader_value.field("observedAt"), f"{path}.observedAt"),
        timestamp(reader_value.field("freshUntil"), f"{path}.freshUntil"),
        cause,
    )


def _summary(value: JsonValue) -> Summary:
    reader_value = reader(
        value,
        "summary",
        frozenset(
            ("totalUpdates", "watchedUpdates", "securityFindings", "degradedSources")
        ),
    )
    return Summary(
        nonnegative_int(reader_value.field("totalUpdates"), "summary.totalUpdates"),
        nonnegative_int(reader_value.field("watchedUpdates"), "summary.watchedUpdates"),
        nonnegative_int(
            reader_value.field("securityFindings"), "summary.securityFindings"
        ),
        nonnegative_int(
            reader_value.field("degradedSources"), "summary.degradedSources"
        ),
    )


def _item(value: JsonValue, path: str) -> NormalizedItem:
    reader_value = reader(
        value,
        path,
        frozenset(
            (
                "id",
                "source",
                "label",
                "installed",
                "candidate",
                "watchMode",
                "watchable",
                "provenance",
            )
        ),
    )
    return NormalizedItem(
        ItemId(identifier(reader_value.field("id"), f"{path}.id")),
        enum(ItemSource, reader_value.field("source"), f"{path}.source"),
        identifier(reader_value.field("label"), f"{path}.label"),
        optional_string(reader_value.field("installed"), f"{path}.installed"),
        optional_string(reader_value.field("candidate"), f"{path}.candidate"),
        enum(WatchMode, reader_value.field("watchMode"), f"{path}.watchMode"),
        boolean(reader_value.field("watchable"), f"{path}.watchable"),
        enum(Provenance, reader_value.field("provenance"), f"{path}.provenance"),
    )


def _group(value: JsonValue, path: str) -> SecurityFindingGroup:
    reader_value = reader(value, path, frozenset(("itemId", "findings")))
    return SecurityFindingGroup(
        ItemId(identifier(reader_value.field("itemId"), f"{path}.itemId")),
        tuple(
            _finding(entry, f"{path}.findings")
            for entry in list_value(reader_value.field("findings"), f"{path}.findings")
        ),
    )


def _finding(value: JsonValue, path: str) -> SecurityFinding:
    reader_value = reader(
        value,
        path,
        frozenset(
            (
                "id",
                "itemId",
                "advisoryId",
                "cveIds",
                "severity",
                "fixedVersion",
                "knownExploited",
                "provenance",
            )
        ),
    )
    cve_ids = tuple(
        identifier(entry, f"{path}.cveIds")
        for entry in list_value(reader_value.field("cveIds"), f"{path}.cveIds")
    )
    return SecurityFinding(
        FindingId(identifier(reader_value.field("id"), f"{path}.id")),
        ItemId(identifier(reader_value.field("itemId"), f"{path}.itemId")),
        identifier(reader_value.field("advisoryId"), f"{path}.advisoryId"),
        cve_ids,
        enum(Severity, reader_value.field("severity"), f"{path}.severity"),
        optional_string(reader_value.field("fixedVersion"), f"{path}.fixedVersion"),
        boolean(reader_value.field("knownExploited"), f"{path}.knownExploited"),
        enum(Provenance, reader_value.field("provenance"), f"{path}.provenance"),
    )


def _notification(value: JsonValue, path: str) -> NotificationOutcome:
    reader_value = reader(value, path, frozenset(("fingerprint", "status")))
    return NotificationOutcome(
        NotificationFingerprint(
            identifier(reader_value.field("fingerprint"), f"{path}.fingerprint")
        ),
        enum(NotificationStatus, reader_value.field("status"), f"{path}.status"),
    )
