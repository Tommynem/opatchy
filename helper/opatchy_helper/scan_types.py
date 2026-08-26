from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, final

from .adapters.arch import ArchDegraded, ArchUpdates, collect_official_updates
from .adapters.aur import AurResult, collect_aur_updates
from .adapters.flatpak import FlatpakResult, collect_flatpak
from .adapters.mise import MiseResult, collect_mise_updates
from .adapters.omarchy import OmarchyAvailability, collect_omarchy_availability
from .adapters.security import SecurityResult, collect_security
from .models import GenerationId, SnapshotResponse
from .runner import fetch_endpoint, run_command
from .runner_types import CommandName, CommandResult, EndpointName, EndpointResult
from .storage import Storage
from .storage_types import FeedName


class ScanCollector(Protocol):
    """Collects typed adapter results without exposing command or network details."""

    def collect_omarchy(self) -> OmarchyAvailability: ...

    def collect_arch(self) -> ArchUpdates | ArchDegraded: ...

    def collect_aur(self) -> AurResult: ...

    def collect_flatpak(self) -> FlatpakResult: ...

    def collect_mise(self) -> MiseResult: ...

    def collect_security(self) -> SecurityResult: ...


@dataclass(frozen=True, slots=True)
class ScanRequest:
    generation_id: GenerationId
    generation_order: int
    force: bool


@dataclass(frozen=True, slots=True)
class ScanResult:
    committed: bool
    snapshot: SnapshotResponse


@final
@dataclass(frozen=True, slots=True)
class RuntimeScanCollector:
    """Production collector wired exclusively to the closed shared runner/fetcher."""

    storage: Storage
    run: Callable[[CommandName, tuple[str, ...]], CommandResult] = run_command

    def collect_omarchy(self) -> OmarchyAvailability:
        return collect_omarchy_availability(self._run_with_default)

    def collect_arch(self) -> ArchUpdates | ArchDegraded:
        return collect_official_updates(self._run_with_default)

    def collect_aur(self) -> AurResult:
        return collect_aur_updates(self._run_with_default)

    def collect_flatpak(self) -> FlatpakResult:
        return collect_flatpak(lambda name: self._run_with_default(name, ()))

    def collect_mise(self) -> MiseResult:
        return collect_mise_updates(self._run_with_default)

    def collect_security(self) -> SecurityResult:
        return collect_security(self._run_with_default, self._fetch, self.storage)

    def _run_with_default(
        self, name: CommandName, arguments: tuple[str, ...] = ()
    ) -> CommandResult:
        return self.run(name, arguments)

    def _fetch(self, name: EndpointName) -> EndpointResult:
        match name:
            case EndpointName.ARCH_SECURITY:
                return fetch_endpoint(
                    name, self.storage.endpoint_cache(FeedName.ARCH_SECURITY)
                )
            case EndpointName.CISA_KEV:
                return fetch_endpoint(
                    name, self.storage.endpoint_cache(FeedName.CISA_KEV)
                )
