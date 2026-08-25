from __future__ import annotations

import sys
from pathlib import Path

import pytest

HELPER_ROOT = Path(__file__).resolve().parents[3] / "helper"
sys.path.insert(0, str(HELPER_ROOT))

from opatchy_helper.adapters.omarchy import (
    OMARCHY_DUPLICATE_FILTER,
    OmarchyAvailability,
    collect_omarchy_availability,
)
from opatchy_helper.models import (
    ItemId,
    ItemSource,
    NormalizedItem,
    Provenance,
    SourceStatus,
    WatchMode,
)
from opatchy_helper.runner import (
    CommandExited,
    CommandMissing,
    CommandName,
    CommandOutputExceeded,
    CommandRejected,
    CommandResult,
    CommandSucceeded,
    CommandTimedOut,
)


class RecordedRunner:
    outcome: CommandResult
    calls: list[tuple[CommandName, tuple[str, ...]]]

    def __init__(self, outcome: CommandResult) -> None:
        self.outcome = outcome
        self.calls = []

    def __call__(
        self, name: CommandName, arguments: tuple[str, ...] = ()
    ) -> CommandResult:
        self.calls.append((name, arguments))
        return self.outcome


def _collect(outcome: CommandResult) -> OmarchyAvailability:
    runner = RecordedRunner(outcome)
    result = collect_omarchy_availability(runner)
    assert runner.calls == [(CommandName.OMARCHY_UPDATE_AVAILABLE, ())]
    return result


def _package(name: str, installed: str, candidate: str) -> NormalizedItem:
    return NormalizedItem(
        ItemId(f"omarchy:{name}"),
        ItemSource.OMARCHY,
        name,
        installed,
        candidate,
        WatchMode.OFF,
        True,
        Provenance.LIVE,
    )


def _development_checkout(behind: int, upstream: str) -> NormalizedItem:
    suffix = "commit" if behind == 1 else "commits"
    return NormalizedItem(
        ItemId("omarchy:dev-checkout"),
        ItemSource.OMARCHY,
        "Omarchy development checkout",
        None,
        f"{behind} new {suffix} on {upstream}",
        WatchMode.OFF,
        False,
        Provenance.LIVE,
    )


def test_collect_omarchy_availability_returns_fresh_empty_for_exact_healthy_exit() -> (
    None
):
    # Given: the installed command's exact healthy exit-one message.
    outcome = CommandExited(1, b"Omarchy is up to date\n", b"")

    # When: Omarchy availability is collected through the injected runner.
    result = _collect(outcome)

    # Then: the source is fresh and empty rather than degraded.
    assert result == OmarchyAvailability(SourceStatus.OK, (), None)


def test_collect_omarchy_availability_normalizes_package_update() -> None:
    # Given: the package row emitted by the installed command source.
    outcome = CommandSucceeded(b"omarchy 4.0.0-1 -> 4.0.1-1\n", b"")

    # When: Omarchy availability is collected.
    result = _collect(outcome)

    # Then: the package has a stable watchable Omarchy ID.
    assert result == OmarchyAvailability(
        SourceStatus.OK,
        (_package("omarchy", "4.0.0-1", "4.0.1-1"),),
        None,
    )


def test_collect_omarchy_availability_preserves_opaque_package_versions() -> None:
    # Given: a valid checkupdates row with opaque Arch version strings.
    outcome = CommandSucceeded(
        b"omarchy 1:4.0.0.r7.gabcdef-2 -> 2026.08+git.r9.gfedcba-1\n", b""
    )

    # When: Omarchy availability is collected.
    result = _collect(outcome)

    # Then: version tokens remain unchanged data rather than parsed semantics.
    assert result == OmarchyAvailability(
        SourceStatus.OK,
        (_package("omarchy", "1:4.0.0.r7.gabcdef-2", "2026.08+git.r9.gfedcba-1"),),
        None,
    )


def test_collect_omarchy_availability_rejects_package_row_without_arrow() -> None:
    # Given: the obsolete package row shape without checkupdates' literal arrow.
    outcome = CommandSucceeded(b"omarchy 4.0.0-1 4.0.1-1\n", b"")

    # When: Omarchy availability is collected.
    result = _collect(outcome)

    # Then: unproven whitespace-only syntax cannot create an update item.
    assert result.status is SourceStatus.INVALID
    assert result.items == ()


def test_collect_omarchy_availability_marks_development_checkout_non_watchable() -> (
    None
):
    # Given: the development-checkout row emitted when the checkout is behind.
    outcome = CommandSucceeded(
        b"omarchy-dev-checkout 2 new commits on origin/main\n", b""
    )

    # When: Omarchy availability is collected.
    result = _collect(outcome)

    # Then: the checkout row cannot be watched as a package.
    assert result == OmarchyAvailability(
        SourceStatus.OK,
        (_development_checkout(2, "origin/main"),),
        None,
    )


def test_collect_omarchy_availability_normalizes_both_proven_row_types() -> None:
    # Given: one checkout row and one omarchy-dev package row.
    outcome = CommandSucceeded(
        b"omarchy-dev-checkout 1 new commit on origin/main\nomarchy-dev 4.0.0-1 -> 4.0.1-1\n",
        b"",
    )

    # When: Omarchy availability is collected.
    result = _collect(outcome)

    # Then: each independent update remains a distinct normalized item.
    assert result == OmarchyAvailability(
        SourceStatus.OK,
        (
            _development_checkout(1, "origin/main"),
            _package("omarchy-dev", "4.0.0-1", "4.0.1-1"),
        ),
        None,
    )


@pytest.mark.parametrize(
    ("outcome", "status"),
    (
        (
            CommandMissing("/usr/bin/omarchy-update-available"),
            SourceStatus.MISSING_DEPENDENCY,
        ),
        (CommandTimedOut(b"", b"slow"), SourceStatus.TIMEOUT),
        (CommandOutputExceeded("stdout", b"password=secret", b""), SourceStatus.ERROR),
        (CommandRejected("token=secret"), SourceStatus.ERROR),
    ),
)
def test_collect_omarchy_availability_reports_typed_runner_failures(
    outcome: CommandResult, status: SourceStatus
) -> None:
    # Given: a typed runner failure with potentially sensitive diagnostics.

    # When: Omarchy availability is collected.
    result = _collect(outcome)

    # Then: the failure is never represented as fresh availability.
    assert result.status is status
    assert result.items == ()
    assert result.diagnostic is not None
    assert "secret" not in result.diagnostic


def test_collect_omarchy_availability_rejects_malformed_row() -> None:
    # Given: an output row with an unproven fourth field.
    outcome = CommandSucceeded(b"omarchy 4.0.0-1 -> 4.0.1-1 unexpected\n", b"")

    # When: Omarchy availability is collected.
    result = _collect(outcome)

    # Then: malformed external text cannot become a partial update list.
    assert result.status is SourceStatus.INVALID
    assert result.items == ()


def test_collect_omarchy_availability_rejects_duplicate_package_row() -> None:
    # Given: the same package appears twice in command output.
    outcome = CommandSucceeded(
        b"omarchy 4.0.0-1 -> 4.0.1-1\nomarchy 4.0.0-1 -> 4.0.1-1\n",
        b"",
    )

    # When: Omarchy availability is collected.
    result = _collect(outcome)

    # Then: it fails closed rather than silently merging duplicate state.
    assert result.status is SourceStatus.INVALID
    assert result.items == ()


def test_collect_omarchy_availability_rejects_successful_empty_output() -> None:
    # Given: a nominal success with no update rows.
    outcome = CommandSucceeded(b"", b"")

    # When: Omarchy availability is collected.
    result = _collect(outcome)

    # Then: missing evidence cannot become a healthy empty result.
    assert result.status is SourceStatus.INVALID
    assert result.items == ()


def test_collect_omarchy_availability_rejects_healthy_stdout_with_stderr() -> None:
    # Given: the healthy stdout is accompanied by unexpected stderr evidence.
    outcome = CommandExited(1, b"Omarchy is up to date\n", b"warning\n")

    # When: Omarchy availability is collected.
    result = _collect(outcome)

    # Then: the exact healthy contract is not satisfied.
    assert result.status is SourceStatus.ERROR
    assert result.items == ()


def test_collect_omarchy_availability_rejects_healthy_stdout_with_extra_text() -> None:
    # Given: an exit-one stdout that extends the exact healthy message.
    outcome = CommandExited(1, b"Omarchy is up to date\nextra\n", b"")

    # When: Omarchy availability is collected.
    result = _collect(outcome)

    # Then: a prefix match cannot be mistaken for fresh empty evidence.
    assert result.status is SourceStatus.ERROR
    assert result.items == ()


@pytest.mark.parametrize(
    "outcome",
    (
        CommandExited(1, b"Omarchy est a jour\n", b""),
        CommandExited(3, b"unexpected\n", b""),
    ),
)
def test_collect_omarchy_availability_rejects_unexpected_nonzero_output(
    outcome: CommandResult,
) -> None:
    # Given: an exit whose text and status do not prove the healthy condition.

    # When: Omarchy availability is collected.
    result = _collect(outcome)

    # Then: arbitrary exit-one prose and other exits are errors, never healthy empty.
    assert result.status is SourceStatus.ERROR
    assert result.items == ()


def test_omarchy_duplicate_filter_is_exact_and_immutable() -> None:
    # Given: the package names whose generic rows Omarchy owns.

    # When: the exported duplicate filter is inspected.
    duplicate_filter = OMARCHY_DUPLICATE_FILTER

    # Then: it contains exactly the two immutable Omarchy package names.
    assert duplicate_filter == frozenset({"omarchy", "omarchy-dev"})
