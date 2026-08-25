from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import pytest

HELPER_ROOT = Path(__file__).resolve().parents[3] / "helper"
sys.path.insert(0, str(HELPER_ROOT))

from opatchy_helper.adapters import mise
from opatchy_helper.runner import (
    COMMAND_SPECS,
    CommandExited,
    CommandMissing,
    CommandName,
    CommandOutputExceeded,
    CommandRejected,
    CommandResult,
    CommandSucceeded,
    CommandTimedOut,
)

Runner = Callable[[CommandName, tuple[str, ...]], CommandResult]


def _runner_for(
    result: CommandResult,
) -> tuple[Runner, list[tuple[CommandName, tuple[str, ...]]]]:
    requests: list[tuple[CommandName, tuple[str, ...]]] = []

    def run(name: CommandName, arguments: tuple[str, ...]) -> CommandResult:
        requests.append((name, arguments))
        return result

    return run, requests


def test_collect_mise_updates_returns_not_applicable_for_empty_object() -> None:
    # Given: mise has no outdated global/home tools.
    run, requests = _runner_for(CommandSucceeded(b"{}", b""))

    # When: the read-only adapter collects its single source.
    result = mise.collect_mise_updates(run)

    # Then: the source is not applicable and requests only the closed command.
    assert isinstance(result, mise.MiseNotApplicable)
    assert requests == [(CommandName.MISE_OUTDATED, ())]
    assert COMMAND_SPECS[CommandName.MISE_OUTDATED].cwd == Path.home()


def test_collect_mise_updates_preserves_multiple_backend_qualified_records() -> None:
    # Given: mise reports backend-qualified names and opaque non-SemVer values.
    payload = b"""{
        "core:node": {"requested": "lts/*", "current": "v20.0.0-custom", "latest": "nightly"},
        "aqua:golangci/golangci-lint": {"requested": "v2", "current": "old+build", "latest": "next@edge"}
    }"""
    run, _ = _runner_for(CommandSucceeded(payload, b""))

    # When: the adapter normalizes the update records.
    result = mise.collect_mise_updates(run)

    # Then: IDs and display/fingerprint strings remain exactly opaque input data.
    assert isinstance(result, mise.MiseCollected)
    assert [
        (record.item.item_id, record.requested, record.current, record.latest)
        for record in result.records
    ] == [
        ("mise:core:node", "lts/*", "v20.0.0-custom", "nightly"),
        ("mise:aqua:golangci/golangci-lint", "v2", "old+build", "next@edge"),
    ]


@pytest.mark.parametrize(
    "payload",
    [
        b'{"node": {"current": "20.0.0", "latest": "20.1.0"}}',
        b'{"node": {"requested": "20", "latest": "20.1.0"}}',
        b'{"node": {"requested": "20", "current": "20.0.0"}}',
        b'{"node": {"requested": true, "current": "20.0.0", "latest": "20.1.0"}}',
        b'{"node": {"requested": "20", "current": null, "latest": "20.1.0"}}',
        b'{"node": ["20", "20.0.0", "20.1.0"]}',
        b'[{"node": {"requested": "20", "current": "20.0.0", "latest": "20.1.0"}}]',
    ],
)
def test_collect_mise_updates_rejects_partial_or_wrongly_typed_records(
    payload: bytes,
) -> None:
    # Given: JSON that is syntactically valid but not the complete documented record shape.
    run, _ = _runner_for(CommandSucceeded(payload, b""))

    # When: the adapter parses mise output.
    result = mise.collect_mise_updates(run)

    # Then: it exposes invalid evidence instead of guessing omitted values.
    assert isinstance(result, mise.MiseInvalid)


@pytest.mark.parametrize(
    "payload",
    [
        b'{"node": {"requested": "20", "current": "20.0.0", "latest": NaN}}',
        b'{"node": {"requested": "20", "current": "20.0.0", "latest": "20.1.0"}, "node": {"requested": "21", "current": "21.0.0", "latest": "21.1.0"}}',
        b'{"\\uD800": {"requested": "20", "current": "20.0.0", "latest": "20.1.0"}}',
        b"{",
    ],
)
def test_collect_mise_updates_rejects_malformed_json(payload: bytes) -> None:
    # Given: output rejected by the shared strict JSON boundary.
    run, _ = _runner_for(CommandSucceeded(payload, b""))

    # When: collection attempts to decode the output.
    result = mise.collect_mise_updates(run)

    # Then: malformed evidence remains explicit.
    assert isinstance(result, mise.MiseInvalid)


@pytest.mark.parametrize(
    ("command_result", "expected_type"),
    [
        (CommandMissing("not installed"), mise.MiseNotApplicable),
        (CommandTimedOut(b"", b""), mise.MiseTimedOut),
        (CommandOutputExceeded("stdout", b"", b""), mise.MiseOutputExceeded),
        (CommandExited(2, b"", b"error"), mise.MiseCommandFailed),
        (CommandRejected("policy"), mise.MiseCommandRejected),
    ],
)
def test_collect_mise_updates_exposes_runner_failures(
    command_result: CommandResult,
    expected_type: type[mise.MiseResult],
) -> None:
    # Given: one typed runner outcome that is not successful output.
    run, _ = _runner_for(command_result)

    # When: mise collection handles the outcome.
    result = mise.collect_mise_updates(run)

    # Then: missing is not-applicable while operational failures remain distinct.
    assert isinstance(result, expected_type)


def test_collect_mise_updates_keeps_hostile_tool_key_as_data(tmp_path: Path) -> None:
    # Given: a key that would be dangerous only if interpolated into a shell command.
    sentinel = Path("/tmp/opatchy-injection-sentinel")
    sentinel.unlink(missing_ok=True)
    key = "core:node; touch /tmp/opatchy-injection-sentinel"
    payload = (
        '{"' + key + '": {"requested": "20", "current": "20.0.0", "latest": "20.1.0"}}'
    ).encode()
    run, requests = _runner_for(CommandSucceeded(payload, b""))

    # When: the adapter observes the hostile key.
    result = mise.collect_mise_updates(run)

    # Then: it remains opaque data and no side effect occurs.
    assert isinstance(result, mise.MiseCollected)
    assert result.records[0].item.item_id == f"mise:{key}"
    assert requests == [(CommandName.MISE_OUTDATED, ())]
    assert not sentinel.exists()
    assert not tmp_path.joinpath("opatchy-injection-sentinel").exists()
