from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "helper"))

from opatchy_helper.adapters.arch import (
    ArchDegraded,
    ArchFailure,
    VersionComparison,
    compare_versions,
)
from opatchy_helper.runner_types import (
    CommandName,
    CommandResult,
    CommandSucceeded,
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


def test_compare_versions_when_epoch_pkgrel_is_higher_uses_vercmp_result() -> None:
    # Given: vercmp's native positive comparison for epoch/pkgrel strings.
    command_runner = RecordingRunner((CommandSucceeded(b"1\n", b""),))

    # When: opaque versions are compared.
    result = compare_versions(command_runner, "1:2.0-1", "2.0-1")

    # Then: the native sign is returned without Python version parsing.
    assert result == VersionComparison(1)
    assert command_runner.requests == [
        (CommandName.VERCMP, ("1:2.0-1", "2.0-1")),
    ]


def test_compare_versions_when_equal_returns_zero() -> None:
    # Given: vercmp's equality output.
    command_runner = RecordingRunner((CommandSucceeded(b"0\n", b""),))

    # When: identical opaque versions are compared.
    result = compare_versions(command_runner, "2.0-1", "2.0-1")

    # Then: equality is preserved.
    assert result == VersionComparison(0)


def test_compare_versions_when_fixed_version_is_lower_returns_negative_one() -> None:
    # Given: vercmp's native lower result.
    command_runner = RecordingRunner((CommandSucceeded(b"-1\n", b""),))

    # When: a lower fixed version is compared to its candidate.
    result = compare_versions(command_runner, "2.0-1", "1:2.0-1")

    # Then: only vercmp's negative sign determines the outcome.
    assert result == VersionComparison(-1)


def test_compare_versions_when_output_is_not_a_native_sign_degrades() -> None:
    # Given: malformed vercmp output.
    command_runner = RecordingRunner((CommandSucceeded(b"2\n", b""),))

    # When: versions are compared.
    result = compare_versions(command_runner, "2.0-1", "2.0-2")

    # Then: no Python fallback comparison is attempted.
    assert result == ArchDegraded(ArchFailure.INVALID_VERCMP_OUTPUT, "2")


def test_compare_versions_when_output_is_not_utf8_degrades() -> None:
    # Given: a non-text native output.
    command_runner = RecordingRunner((CommandSucceeded(b"\xff", b""),))

    # When: opaque versions are compared.
    result = compare_versions(command_runner, "2.0-1", "2.0-2")

    # Then: the adapter cannot use a fallback comparator.
    assert result == ArchDegraded(ArchFailure.INVALID_VERCMP_OUTPUT, "non-UTF-8 output")
