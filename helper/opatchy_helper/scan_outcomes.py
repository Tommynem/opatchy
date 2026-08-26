from dataclasses import dataclass

from .adapters.arch import ArchFailure
from .models import (
    ErrorCode,
    ErrorInfo,
    NormalizedItem,
    Provenance,
    SecurityFindingGroup,
    SourceName,
    SourceScope,
    SourceStatus,
)


@dataclass(frozen=True, slots=True)
class SourceOutcome:
    source: SourceName
    scope: SourceScope | None
    status: SourceStatus
    provenance: Provenance
    items: tuple[NormalizedItem, ...]
    findings: tuple[SecurityFindingGroup, ...]
    cause: ErrorInfo | None
    permanent: bool
    applicable: bool

    @property
    def key(self) -> str:
        match self.scope:
            case None:
                return self.source.value
            case scope:
                return f"{self.source.value}:{scope.value}"


def successful(outcome: SourceOutcome) -> bool:
    match outcome.status:
        case SourceStatus.OK | SourceStatus.NOT_APPLICABLE:
            return True
        case (
            SourceStatus.MISSING_DEPENDENCY
            | SourceStatus.OFFLINE
            | SourceStatus.TIMEOUT
            | SourceStatus.ERROR
            | SourceStatus.INVALID
            | SourceStatus.STALE
        ):
            return False


def from_status(
    source: SourceName,
    status: SourceStatus,
    items: tuple[NormalizedItem, ...],
    findings: tuple[SecurityFindingGroup, ...],
    diagnostic: str | None,
) -> SourceOutcome:
    match status:
        case SourceStatus.OK:
            return current(source, items, Provenance.LIVE, findings)
        case SourceStatus.NOT_APPLICABLE:
            return not_applicable(source)
        case SourceStatus.MISSING_DEPENDENCY | SourceStatus.INVALID:
            return failure(source, status, diagnostic or status.value, True, True)
        case (
            SourceStatus.TIMEOUT
            | SourceStatus.OFFLINE
            | SourceStatus.ERROR
            | SourceStatus.STALE
        ):
            return failure(source, status, diagnostic or status.value, False, True)


def arch_failure(
    source: SourceName, failure_kind: ArchFailure, detail: str, applicable: bool
) -> SourceOutcome:
    match failure_kind:
        case ArchFailure.COMMAND_MISSING:
            return failure(
                source, SourceStatus.MISSING_DEPENDENCY, detail, True, applicable
            )
        case ArchFailure.COMMAND_TIMED_OUT:
            return failure(source, SourceStatus.TIMEOUT, detail, False, applicable)
        case (
            ArchFailure.MALFORMED_ROW
            | ArchFailure.DUPLICATE_PACKAGE
            | ArchFailure.INVALID_VERCMP_OUTPUT
            | ArchFailure.MISSING_NATIVE_PACKAGE
            | ArchFailure.UNEXPECTED_COMMAND_RESULT
            | ArchFailure.COMMAND_REJECTED
        ):
            return failure(source, SourceStatus.INVALID, detail, True, applicable)
        case ArchFailure.COMMAND_EXITED | ArchFailure.COMMAND_OUTPUT_EXCEEDED:
            return failure(source, SourceStatus.ERROR, detail, False, applicable)


def current(
    source: SourceName,
    items: tuple[NormalizedItem, ...],
    provenance: Provenance = Provenance.LIVE,
    findings: tuple[SecurityFindingGroup, ...] = (),
    scope: SourceScope | None = None,
) -> SourceOutcome:
    return SourceOutcome(
        source, scope, SourceStatus.OK, provenance, items, findings, None, False, True
    )


def not_applicable(
    source: SourceName, scope: SourceScope | None = None
) -> SourceOutcome:
    return SourceOutcome(
        source,
        scope,
        SourceStatus.NOT_APPLICABLE,
        Provenance.LIVE,
        (),
        (),
        None,
        False,
        False,
    )


def failure(
    source: SourceName,
    status: SourceStatus,
    detail: str,
    permanent: bool,
    applicable: bool,
    scope: SourceScope | None = None,
    items: tuple[NormalizedItem, ...] = (),
) -> SourceOutcome:
    code = (
        ErrorCode.SOURCE_INVALID
        if status is SourceStatus.INVALID
        else ErrorCode.SOURCE_UNAVAILABLE
    )
    return SourceOutcome(
        source,
        scope,
        status,
        Provenance.LIVE,
        items,
        (),
        ErrorInfo(code, detail[:512] or status.value),
        permanent,
        applicable,
    )
