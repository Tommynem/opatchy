from .adapters.arch import ArchDegraded, ArchUpdates
from .adapters.aur import (
    AurCollected,
    AurCommandFailed,
    AurCommandRejected,
    AurForeignInventoryDegraded,
    AurInvalid,
    AurMissingDependency,
    AurNotApplicable,
    AurOutputExceeded,
    AurResult,
    AurTimedOut,
)
from .adapters.mise import (
    MiseCollected,
    MiseCommandFailed,
    MiseCommandRejected,
    MiseInvalid,
    MiseNotApplicable,
    MiseOutputExceeded,
    MiseResult,
    MiseTimedOut,
)
from .models import SourceName, SourceStatus
from .scan_outcomes import SourceOutcome, arch_failure, current, failure, not_applicable


def arch_outcome(result: ArchUpdates | ArchDegraded) -> SourceOutcome:
    match result:
        case ArchUpdates(items=items):
            return current(SourceName.ARCH, items)
        case ArchDegraded(failure=failure_kind, detail=detail):
            return arch_failure(SourceName.ARCH, failure_kind, detail, True)


def aur_outcome(result: AurResult) -> SourceOutcome:
    match result:
        case AurCollected(items=items):
            return current(SourceName.AUR, items)
        case AurNotApplicable():
            return not_applicable(SourceName.AUR)
        case AurMissingDependency():
            return failure(
                SourceName.AUR,
                SourceStatus.MISSING_DEPENDENCY,
                "AUR helper is unavailable",
                True,
                True,
            )
        case AurInvalid(diagnostic=diagnostic):
            return failure(SourceName.AUR, SourceStatus.INVALID, diagnostic, True, True)
        case AurTimedOut(helper=helper):
            return failure(
                SourceName.AUR, SourceStatus.TIMEOUT, f"{helper} timed out", False, True
            )
        case AurOutputExceeded(helper=helper, stream=stream):
            return failure(
                SourceName.AUR,
                SourceStatus.ERROR,
                f"{helper} {stream} output exceeded",
                False,
                True,
            )
        case AurCommandFailed(helper=helper, returncode=returncode):
            return failure(
                SourceName.AUR,
                SourceStatus.ERROR,
                f"{helper} exited {returncode}",
                False,
                True,
            )
        case AurCommandRejected(helper=helper, diagnostic=diagnostic):
            return failure(
                SourceName.AUR,
                SourceStatus.ERROR,
                f"{helper} rejected: {diagnostic}",
                True,
                True,
            )
        case AurForeignInventoryDegraded(failure=failure_kind, detail=detail):
            return arch_failure(SourceName.AUR, failure_kind, detail, True)


def mise_outcome(result: MiseResult) -> SourceOutcome:
    match result:
        case MiseCollected(records=records):
            return current(SourceName.MISE, tuple(record.item for record in records))
        case MiseNotApplicable():
            return not_applicable(SourceName.MISE)
        case MiseInvalid(diagnostic=diagnostic):
            return failure(
                SourceName.MISE, SourceStatus.INVALID, diagnostic, True, True
            )
        case MiseTimedOut():
            return failure(
                SourceName.MISE, SourceStatus.TIMEOUT, "mise timed out", False, True
            )
        case MiseOutputExceeded(stream=stream):
            return failure(
                SourceName.MISE,
                SourceStatus.ERROR,
                f"mise {stream} output exceeded",
                False,
                True,
            )
        case MiseCommandFailed(returncode=returncode):
            return failure(
                SourceName.MISE,
                SourceStatus.ERROR,
                f"mise exited {returncode}",
                False,
                True,
            )
        case MiseCommandRejected(diagnostic=diagnostic):
            return failure(SourceName.MISE, SourceStatus.ERROR, diagnostic, True, True)
