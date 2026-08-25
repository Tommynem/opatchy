from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3] / "helper"))

from opatchy_helper.adapters.aur import (
    AurCollected,
    AurCommandFailed,
    AurCommandRejected,
    AurForeignInventoryDegraded,
    AurHelper,
    AurInvalid,
    AurMissingDependency,
    AurNotApplicable,
    AurOutputExceeded,
    AurTimedOut,
    collect_aur_updates,
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

    def __call__(self, name: CommandName, arguments: tuple[str, ...]) -> CommandResult:
        self.requests.append((name, arguments))
        return next(self._responses)


def test_collect_aur_updates_when_no_foreign_packages_is_not_applicable() -> None:
    # Given: pacman has no foreign packages.
    run = RecordingRunner((CommandSucceeded(b"", b""),))

    # When: AUR update collection begins.
    result = collect_aur_updates(run)

    # Then: no helper is invoked because AUR is not applicable.
    assert result == AurNotApplicable()
    assert run.requests == [(CommandName.PACMAN_FOREIGN, ())]


def test_collect_aur_updates_prefers_yay_and_preserves_opaque_versions() -> None:
    # Given: foreign inventory and a yay update with non-SemVer version strings.
    run = RecordingRunner(
        (
            CommandSucceeded(b"foo old+custom\n", b""),
            CommandSucceeded(b"foo old+custom -> next@edge\n", b""),
        )
    )

    # When: AUR updates are collected.
    result = collect_aur_updates(run)

    # Then: yay is recorded as provenance and versions are unmodified data.
    assert isinstance(result, AurCollected)
    assert result.helper is AurHelper.YAY
    assert result.items[0].item_id == "aur:foo"
    assert result.items[0].label == "foo"
    assert result.items[0].installed == "old+custom"
    assert result.items[0].candidate == "next@edge"
    assert result.items[0].source.value == "aur"
    assert run.requests == [
        (CommandName.PACMAN_FOREIGN, ()),
        (CommandName.YAY_UPDATES, ()),
    ]


def test_collect_aur_updates_uses_paru_only_when_yay_is_missing() -> None:
    # Given: yay is absent and paru has update evidence.
    run = RecordingRunner(
        (
            CommandSucceeded(b"foo 1\n", b""),
            CommandMissing("yay missing"),
            CommandSucceeded(b"foo 1 -> 2\n", b""),
        )
    )

    # When: AUR updates are collected.
    result = collect_aur_updates(run)

    # Then: paru is the sole fallback and its provenance is retained.
    assert isinstance(result, AurCollected)
    assert result.helper is AurHelper.PARU
    assert result.items[0].item_id == "aur:foo"
    assert run.requests == [
        (CommandName.PACMAN_FOREIGN, ()),
        (CommandName.YAY_UPDATES, ()),
        (CommandName.PARU_UPDATES, ()),
    ]


def test_collect_aur_updates_when_both_helpers_exist_does_not_invoke_paru() -> None:
    # Given: yay returns valid evidence while paru would also be available.
    run = RecordingRunner(
        (
            CommandSucceeded(b"foo 1\n", b""),
            CommandSucceeded(b"foo 1 -> 2\n", b""),
        )
    )

    # When: AUR updates are collected.
    result = collect_aur_updates(run)

    # Then: yay wins without probing paru.
    assert isinstance(result, AurCollected)
    assert result.helper is AurHelper.YAY
    assert run.requests == [
        (CommandName.PACMAN_FOREIGN, ()),
        (CommandName.YAY_UPDATES, ()),
    ]


def test_collect_aur_updates_when_neither_helper_exists_is_degraded() -> None:
    # Given: foreign packages but no supported helper.
    run = RecordingRunner(
        (
            CommandSucceeded(b"foo 1\n", b""),
            CommandMissing("yay missing"),
            CommandMissing("paru missing"),
        )
    )

    # When: AUR updates are collected.
    result = collect_aur_updates(run)

    # Then: coverage is explicitly degraded as a missing dependency.
    assert result == AurMissingDependency()


def test_collect_aur_updates_when_helper_output_is_empty_is_fresh_empty_evidence() -> (
    None
):
    # Given: foreign packages and a successful helper with no update rows.
    run = RecordingRunner(
        (CommandSucceeded(b"foo 1\n", b""), CommandSucceeded(b"", b""))
    )

    # When: AUR updates are collected.
    result = collect_aur_updates(run)

    # Then: empty success is truthful fresh evidence, not an applicability failure.
    assert result == AurCollected(AurHelper.YAY, ())


@pytest.mark.parametrize(
    "output",
    [
        b"foo 1 2\n",
        b"foo 1 -> 2 extra\n",
        b"foo 1 -> 2\nfoo 1 -> 3\n",
        b"missing 1 -> 2\n",
        b"\xff",
    ],
)
def test_collect_aur_updates_rejects_malformed_or_unmatched_rows(output: bytes) -> None:
    # Given: a foreign inventory and output that cannot be exactly joined to it.
    run = RecordingRunner(
        (CommandSucceeded(b"foo 1\n", b""), CommandSucceeded(output, b""))
    )

    # When: AUR updates are collected.
    result = collect_aur_updates(run)

    # Then: no ambiguous helper row becomes an item.
    assert isinstance(result, AurInvalid)


@pytest.mark.parametrize(
    ("helper_result", "expected"),
    [
        (CommandTimedOut(b"", b""), AurTimedOut(AurHelper.YAY)),
        (
            CommandOutputExceeded("stdout", b"", b""),
            AurOutputExceeded(AurHelper.YAY, "stdout"),
        ),
        (CommandRejected("policy"), AurCommandRejected(AurHelper.YAY, "policy")),
        (CommandExited(1, b"", b"failure"), AurCommandFailed(AurHelper.YAY, 1)),
    ],
)
def test_collect_aur_updates_keeps_yay_failures_fail_closed_without_paru_fallback(
    helper_result: CommandResult,
    expected: AurTimedOut | AurOutputExceeded | AurCommandRejected | AurCommandFailed,
) -> None:
    # Given: yay exists but cannot produce trusted evidence.
    run = RecordingRunner((CommandSucceeded(b"foo 1\n", b""), helper_result))

    # When: AUR updates are collected.
    result = collect_aur_updates(run)

    # Then: its failure is retained and paru is not silently substituted.
    assert result == expected
    assert run.requests == [
        (CommandName.PACMAN_FOREIGN, ()),
        (CommandName.YAY_UPDATES, ()),
    ]


def test_collect_aur_updates_when_foreign_inventory_fails_degrades_without_helper() -> (
    None
):
    # Given: pacman -Qm exceeds its bounded stdout limit.
    run = RecordingRunner((CommandOutputExceeded("stdout", b"", b""),))

    # When: AUR updates are collected.
    result = collect_aur_updates(run)

    # Then: the inventory failure remains visible and no helper is called.
    assert isinstance(result, AurForeignInventoryDegraded)
    assert run.requests == [(CommandName.PACMAN_FOREIGN, ())]


def test_collect_aur_updates_keeps_collision_as_aur_identity_without_security_claim() -> (
    None
):
    # Given: a foreign package whose name is also plausible as an official package.
    run = RecordingRunner(
        (
            CommandSucceeded(b"openssl 3.0-custom\n", b""),
            CommandSucceeded(b"openssl 3.0-custom -> 3.1-custom\n", b""),
        )
    )

    # When: AUR updates are collected.
    result = collect_aur_updates(run)

    # Then: identity and source remain AUR, with no path to an Arch security item.
    assert isinstance(result, AurCollected)
    assert result.items[0].item_id == "aur:openssl"
    assert result.items[0].source.value == "aur"


def test_collect_aur_updates_keeps_hostile_label_as_data_without_injection() -> None:
    # Given: a foreign package label containing shell metacharacters.
    sentinel = Path("/tmp/opatchy-injection-sentinel")
    sentinel.unlink(missing_ok=True)
    name = "evil;touch-/tmp/opatchy-injection-sentinel"
    run = RecordingRunner(
        (
            CommandSucceeded(f"{name} 1\n".encode(), b""),
            CommandSucceeded(f"{name} 1 -> 2\n".encode(), b""),
        )
    )

    # When: AUR updates are collected.
    result = collect_aur_updates(run)

    # Then: the hostile label is data only and helper argv stays closed.
    assert isinstance(result, AurCollected)
    assert result.items[0].label == name
    assert run.requests == [
        (CommandName.PACMAN_FOREIGN, ()),
        (CommandName.YAY_UPDATES, ()),
    ]
    assert not sentinel.exists()
