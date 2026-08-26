from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

import pytest

HELPER_ROOT: Final = Path(__file__).resolve().parents[3] / "helper"
FIXTURE_ROOT: Final = Path(__file__).resolve().parents[2] / "fixtures" / "security"
sys.path.insert(0, str(HELPER_ROOT))

from opatchy_helper.adapters.security import (
    SecurityArchUnavailable,
    SecurityCollected,
    collect_security,
)
from opatchy_helper.adapters.security_kev import KevUnavailable
from opatchy_helper.runner_types import (
    CommandName,
    CommandResult,
    CommandSucceeded,
    EndpointDownloaded,
    EndpointName,
    EndpointResult,
    EndpointTimedOut,
)
from opatchy_helper.storage import Storage, SystemAtomicOperations
from opatchy_helper.storage_types import FeedName


def _fixture(name: str) -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()


def _command_runner(
    results: tuple[CommandResult, ...],
) -> tuple[
    Callable[[CommandName, tuple[str, ...]], CommandResult],
    list[tuple[CommandName, tuple[str, ...]]],
]:
    requests: list[tuple[CommandName, tuple[str, ...]]] = []
    remaining = iter(results)

    def run(name: CommandName, arguments: tuple[str, ...]) -> CommandResult:
        requests.append((name, arguments))
        return next(remaining)

    return run, requests


def _fetcher(
    results: tuple[EndpointResult, ...],
) -> tuple[Callable[[EndpointName], EndpointResult], list[EndpointName]]:
    requests: list[EndpointName] = []
    remaining = iter(results)

    def fetch(name: EndpointName) -> EndpointResult:
        requests.append(name)
        return next(remaining)

    return fetch, requests


def test_primary_success_uses_fresh_inventory_without_tracker_and_enriches_kev(
    tmp_path: Path,
) -> None:
    # Given: fresh official inventory, valid arch-audit, and an independent KEV response.
    run, command_requests = _command_runner(
        (
            CommandSucceeded(b"linux 1:6.12.2-1\nopenssl 3.0-1\n", b""),
            CommandSucceeded(_fixture("arch-audit.json"), b""),
            CommandSucceeded(b"-1\n", b""),
        )
    )
    fetch, endpoint_requests = _fetcher(
        (EndpointDownloaded(_fixture("cisa-kev.json"), None, None),)
    )
    storage = Storage(
        tmp_path / "state.json",
        tmp_path / "cache",
        lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        SystemAtomicOperations(),
    )

    # When: current security evidence is collected.
    result = collect_security(run, fetch, storage)

    # Then: it does not fetch Tracker and a matched CVE is listed as KEV.
    assert isinstance(result, SecurityCollected)
    assert result.groups[0].findings[0].known_exploited is True
    assert endpoint_requests == [EndpointName.CISA_KEV]
    assert storage.read_last_good_feed(FeedName.CISA_KEV) == _fixture("cisa-kev.json")
    assert command_requests == [
        (CommandName.PACMAN_NATIVE, ()),
        (CommandName.ARCH_AUDIT, ()),
        (CommandName.VERCMP, ("1:6.12.2-1", "1:6.12.3-1")),
    ]


def test_primary_failure_uses_tracker_but_both_unavailable_never_becomes_clean() -> (
    None
):
    # Given: arch-audit fails and the closed Tracker endpoint cannot be fetched.
    run, _ = _command_runner(
        (
            CommandSucceeded(b"linux 1\n", b""),
            CommandSucceeded(b"{}", b""),
        )
    )
    fetch, requests = _fetcher((EndpointTimedOut("offline"),))

    # When: the primary parser fails and fallback also fails.
    result = collect_security(run, fetch)

    # Then: the typed current failure cannot masquerade as a fresh empty result.
    assert isinstance(result, SecurityArchUnavailable)
    assert requests == [EndpointName.ARCH_SECURITY]


def test_primary_failure_uses_valid_tracker_fallback() -> None:
    # Given: a primary schema failure, a fresh official inventory, and valid fallback feeds.
    run, command_requests = _command_runner(
        (
            CommandSucceeded(b"linux 1:6.12.2-1\nopenssl 3.0-1\n", b""),
            CommandSucceeded(b"{}", b""),
            CommandSucceeded(b"-1", b""),
        )
    )
    fetch, endpoint_requests = _fetcher(
        (
            EndpointDownloaded(_fixture("tracker-all.json"), None, None),
            EndpointDownloaded(_fixture("cisa-kev.json"), None, None),
        )
    )

    # When: a typed primary failure permits the closed Tracker fallback.
    result = collect_security(run, fetch)

    # Then: fallback findings retain their provenance and use only required commands.
    assert isinstance(result, SecurityCollected)
    assert result.arch_provenance.value == "fallback"
    assert endpoint_requests == [EndpointName.ARCH_SECURITY, EndpointName.CISA_KEV]
    assert command_requests == [
        (CommandName.PACMAN_NATIVE, ()),
        (CommandName.ARCH_AUDIT, ()),
        (CommandName.VERCMP, ("1:6.12.2-1", "1:6.12.3-1")),
    ]


def test_kev_failure_preserves_current_arch_findings_and_is_distinguishable() -> None:
    # Given: valid Arch evidence and an unavailable KEV endpoint.
    run, _ = _command_runner(
        (
            CommandSucceeded(b"linux 1:6.12.2-1\nopenssl 3.0-1\n", b""),
            CommandSucceeded(_fixture("arch-audit.json"), b""),
            CommandSucceeded(b"-1", b""),
        )
    )
    fetch, _ = _fetcher((EndpointTimedOut("offline"),))

    # When: KEV cannot be fetched after Arch correlation succeeds.
    result = collect_security(run, fetch)

    # Then: Arch groups survive unaltered while KEV is explicitly unavailable.
    assert isinstance(result, SecurityCollected)
    assert isinstance(result.kev, KevUnavailable)
    assert len(result.groups) == 2


def test_primary_empty_does_not_fetch_tracker_and_requires_fresh_inventory() -> None:
    # Given: a mandatory fresh inventory and a valid empty primary feed.
    run, _ = _command_runner(
        (
            CommandSucceeded(b"linux 1\n", b""),
            CommandSucceeded(b"[]", b""),
        )
    )
    fetch, requests = _fetcher((EndpointTimedOut("offline"),))

    # When: primary evidence is semantically valid but empty.
    result = collect_security(run, fetch)

    # Then: it is a clean Arch result, but KEV remains independently unavailable.
    assert isinstance(result, SecurityCollected)
    assert result.groups == ()
    assert requests == [EndpointName.CISA_KEV]


def test_transport_cache_and_semantic_last_good_cache_are_separate(
    tmp_path: Path,
) -> None:
    # Given: an isolated store with a valid semantic feed body.
    storage = Storage(
        tmp_path / "state.json",
        tmp_path / "cache",
        lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        SystemAtomicOperations(),
    )
    valid = b"[]"
    assert storage.write_last_good_feed(FeedName.ARCH_SECURITY, valid, lambda _: True)

    # When: invalid downloaded evidence is refused after transport paths are requested.
    transport = storage.endpoint_cache(FeedName.ARCH_SECURITY)
    accepted = storage.write_last_good_feed(
        FeedName.ARCH_SECURITY, b"{", lambda _: False
    )

    # Then: the transport artifact cannot overwrite semantically validated last-good data.
    assert transport.body_path != storage.cache_path / "arch-security.json"
    assert accepted is False
    assert storage.read_last_good_feed(FeedName.ARCH_SECURITY) == valid


@pytest.mark.parametrize(
    "payload",
    (
        b'{"catalogVersion":"1","dateReleased":"today","count":1,"vulnerabilities":[]}',
        b'{"catalogVersion":"1","dateReleased":"today","count":true,"vulnerabilities":[]}',
        b'{"catalogVersion":"1","dateReleased":"today","count":0,"vulnerabilities":[{"cveID":"CVE-2026-0001"}]}',
    ),
)
def test_kev_shape_failures_do_not_affect_arch_collection(payload: bytes) -> None:
    # Given: current Arch evidence and malformed/incompatible KEV JSON.
    run, _ = _command_runner(
        (
            CommandSucceeded(b"linux 1:6.12.2-1\nopenssl 3.0-1\n", b""),
            CommandSucceeded(_fixture("arch-audit.json"), b""),
            CommandSucceeded(b"-1", b""),
        )
    )
    fetch, _ = _fetcher((EndpointDownloaded(payload, None, None),))

    # When: KEV validation rejects the downloaded body.
    result = collect_security(run, fetch)

    # Then: the Arch results remain current, with KEV unavailable rather than false.
    assert isinstance(result, SecurityCollected)
    assert isinstance(result.kev, KevUnavailable)
