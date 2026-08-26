from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum, unique
from typing import Final, NewType, TypeAlias, override

ProtocolVersion = NewType("ProtocolVersion", int)
GenerationId = NewType("GenerationId", str)
GenerationOrder = NewType("GenerationOrder", int)
ItemId = NewType("ItemId", str)
FindingId = NewType("FindingId", str)
NotificationFingerprint = NewType("NotificationFingerprint", str)
PROTOCOL_VERSION: Final = ProtocolVersion(1)


@unique
class SourceStatus(StrEnum):
    OK = "ok"
    NOT_APPLICABLE = "not_applicable"
    MISSING_DEPENDENCY = "missing_dependency"
    OFFLINE = "offline"
    TIMEOUT = "timeout"
    ERROR = "error"
    INVALID = "invalid"
    STALE = "stale"


@unique
class ScanState(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


@unique
class SourceName(StrEnum):
    SECURITY = "security"
    CISA_KEV = "cisa-kev"
    OMARCHY = "omarchy"
    ARCH = "arch"
    AUR = "aur"
    FLATPAK = "flatpak"
    MISE = "mise"


@unique
class SourceScope(StrEnum):
    USER = "user"
    SYSTEM = "system"


@unique
class ItemSource(StrEnum):
    OMARCHY = "omarchy"
    ARCH = "arch"
    AUR = "aur"
    FLATPAK = "flatpak"
    MISE = "mise"


@unique
class WatchMode(StrEnum):
    OFF = "off"
    TEMPORARY = "temporary"
    PERMANENT = "permanent"


@unique
class Severity(StrEnum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@unique
class ArchStatus(StrEnum):
    UNKNOWN = "Unknown"
    VULNERABLE = "Vulnerable"
    TESTING = "Testing"
    FIXED = "Fixed"
    NOT_AFFECTED = "Not affected"


@unique
class KevStatus(StrEnum):
    LISTED = "listed"
    NOT_LISTED = "not_listed"
    UNAVAILABLE = "unavailable"


@unique
class Provenance(StrEnum):
    LIVE = "live"
    CACHE = "cache"
    LAST_GOOD = "last_good"
    FALLBACK = "fallback"


@unique
class NotificationStatus(StrEnum):
    DELIVERED = "delivered"
    PENDING = "pending"
    SUPPRESSED = "suppressed"
    FAILED = "failed"


@unique
class ResponseKind(StrEnum):
    SNAPSHOT = "snapshot"
    INVENTORY = "inventory"
    STAR_RESULT = "star-result"
    ERROR = "error"


@unique
class ErrorCode(StrEnum):
    CLI_USAGE = "CLI_USAGE"
    STATE_UNAVAILABLE = "STATE_UNAVAILABLE"
    INVALID_UTF8 = "INVALID_UTF8"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    MALFORMED_JSON = "MALFORMED_JSON"
    INVALID_TYPE = "INVALID_TYPE"
    MISSING_FIELD = "MISSING_FIELD"
    UNKNOWN_FIELD = "UNKNOWN_FIELD"
    PROTOCOL_VERSION_MISSING = "PROTOCOL_VERSION_MISSING"
    PROTOCOL_VERSION_INVALID = "PROTOCOL_VERSION_INVALID"
    PROTOCOL_VERSION_FUTURE = "PROTOCOL_VERSION_FUTURE"
    UNKNOWN_ENUM = "UNKNOWN_ENUM"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    INVALID_ENVELOPE = "INVALID_ENVELOPE"
    DUPLICATE_ITEM_ID = "DUPLICATE_ITEM_ID"
    DUPLICATE_FINDING_ID = "DUPLICATE_FINDING_ID"
    OUTPUT_TOO_LARGE = "OUTPUT_TOO_LARGE"
    SOURCE_INVALID = "SOURCE_INVALID"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class ErrorInfo:
    code: ErrorCode
    message: str


@dataclass(frozen=True, slots=True)
class ProtocolError(Exception):
    error: ErrorInfo

    @override
    def __str__(self) -> str:
        return f"{self.error.code}: {self.error.message}"


@dataclass(frozen=True, slots=True)
class SourceHealth:
    source: SourceName
    status: SourceStatus
    provenance: Provenance
    observed_at: datetime
    fresh_until: datetime
    cause: ErrorInfo | None
    scopes: tuple["ScopeHealth", ...] = ()


@dataclass(frozen=True, slots=True)
class ScopeHealth:
    scope: SourceScope
    status: SourceStatus
    provenance: Provenance
    observed_at: datetime
    fresh_until: datetime
    cause: ErrorInfo | None


@dataclass(frozen=True, slots=True)
class Summary:
    total_updates: int
    watched_updates: int
    security_findings: int
    degraded_sources: int


@dataclass(frozen=True, slots=True)
class NormalizedItem:
    item_id: ItemId
    source: ItemSource
    label: str
    installed: str | None
    candidate: str | None
    watch_mode: WatchMode
    watchable: bool
    provenance: Provenance
    installed_fingerprint: str | None = None
    candidate_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class SecurityFinding:
    finding_id: FindingId
    item_id: ItemId
    advisory_id: str
    cve_ids: tuple[str, ...]
    severity: Severity
    fixed_version: str | None
    known_exploited: bool
    provenance: Provenance
    status: ArchStatus = ArchStatus.UNKNOWN
    advisory_type: str = "unknown"
    installed_version: str | None = None
    kev_status: KevStatus = KevStatus.UNAVAILABLE
    kev_provenance: Provenance | None = None


@dataclass(frozen=True, slots=True)
class SecurityFindingGroup:
    item_id: ItemId
    findings: tuple[SecurityFinding, ...]


@dataclass(frozen=True, slots=True)
class NotificationOutcome:
    fingerprint: NotificationFingerprint
    status: NotificationStatus


@dataclass(frozen=True, slots=True)
class SnapshotPayload:
    scan_state: ScanState
    sources: tuple[SourceHealth, ...]
    summary: Summary
    items: tuple[NormalizedItem, ...]
    findings: tuple[SecurityFindingGroup, ...]
    notifications: tuple[NotificationOutcome, ...]


@dataclass(frozen=True, slots=True)
class InventoryPayload:
    source: ItemSource
    total: int
    items: tuple[NormalizedItem, ...]


@dataclass(frozen=True, slots=True)
class StarResultPayload:
    item_id: ItemId
    mode: WatchMode


@dataclass(frozen=True, slots=True)
class SnapshotResponse:
    generated_at: datetime
    generation_id: GenerationId
    payload: SnapshotPayload
    protocol_version: ProtocolVersion = PROTOCOL_VERSION


@dataclass(frozen=True, slots=True)
class InventoryResponse:
    generated_at: datetime
    generation_id: GenerationId
    payload: InventoryPayload
    protocol_version: ProtocolVersion = PROTOCOL_VERSION


@dataclass(frozen=True, slots=True)
class StarResultResponse:
    generated_at: datetime
    generation_id: GenerationId
    payload: StarResultPayload
    protocol_version: ProtocolVersion = PROTOCOL_VERSION


@dataclass(frozen=True, slots=True)
class ErrorResponse:
    generated_at: datetime
    generation_id: GenerationId
    error: ErrorInfo
    protocol_version: ProtocolVersion = PROTOCOL_VERSION


Response: TypeAlias = (
    SnapshotResponse | InventoryResponse | StarResultResponse | ErrorResponse
)
