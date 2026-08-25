from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "helper"))

from opatchy_helper import runner
from opatchy_helper.adapters.arch import (
    ArchDegraded,
    ArchFailure,
    ArchUpdates,
    ForeignInventory,
    collect_foreign_inventory,
    collect_official_updates,
)
from opatchy_helper.runner_types import (
    CommandExited,
    CommandMissing,
    CommandName,
    CommandOutputExceeded,
    CommandRejected,
    CommandResult,
    CommandSucceeded,
    CommandTimedOut,
)


class RecordingRunner:
    def __init__(self, responses: tuple[CommandResult, ...]) -> None:
        self.requests: list[tuple[CommandName, tuple[str, ...]]] = []
        self._responses: Iterator[CommandResult] = iter(responses)

    def __call__(
        self, name: CommandName, arguments: tuple[str, ...] = ()
    ) -> CommandResult:
        self.requests.append((name, arguments))
        return next(self._responses)


def test_collect_official_updates_when_checkupdates_exits_two_returns_fresh_empty_result() -> (
    None
):
    # Given: a native inventory and checkupdates' documented no-update exit code.
    command_runner = RecordingRunner(
        (
            CommandSucceeded(b"linux 6.12.1-1\nomarchy 1.0-1\n", b""),
            CommandExited(2, b"", b""),
        )
    )

    # When: official updates are collected.
    result = collect_official_updates(command_runner)

    # Then: the empty result is fresh and only fixed command specs were used.
    assert result == ArchUpdates(())
    assert command_runner.requests == [
        (CommandName.PACMAN_NATIVE, ()),
        (CommandName.CHECKUPDATES, ()),
    ]


def test_collect_official_updates_when_checkupdates_succeeds_without_rows_degrades() -> (
    None
):
    # Given: a native inventory and an impossible empty checkupdates success.
    command_runner = RecordingRunner(
        (
            CommandSucceeded(b"linux 6.12.1-1\n", b""),
            CommandSucceeded(b"", b""),
        )
    )

    # When: official updates are collected.
    result = collect_official_updates(command_runner)

    # Then: empty success is invalid evidence, not a fresh empty update result.
    assert result == ArchDegraded(
        ArchFailure.MALFORMED_ROW, "empty checkupdates output"
    )


def test_collect_official_updates_when_rows_join_exact_inventory_and_filter_omarchy() -> (
    None
):
    # Given: native inventory and update rows including only exact Omarchy names.
    command_runner = RecordingRunner(
        (
            CommandSucceeded(
                b"linux 6.12.1-1\nomarchy 1.0-1\nomarchy-dev 1.0-1\nomarchy-tools 1.0-1\n",
                b"",
            ),
            CommandSucceeded(
                b"\n".join(
                    (
                        b"linux 1:6.12.2-1 -> 1:6.12.3-1",
                        b"omarchy 1.0-1 -> 1.1-1",
                        b"omarchy-dev 1.0-1 -> 1.1-1",
                        b"omarchy-tools 1.0-1 -> 1.1-1",
                    )
                )
                + b"\n",
                b"",
            ),
        )
    )

    # When: official updates are collected.
    result = collect_official_updates(command_runner)

    # Then: exact names join, native strings remain opaque, and prefix names remain.
    match result:
        case ArchUpdates(items=items):
            assert len(items) == 2
            assert items[0].item_id == "arch:linux"
            assert items[0].installed == "1:6.12.2-1"
            assert items[0].candidate == "1:6.12.3-1"
            assert items[0].watch_mode.value == "off"
            assert items[0].watchable is True
            assert items[1].item_id == "arch:omarchy-tools"
        case ArchDegraded() as degraded:
            raise AssertionError(degraded)


def test_collect_official_updates_when_update_is_absent_from_native_inventory_degrades() -> (
    None
):
    # Given: an update that cannot be joined to pacman -Qn output.
    command_runner = RecordingRunner(
        (
            CommandSucceeded(b"linux 6.12.1-1\n", b""),
            CommandSucceeded(b"foreign 1.0-1 -> 1.1-1\n", b""),
        )
    )

    # When: official updates are collected.
    result = collect_official_updates(command_runner)

    # Then: the ambiguity is surfaced instead of creating an official item.
    assert result == ArchDegraded(ArchFailure.MISSING_NATIVE_PACKAGE, "foreign")


def test_collect_official_updates_when_rows_are_malformed_or_duplicate_degrades() -> (
    None
):
    # Given: a valid native inventory and ambiguous update output.
    malformed_runner = RecordingRunner(
        (
            CommandSucceeded(b"linux 6.12.1-1\n", b""),
            CommandSucceeded(b"linux 6.12.1-1 6.12.2-1\n", b""),
        )
    )
    duplicate_runner = RecordingRunner(
        (
            CommandSucceeded(b"linux 6.12.1-1\n", b""),
            CommandSucceeded(
                b"linux 6.12.1-1 -> 6.12.2-1\nlinux 6.12.1-1 -> 6.12.2-1\n",
                b"",
            ),
        )
    )

    # When: each ambiguous output is collected.
    malformed = collect_official_updates(malformed_runner)
    duplicate = collect_official_updates(duplicate_runner)

    # Then: neither ambiguity is silently accepted.
    assert malformed == ArchDegraded(
        ArchFailure.MALFORMED_ROW, "linux 6.12.1-1 6.12.2-1"
    )
    assert duplicate == ArchDegraded(ArchFailure.DUPLICATE_PACKAGE, "linux")


def test_collect_official_updates_when_inventory_has_duplicate_rows_degrades() -> None:
    # Given: duplicate package names in pacman -Qn output.
    command_runner = RecordingRunner(
        (CommandSucceeded(b"linux 6.12.1-1\nlinux 6.12.2-1\n", b""),)
    )

    # When: official updates are collected.
    result = collect_official_updates(command_runner)

    # Then: checkupdates is not called after invalid inventory.
    assert result == ArchDegraded(ArchFailure.DUPLICATE_PACKAGE, "linux")
    assert command_runner.requests == [(CommandName.PACMAN_NATIVE, ())]


def test_collect_official_updates_when_runner_cannot_produce_updates_degrades() -> None:
    # Given: missing, timed-out, overflowed, and failed command outcomes.
    missing_runner = RecordingRunner((CommandMissing("pacman missing"),))
    timeout_runner = RecordingRunner(
        (
            CommandSucceeded(b"linux 6.12.1-1\n", b""),
            CommandTimedOut(b"", b""),
        )
    )
    overflow_runner = RecordingRunner(
        (
            CommandSucceeded(b"linux 6.12.1-1\n", b""),
            CommandOutputExceeded("stdout", b"", b""),
        )
    )
    failed_runner = RecordingRunner(
        (
            CommandSucceeded(b"linux 6.12.1-1\n", b""),
            CommandExited(1, b"", b"sync failed"),
        )
    )

    # When: each command outcome is collected.
    missing = collect_official_updates(missing_runner)
    timeout = collect_official_updates(timeout_runner)
    overflow = collect_official_updates(overflow_runner)
    failed = collect_official_updates(failed_runner)

    # Then: failures are degraded, never reported as fresh inventory.
    assert missing == ArchDegraded(ArchFailure.COMMAND_MISSING, "pacman missing")
    assert timeout == ArchDegraded(ArchFailure.COMMAND_TIMED_OUT, "checkupdates")
    assert overflow == ArchDegraded(
        ArchFailure.COMMAND_OUTPUT_EXCEEDED, "checkupdates: stdout"
    )
    assert failed == ArchDegraded(ArchFailure.COMMAND_EXITED, "checkupdates: exit 1")


def test_collect_foreign_inventory_when_successful_uses_only_pacman_foreign() -> None:
    # Given: foreign package inventory output.
    command_runner = RecordingRunner((CommandSucceeded(b"paru 2.0-1\n", b""),))

    # When: foreign inventory is collected for Todo 9.
    result = collect_foreign_inventory(command_runner)

    # Then: its records remain separate from official normalized update items.
    match result:
        case ForeignInventory(records=records):
            assert records[0].name == "paru"
            assert records[0].installed == "2.0-1"
        case ArchDegraded() as degraded:
            raise AssertionError(degraded)
    assert command_runner.requests == [(CommandName.PACMAN_FOREIGN, ())]


def test_collect_official_updates_when_inventory_or_update_encoding_is_invalid_degrades() -> (
    None
):
    # Given: invalid UTF-8 at either output parsing boundary.
    inventory_runner = RecordingRunner((CommandSucceeded(b"\xff", b""),))
    update_runner = RecordingRunner(
        (
            CommandSucceeded(b"linux 6.12.1-1\n", b""),
            CommandSucceeded(b"\xff", b""),
        )
    )

    # When: official updates are collected.
    inventory_result = collect_official_updates(inventory_runner)
    update_result = collect_official_updates(update_runner)

    # Then: encoding failures are explicit malformed rows.
    expected = ArchDegraded(ArchFailure.MALFORMED_ROW, "non-UTF-8 output")
    assert inventory_result == expected
    assert update_result == expected


def test_collect_official_updates_when_rows_have_invalid_field_counts_degrades() -> (
    None
):
    # Given: malformed native and checkupdates record shapes.
    native_runner = RecordingRunner((CommandSucceeded(b"linux\n", b""),))
    update_runner = RecordingRunner(
        (
            CommandSucceeded(b"linux 6.12.1-1\n", b""),
            CommandSucceeded(b"linux 6.12.1-1 -> 6.12.2-1 extra\n", b""),
        )
    )

    # When: official updates are collected.
    native_result = collect_official_updates(native_runner)
    update_result = collect_official_updates(update_runner)

    # Then: neither parser accepts ambiguous field counts.
    assert native_result == ArchDegraded(ArchFailure.MALFORMED_ROW, "linux")
    assert update_result == ArchDegraded(
        ArchFailure.MALFORMED_ROW, "linux 6.12.1-1 -> 6.12.2-1 extra"
    )


def test_collect_foreign_inventory_when_command_is_rejected_degrades() -> None:
    # Given: a closed runner rejection for pacman -Qm.
    command_runner = RecordingRunner((CommandRejected("rejected"),))

    # When: foreign inventory is collected.
    result = collect_foreign_inventory(command_runner)

    # Then: the separate seam returns a typed degradation.
    assert result == ArchDegraded(ArchFailure.COMMAND_REJECTED, "rejected")


def test_runner_rejects_mutating_arguments_without_creating_sentinel() -> None:
    # Given: an unmodified runner registry and an absent injection sentinel.
    sentinel = Path("/tmp/opatchy-injection-sentinel")
    assert not sentinel.exists()

    # When: callers attempt mutating pacman and checkupdates arguments.
    native_result = runner.run_command(CommandName.PACMAN_NATIVE, ("-Sy",))
    updates_result = runner.run_command(CommandName.CHECKUPDATES, ("--download",))

    # Then: the closed runner rejects them before any subprocess can run.
    match native_result:
        case CommandRejected():
            pass
        case unexpected:
            raise AssertionError(unexpected)
    match updates_result:
        case CommandRejected():
            pass
        case unexpected:
            raise AssertionError(unexpected)
    assert not sentinel.exists()
