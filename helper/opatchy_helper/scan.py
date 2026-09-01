from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import Protocol, final

from .models import NotificationOutcome, SnapshotResponse, SourceName
from .notifications import NotificationCoordinator
from .scan_command_outcomes import (
    arch_outcome,
    aur_outcome,
    mise_outcome,
)
from .scan_generation import ScanInputs, build_generation, due
from .scan_normalize import (
    flatpak_outcomes,
    omarchy_outcome,
    security_outcomes,
)
from .scan_outcomes import SourceOutcome, not_applicable
from .scan_types import ScanCollector, ScanRequest, ScanResult
from .storage import Storage
from .storage_types import SourceMetadata

__all__ = ("ScanCollector", "ScanCoordinator", "ScanRequest", "ScanResult")


class NotificationDispatcher(Protocol):
    def dispatch(
        self, snapshot: SnapshotResponse
    ) -> tuple[NotificationOutcome, ...]: ...


@final
class ScanCoordinator:
    def __init__(
        self,
        storage: Storage,
        collector: ScanCollector,
        clock: Callable[[], datetime],
        notifications: NotificationDispatcher | None = None,
    ) -> None:
        self._storage = storage
        self._collector = collector
        self._clock = clock
        self._notifications = notifications

    def run(self, request: ScanRequest) -> ScanResult:
        now = self._clock()
        previous = self._storage.load_generation()
        state = self._storage.load_state().state
        metadata = state.sources
        omarchy_due = _due(SourceName.OMARCHY, metadata, now, request.force)
        arch_due = _due(SourceName.ARCH, metadata, now, request.force)
        aur_due = _due(SourceName.AUR, metadata, now, request.force)
        flatpak_due = _due(SourceName.FLATPAK, metadata, now, request.force)
        mise_due = _due(SourceName.MISE, metadata, now, request.force)
        security_due = _due(SourceName.SECURITY, metadata, now, request.force)
        cisa_due = _due(SourceName.CISA_KEV, metadata, now, request.force)
        omarchy = (
            omarchy_outcome(self._collector.collect_omarchy()) if omarchy_due else None
        )
        arch = arch_outcome(self._collector.collect_arch()) if arch_due else None
        aur = aur_outcome(self._collector.collect_aur()) if aur_due else None
        flatpak_user, flatpak_system = _flatpak(self._collector, flatpak_due)
        mise = mise_outcome(self._collector.collect_mise()) if mise_due else None
        security, cisa_kev = _security(
            self._collector, security_due, cisa_due, request.enable_cisa_kev
        )
        generation = build_generation(
            request.generation_id,
            request.generation_order,
            ScanInputs(
                omarchy,
                arch,
                aur,
                flatpak_user,
                flatpak_system,
                mise,
                security,
                cisa_kev,
            ),
            previous,
            state,
            now,
        )
        committed = self._storage.commit_generation(generation)
        if committed:
            dispatcher = self._notifications or NotificationCoordinator(
                self._storage, settings=request.notification_settings
            )
            outcomes = dispatcher.dispatch(generation.snapshot)
            snapshot = replace(
                generation.snapshot,
                payload=replace(generation.snapshot.payload, notifications=outcomes),
            )
            return ScanResult(True, snapshot)
        return ScanResult(False, generation.snapshot)


def _due(
    source: SourceName,
    metadata: tuple[SourceMetadata, ...],
    now: datetime,
    force: bool,
) -> bool:
    return due(
        next((entry for entry in metadata if entry.source is source), None), now, force
    )


def _flatpak(
    collector: ScanCollector, is_due: bool
) -> tuple[SourceOutcome | None, SourceOutcome | None]:
    if not is_due:
        return None, None
    return flatpak_outcomes(collector.collect_flatpak())


def _security(
    collector: ScanCollector,
    security_due: bool,
    cisa_due: bool,
    enable_cisa_kev: bool,
) -> tuple[SourceOutcome | None, SourceOutcome | None]:
    if not enable_cisa_kev:
        if not security_due:
            return None, not_applicable(SourceName.CISA_KEV)
        security, _ = security_outcomes(collector.collect_security(False))
        return security, not_applicable(SourceName.CISA_KEV)
    if not security_due and not cisa_due:
        return None, None
    return security_outcomes(collector.collect_security(True))
