from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "helper"))

from opatchy_helper.models import GenerationId, SourceStatus
from opatchy_helper.runner_types import (
    CommandMissing,
    CommandName,
    CommandResult,
    CommandSucceeded,
    CommandTimedOut,
    EndpointCache,
    EndpointDownloaded,
    EndpointName,
    EndpointResult,
)
from opatchy_helper.scan import ScanCoordinator, ScanRequest
from opatchy_helper.scan_types import RuntimeScanCollector
from opatchy_helper.storage import Storage, SystemAtomicOperations

from tests.e2e.offline_scenario_runner import assert_qml_presentation

NOW = datetime(2026, 8, 26, 12, tzinfo=timezone.utc)
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "security"


def _store(tmp_path: Path) -> Storage:
    return Storage(
        tmp_path / "xdg-state" / "opatchy" / "state.json",
        tmp_path / "xdg-cache" / "opatchy",
        lambda: NOW,
        SystemAtomicOperations(),
    )


def _run_fixture(
    offline_arch: bool = False,
) -> Callable[[CommandName, tuple[str, ...]], CommandResult]:
    def run(name: CommandName, _: tuple[str, ...]) -> CommandResult:
        match name:
            case CommandName.OMARCHY_UPDATE_AVAILABLE:
                return CommandSucceeded(b"omarchy 1 -> 2\n", b"")
            case CommandName.PACMAN_NATIVE:
                return CommandSucceeded(b"linux 1:6.12.2-1\nopenssl 3.0-1\n", b"")
            case CommandName.CHECKUPDATES:
                return (
                    CommandTimedOut(b"", b"")
                    if offline_arch
                    else CommandSucceeded(b"linux 1:6.12.2-1 -> 1:6.12.3-1\n", b"")
                )
            case CommandName.PACMAN_FOREIGN:
                return CommandSucceeded(b"", b"")
            case (
                CommandName.FLATPAK_USER_APP_LIST
                | CommandName.FLATPAK_USER_RUNTIME_LIST
                | CommandName.FLATPAK_SYSTEM_APP_LIST
                | CommandName.FLATPAK_SYSTEM_RUNTIME_LIST
            ):
                return CommandMissing("fixture-only absent")
            case CommandName.MISE_OUTDATED:
                return CommandMissing("fixture-only absent")
            case CommandName.ARCH_AUDIT:
                return CommandSucceeded(
                    (FIXTURES / "arch-audit.json").read_bytes(), b""
                )
            case CommandName.VERCMP:
                return CommandSucceeded(b"-1\n", b"")
            case unreachable:
                raise AssertionError(f"unexpected fixture command: {unreachable}")

    return run


def _fetch_fixture(_: EndpointName, _cache: EndpointCache) -> EndpointResult:
    return EndpointDownloaded((FIXTURES / "cisa-kev.json").read_bytes(), None, None)


def _scan(
    store: Storage,
    monkeypatch: pytest.MonkeyPatch,
    order: int,
    *,
    offline_arch: bool = False,
) -> None:
    import opatchy_helper.scan_types as scan_types

    monkeypatch.setattr(scan_types, "fetch_endpoint", _fetch_fixture)
    _ = ScanCoordinator(
        store, RuntimeScanCollector(store, _run_fixture(offline_arch)), lambda: NOW
    ).run(ScanRequest(GenerationId(f"fixture-{order}"), order, True))


def test_fixture_only_runtime_adapters_reach_storage_protocol_and_qml_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: closed command and endpoint fixtures under isolated XDG-equivalent roots.
    store = _store(tmp_path)
    _scan(store, monkeypatch, 1)
    current = store.load_snapshot()

    # When: the next adapter-backed scan has offline Arch evidence.
    assert current is not None
    assert_qml_presentation(current)
    _scan(store, monkeypatch, 2, offline_arch=True)
    partial = store.load_snapshot()

    # Then: fixed/KEV and no-fix findings cross the consumer boundary; stale is explicit.
    assert current.payload.summary.total_updates == 2
    assert current.payload.summary.security_findings == 2
    assert any(group.findings[0].known_exploited for group in current.payload.findings)
    assert any(
        finding.fixed_version is None
        for group in current.payload.findings
        for finding in group.findings
    )
    assert partial is not None
    assert partial.payload.scan_state.value == "partial"
    assert (
        next(
            source
            for source in partial.payload.sources
            if source.source.value == "arch"
        ).status
        is SourceStatus.STALE
    )
    assert_qml_presentation(partial)
