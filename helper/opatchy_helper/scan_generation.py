from dataclasses import dataclass, replace
from datetime import datetime

from .models import GenerationId, SnapshotPayload, SnapshotResponse, SourceName
from .scan_assembly import (
    SourceOutcomeGroups,
    inventories,
    last_good_keys,
    metadata,
    normalized_findings,
    normalized_items,
    scan_state,
    source_healths,
    summary,
)
from .scan_outcomes import SourceOutcome
from .scan_resolution import FRESHNESS, resolve_all
from .storage_generation import GenerationBundle
from .storage_types import PersistentState, SourceMetadata


@dataclass(frozen=True, slots=True)
class ScanInputs:
    omarchy: SourceOutcome | None
    arch: SourceOutcome | None
    aur: SourceOutcome | None
    flatpak_user: SourceOutcome | None
    flatpak_system: SourceOutcome | None
    mise: SourceOutcome | None
    security: SourceOutcome | None
    cisa_kev: SourceOutcome | None

    def outcomes(self) -> tuple[SourceOutcome | None, ...]:
        return (
            self.omarchy,
            self.arch,
            self.aur,
            self.flatpak_user,
            self.flatpak_system,
            self.mise,
            self.security,
            self.cisa_kev,
        )

    def source_outcomes(self) -> SourceOutcomeGroups:
        return (
            (SourceName.OMARCHY, (self.omarchy,)),
            (SourceName.ARCH, (self.arch,)),
            (SourceName.AUR, (self.aur,)),
            (SourceName.FLATPAK, (self.flatpak_user, self.flatpak_system)),
            (SourceName.MISE, (self.mise,)),
            (SourceName.SECURITY, (self.security,)),
            (SourceName.CISA_KEV, (self.cisa_kev,)),
        )


def due(metadata: SourceMetadata | None, now: datetime, force: bool) -> bool:
    if force or metadata is None:
        return True
    if metadata.backoff_until is not None and now < metadata.backoff_until:
        return False
    if metadata.last_success is None:
        return True
    return now >= metadata.last_success + FRESHNESS


def build_generation(
    generation_id: GenerationId,
    order: int,
    inputs: ScanInputs,
    previous: GenerationBundle | None,
    state: PersistentState,
    now: datetime,
) -> GenerationBundle:
    resolved = resolve_all(inputs.outcomes(), previous, now)
    sources = source_healths(resolved, now)
    items = normalized_items(resolved)
    findings = normalized_findings(resolved)
    snapshot = SnapshotResponse(
        now,
        generation_id,
        SnapshotPayload(
            scan_state(resolved),
            sources,
            summary(items, findings, sources),
            items,
            findings,
            (),
        ),
    )
    return GenerationBundle(
        order,
        snapshot,
        inventories(now, generation_id, items),
        replace(state, sources=metadata(state.sources, inputs.source_outcomes(), now)),
        snapshot,
        last_good_keys(previous, resolved),
    )
