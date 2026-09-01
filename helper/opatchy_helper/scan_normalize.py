from .adapters.flatpak import (
    FlatpakResult,
    FlatpakScopeResult,
    FlatpakScopeStatus,
)
from .adapters.omarchy import OmarchyAvailability
from .adapters.security import (
    SecurityArchUnavailable,
    SecurityCollected,
    SecurityResult,
)
from .adapters.security_kev import KevCatalog, KevDisabled, KevUnavailable
from .models import SourceName, SourceScope, SourceStatus
from .scan_outcomes import SourceOutcome, current, failure, from_status, not_applicable


def omarchy_outcome(result: OmarchyAvailability) -> SourceOutcome:
    return from_status(
        SourceName.OMARCHY, result.status, result.items, (), result.diagnostic
    )


def flatpak_outcomes(result: FlatpakResult) -> tuple[SourceOutcome, SourceOutcome]:
    user, system = result.scopes
    return _flatpak_scope(user), _flatpak_scope(system)


def security_outcomes(result: SecurityResult) -> tuple[SourceOutcome, SourceOutcome]:
    match result:
        case SecurityCollected(groups=groups, arch_provenance=provenance, kev=kev):
            security = SourceOutcome(
                SourceName.SECURITY,
                None,
                SourceStatus.OK,
                provenance,
                (),
                groups,
                None,
                False,
                True,
            )
            match kev:
                case KevCatalog(provenance=kev_provenance):
                    return security, current(SourceName.CISA_KEV, (), kev_provenance)
                case KevDisabled():
                    return security, not_applicable(SourceName.CISA_KEV)
                case KevUnavailable(diagnostic=diagnostic):
                    return security, failure(
                        SourceName.CISA_KEV,
                        SourceStatus.ERROR,
                        diagnostic,
                        False,
                        True,
                    )
        case SecurityArchUnavailable(diagnostic=diagnostic):
            return (
                failure(
                    SourceName.SECURITY, SourceStatus.ERROR, diagnostic, False, True
                ),
                failure(
                    SourceName.CISA_KEV,
                    SourceStatus.ERROR,
                    "security evidence is unavailable",
                    False,
                    False,
                ),
            )


def _flatpak_scope(scope: FlatpakScopeResult) -> SourceOutcome:
    mapped_scope = SourceScope(scope.scope.value)
    items = tuple(record.item for record in scope.records)
    match scope.status:
        case FlatpakScopeStatus.OK:
            return current(SourceName.FLATPAK, items, scope=mapped_scope)
        case FlatpakScopeStatus.NOT_APPLICABLE:
            return not_applicable(SourceName.FLATPAK, mapped_scope)
        case FlatpakScopeStatus.MISSING_DEPENDENCY:
            return failure(
                SourceName.FLATPAK,
                SourceStatus.MISSING_DEPENDENCY,
                scope.diagnostic or "Flatpak is unavailable",
                True,
                True,
                mapped_scope,
                items,
            )
        case FlatpakScopeStatus.TIMEOUT:
            return failure(
                SourceName.FLATPAK,
                SourceStatus.TIMEOUT,
                scope.diagnostic or "Flatpak timed out",
                False,
                True,
                mapped_scope,
                items,
            )
        case FlatpakScopeStatus.OUTPUT_EXCEEDED | FlatpakScopeStatus.ERROR:
            return failure(
                SourceName.FLATPAK,
                SourceStatus.ERROR,
                scope.diagnostic or "Flatpak failed",
                False,
                True,
                mapped_scope,
                items,
            )
        case FlatpakScopeStatus.INVALID:
            return failure(
                SourceName.FLATPAK,
                SourceStatus.INVALID,
                scope.diagnostic or "Flatpak evidence is invalid",
                True,
                True,
                mapped_scope,
                items,
            )
