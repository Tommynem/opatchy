from opatchy_helper.adapters.arch import ArchDegraded, ArchFailure, ArchUpdates
from opatchy_helper.adapters.aur import (
    AurCollected,
    AurCommandFailed,
    AurCommandRejected,
    AurForeignInventoryDegraded,
    AurHelper,
    AurInvalid,
    AurMissingDependency,
    AurNotApplicable,
    AurOutputExceeded,
    AurTimedOut,
)
from opatchy_helper.adapters.flatpak import (
    FlatpakResult,
    FlatpakScope,
    FlatpakScopeResult,
    FlatpakScopeStatus,
)
from opatchy_helper.adapters.mise import (
    MiseCollected,
    MiseCommandFailed,
    MiseCommandRejected,
    MiseInvalid,
    MiseNotApplicable,
    MiseOutputExceeded,
    MiseRecord,
    MiseTimedOut,
)
from opatchy_helper.adapters.omarchy import OmarchyAvailability
from opatchy_helper.adapters.security import SecurityArchUnavailable, SecurityCollected
from opatchy_helper.adapters.security_kev import KevUnavailable
from opatchy_helper.models import ItemSource, Provenance, SourceName, SourceStatus
from opatchy_helper.scan_command_outcomes import arch_outcome, aur_outcome, mise_outcome
from opatchy_helper.scan_normalize import (
    flatpak_outcomes,
    omarchy_outcome,
    security_outcomes,
)
from opatchy_helper.scan_outcomes import arch_failure, from_status

from tests.python.scan_support import item


def test_scan_command_normalizers_cover_arch_aur_and_mise_variants() -> None:
    # Given: every typed command adapter result variant.
    arch_item = item(ItemSource.ARCH, "linux")
    mise_item = item(ItemSource.MISE, "python")
    aur_results = (
        (AurCollected(AurHelper.YAY, (item(ItemSource.AUR, "paru"),)), SourceStatus.OK),
        (AurNotApplicable(), SourceStatus.NOT_APPLICABLE),
        (AurMissingDependency(), SourceStatus.MISSING_DEPENDENCY),
        (AurInvalid("bad"), SourceStatus.INVALID),
        (AurTimedOut(AurHelper.YAY), SourceStatus.TIMEOUT),
        (AurOutputExceeded(AurHelper.PARU, "stdout"), SourceStatus.ERROR),
        (AurCommandFailed(AurHelper.PARU, 1), SourceStatus.ERROR),
        (AurCommandRejected(AurHelper.YAY, "bad"), SourceStatus.ERROR),
        (
            AurForeignInventoryDegraded(ArchFailure.COMMAND_TIMED_OUT, "bad"),
            SourceStatus.TIMEOUT,
        ),
    )
    mise_results = (
        (MiseCollected((MiseRecord(mise_item, "1", "1", "2"),)), SourceStatus.OK),
        (MiseNotApplicable(), SourceStatus.NOT_APPLICABLE),
        (MiseInvalid("bad"), SourceStatus.INVALID),
        (MiseTimedOut(), SourceStatus.TIMEOUT),
        (MiseOutputExceeded("stdout"), SourceStatus.ERROR),
        (MiseCommandFailed(1), SourceStatus.ERROR),
        (MiseCommandRejected("bad"), SourceStatus.ERROR),
    )

    # When: each result is converted to its scan outcome.
    arch_current = arch_outcome(ArchUpdates((arch_item,)))
    arch_failed = arch_outcome(ArchDegraded(ArchFailure.COMMAND_MISSING, "missing"))
    aur_statuses = tuple(aur_outcome(result).status for result, _ in aur_results)
    mise_statuses = tuple(mise_outcome(result).status for result, _ in mise_results)

    # Then: every variant preserves the typed source health category.
    assert (arch_current.status, arch_failed.status) == (
        SourceStatus.OK,
        SourceStatus.MISSING_DEPENDENCY,
    )
    assert aur_statuses == tuple(expected for _, expected in aur_results)
    assert mise_statuses == tuple(expected for _, expected in mise_results)


def test_scan_scope_security_and_generic_outcomes_cover_all_status_branches() -> None:
    # Given: Flatpak scopes, security evidence, and generic source status variants.
    flatpak = FlatpakResult(
        (
            FlatpakScopeResult(FlatpakScope.USER, FlatpakScopeStatus.OK, (), None),
            FlatpakScopeResult(
                FlatpakScope.SYSTEM, FlatpakScopeStatus.NOT_APPLICABLE, (), None
            ),
        )
    )
    flatpak_failures = tuple(
        FlatpakResult(
            (
                FlatpakScopeResult(FlatpakScope.USER, status, (), "bad"),
                FlatpakScopeResult(
                    FlatpakScope.SYSTEM, FlatpakScopeStatus.NOT_APPLICABLE, (), None
                ),
            )
        )
        for status in (
            FlatpakScopeStatus.MISSING_DEPENDENCY,
            FlatpakScopeStatus.TIMEOUT,
            FlatpakScopeStatus.OUTPUT_EXCEEDED,
            FlatpakScopeStatus.ERROR,
            FlatpakScopeStatus.INVALID,
        )
    )
    statuses = (
        SourceStatus.OK,
        SourceStatus.NOT_APPLICABLE,
        SourceStatus.MISSING_DEPENDENCY,
        SourceStatus.INVALID,
        SourceStatus.TIMEOUT,
        SourceStatus.OFFLINE,
        SourceStatus.ERROR,
        SourceStatus.STALE,
    )

    # When: all source outcomes are normalized.
    live_scopes = flatpak_outcomes(flatpak)
    failed_scopes = tuple(
        flatpak_outcomes(result)[0].status for result in flatpak_failures
    )
    security, kev = security_outcomes(
        SecurityCollected((), Provenance.LIVE, KevUnavailable("unavailable"))
    )
    unavailable, unavailable_kev = security_outcomes(SecurityArchUnavailable("bad"))
    generic = tuple(
        from_status(SourceName.OMARCHY, status, (), (), "bad").status
        for status in statuses
    )
    permanent = tuple(
        arch_failure(SourceName.ARCH, failure, "bad", True).permanent
        for failure in ArchFailure
    )
    omarchy = omarchy_outcome(
        OmarchyAvailability(SourceStatus.NOT_APPLICABLE, (), None)
    )

    # Then: scoped failures, security degradation, and permanence remain explicit.
    assert tuple(outcome.status for outcome in live_scopes) == (
        SourceStatus.OK,
        SourceStatus.NOT_APPLICABLE,
    )
    assert failed_scopes == (
        SourceStatus.MISSING_DEPENDENCY,
        SourceStatus.TIMEOUT,
        SourceStatus.ERROR,
        SourceStatus.ERROR,
        SourceStatus.INVALID,
    )
    assert (
        security.status,
        kev.status,
        unavailable.status,
        unavailable_kev.status,
    ) == (
        SourceStatus.OK,
        SourceStatus.ERROR,
        SourceStatus.ERROR,
        SourceStatus.ERROR,
    )
    assert generic == statuses
    assert any(permanent) and not all(permanent)
    assert omarchy.status is SourceStatus.NOT_APPLICABLE
