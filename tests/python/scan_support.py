from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, override

from opatchy_helper.adapters.arch import ArchDegraded, ArchUpdates
from opatchy_helper.adapters.aur import AurNotApplicable, AurResult
from opatchy_helper.adapters.flatpak import (
    FlatpakResult,
    FlatpakScope,
    FlatpakScopeResult,
    FlatpakScopeStatus,
)
from opatchy_helper.adapters.mise import MiseNotApplicable, MiseResult
from opatchy_helper.adapters.omarchy import OmarchyAvailability
from opatchy_helper.adapters.security import SecurityArchUnavailable, SecurityCollected
from opatchy_helper.adapters.security_kev import KevCatalog
from opatchy_helper.models import (
    GenerationId,
    ItemId,
    ItemSource,
    NormalizedItem,
    Provenance,
    SourceStatus,
    WatchMode,
)
from opatchy_helper.scan import ScanCollector, ScanCoordinator, ScanRequest, ScanResult
from opatchy_helper.storage import Storage, SystemAtomicOperations

NOW: Final = datetime(2026, 8, 26, 12, tzinfo=timezone.utc)


@dataclass(slots=True)
class ScanClock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now


def item(
    source: ItemSource, name: str, installed: str = "1", candidate: str = "2"
) -> NormalizedItem:
    return NormalizedItem(
        ItemId(f"{source}:{name}"),
        source,
        name,
        installed,
        candidate,
        WatchMode.OFF,
        True,
        Provenance.LIVE,
    )


@dataclass(frozen=True, slots=True)
class FakeCollector(ScanCollector):
    omarchy: OmarchyAvailability
    arch: ArchUpdates | ArchDegraded
    security: SecurityCollected | SecurityArchUnavailable
    aur: AurResult = AurNotApplicable()
    flatpak: FlatpakResult = FlatpakResult(
        (
            FlatpakScopeResult(
                FlatpakScope.USER, FlatpakScopeStatus.NOT_APPLICABLE, (), None
            ),
            FlatpakScopeResult(
                FlatpakScope.SYSTEM, FlatpakScopeStatus.NOT_APPLICABLE, (), None
            ),
        )
    )
    mise: MiseResult = MiseNotApplicable()

    @override
    def collect_omarchy(self) -> OmarchyAvailability:
        return self.omarchy

    @override
    def collect_arch(self) -> ArchUpdates | ArchDegraded:
        return self.arch

    @override
    def collect_aur(self) -> AurResult:
        return self.aur

    @override
    def collect_flatpak(self) -> FlatpakResult:
        return self.flatpak

    @override
    def collect_mise(self) -> MiseResult:
        return self.mise

    @override
    def collect_security(
        self, enable_cisa_kev: bool = True
    ) -> SecurityCollected | SecurityArchUnavailable:
        _ = enable_cisa_kev
        return self.security


def collector(
    arch: ArchUpdates | ArchDegraded | None = None,
    omarchy: OmarchyAvailability | None = None,
    security: SecurityCollected | SecurityArchUnavailable | None = None,
) -> FakeCollector:
    resolved_arch = (
        ArchUpdates((item(ItemSource.ARCH, "linux"),)) if arch is None else arch
    )
    resolved_omarchy = (
        OmarchyAvailability(
            SourceStatus.OK, (item(ItemSource.OMARCHY, "omarchy"),), None
        )
        if omarchy is None
        else omarchy
    )
    resolved_security = (
        SecurityCollected((), Provenance.LIVE, KevCatalog(frozenset(), Provenance.LIVE))
        if security is None
        else security
    )
    return FakeCollector(resolved_omarchy, resolved_arch, resolved_security)


def store(tmp_path: Path, clock: Callable[[], datetime] | None = None) -> Storage:
    return Storage(
        tmp_path / "state" / "state.json",
        tmp_path / "cache",
        (lambda: NOW) if clock is None else clock,
        SystemAtomicOperations(),
    )


def run(
    storage: Storage,
    source: ScanCollector,
    order: int,
    *,
    force: bool = False,
    clock: Callable[[], datetime] | None = None,
) -> ScanResult:
    return ScanCoordinator(
        storage, source, (lambda: NOW) if clock is None else clock
    ).run(ScanRequest(GenerationId(f"generation-{order}"), order, force))
