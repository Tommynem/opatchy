from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .models import (
    ItemId,
    NotificationFingerprint,
    NotificationStatus,
    SourceName,
    WatchMode,
)


class StorageWarning(StrEnum):
    STATE_CORRUPT = "state_corrupt"


class FeedName(StrEnum):
    ARCH_SECURITY = "arch-security"
    CISA_KEV = "cisa-kev"


class StateCorruptError(Exception):
    reason: str

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class StateSchemaIncompatible(Exception):
    schema_version: int

    def __init__(self, schema_version: int) -> None:
        self.schema_version = schema_version
        super().__init__(f"state schema {schema_version} is newer than supported")


class StoragePathError(Exception):
    variable: str

    def __init__(self, variable: str) -> None:
        self.variable = variable
        super().__init__(f"{variable} must be an absolute path")


@dataclass(frozen=True, slots=True)
class WatchRecord:
    item_id: ItemId
    mode: WatchMode
    installed_fingerprint: str | None
    candidate_fingerprint: str | None
    armed: bool


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    fingerprint: NotificationFingerprint
    status: NotificationStatus
    recorded_at: datetime
    lease_token: str | None = None
    lease_expires_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        match self.status:
            case NotificationStatus.PENDING:
                return True
            case (
                NotificationStatus.DELIVERED
                | NotificationStatus.SUPPRESSED
                | NotificationStatus.FAILED
            ):
                return False


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    source: SourceName
    last_success: datetime | None
    backoff_until: datetime | None
    failure_count: int = 0
    permanent_failure: bool = False


@dataclass(frozen=True, slots=True)
class PersistentState:
    watches: tuple[WatchRecord, ...]
    ledger: tuple[LedgerEntry, ...]
    sources: tuple[SourceMetadata, ...]

    @classmethod
    def empty(cls) -> "PersistentState":
        return cls((), (), ())


@dataclass(frozen=True, slots=True)
class StateLoad:
    state: PersistentState
    warning: StorageWarning | None
