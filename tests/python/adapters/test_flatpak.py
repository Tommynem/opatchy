from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

HELPER_ROOT = Path(__file__).resolve().parents[3] / "helper"
sys.path.insert(0, str(HELPER_ROOT))

from opatchy_helper.adapters.flatpak import (
    FlatpakScope,
    FlatpakScopeStatus,
    collect_flatpak,
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

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "flatpak"


class RecordingRunner:
    def __init__(self, results: Iterator[CommandResult]) -> None:
        self._results: Iterator[CommandResult] = results
        self.calls: list[CommandName] = []

    def __call__(self, name: CommandName) -> CommandResult:
        self.calls.append(name)
        return next(self._results)


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _succeeded(name: str) -> CommandSucceeded:
    return CommandSucceeded(_fixture(name), b"")


def test_collect_flatpak_keeps_scopes_refs_and_runtime_distinct() -> None:
    # Given: user and system inventory, including an app/runtime pair and duplicate app ID.
    runner = RecordingRunner(
        iter(
            (
                _succeeded("user-list.tsv"),
                _succeeded("user-updates.tsv"),
                _succeeded("system-list.tsv"),
                _succeeded("system-updates.tsv"),
            )
        )
    )

    # When: both default Flatpak installations are collected.
    result = collect_flatpak(runner)

    # Then: IDs qualify the exact full ref by scope and opaque candidates remain display data.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.OK
    assert system.status is FlatpakScopeStatus.OK
    assert [record.item.item_id for record in user.records] == [
        "flatpak:user:app/org.mozilla.firefox/x86_64/stable",
        "flatpak:user:runtime/org.freedesktop.Platform/x86_64/24.08",
    ]
    assert user.records[0].kind == "app"
    assert user.records[0].application_id == "org.mozilla.firefox"
    assert user.records[0].arch == "x86_64"
    assert user.records[0].branch == "stable"
    assert user.records[0].origin == "flathub"
    assert user.records[0].item.installed == "124.0"
    assert user.records[0].item.candidate == "125.0"
    assert user.records[0].candidate_ref == "app/org.mozilla.firefox/x86_64/stable"
    assert user.records[1].kind == "runtime"
    assert user.records[1].item.candidate is None
    assert (
        system.records[0].item.item_id
        == "flatpak:system:app/org.mozilla.firefox/x86_64/stable"
    )
    assert system.records[0].item.candidate == "2026.08-rc1+build.7"
    assert runner.calls == [
        CommandName.FLATPAK_USER_LIST,
        CommandName.FLATPAK_USER_UPDATES,
        CommandName.FLATPAK_SYSTEM_LIST,
        CommandName.FLATPAK_SYSTEM_UPDATES,
    ]


def test_collect_flatpak_marks_empty_system_scope_not_applicable() -> None:
    # Given: a user installation with updates and a default system installation without refs.
    runner = RecordingRunner(
        iter(
            (
                _succeeded("user-list.tsv"),
                _succeeded("user-updates.tsv"),
                CommandSucceeded(b"", b""),
            )
        )
    )

    # When: collection checks both scopes independently.
    result = collect_flatpak(runner)

    # Then: only the empty scope is not applicable and does not need an update query.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.OK
    assert system.scope is FlatpakScope.SYSTEM
    assert system.status is FlatpakScopeStatus.NOT_APPLICABLE
    assert not system.records
    assert runner.calls == [
        CommandName.FLATPAK_USER_LIST,
        CommandName.FLATPAK_USER_UPDATES,
        CommandName.FLATPAK_SYSTEM_LIST,
    ]


def test_collect_flatpak_marks_both_empty_scopes_not_applicable() -> None:
    # Given: neither default Flatpak installation has installed refs.
    runner = RecordingRunner(
        iter((CommandSucceeded(b"", b""), CommandSucceeded(b"", b"")))
    )

    # When: collection checks the user and default system installations.
    result = collect_flatpak(runner)

    # Then: neither empty scope triggers a remote update query.
    assert [scope.status for scope in result.scopes] == [
        FlatpakScopeStatus.NOT_APPLICABLE,
        FlatpakScopeStatus.NOT_APPLICABLE,
    ]
    assert runner.calls == [
        CommandName.FLATPAK_USER_LIST,
        CommandName.FLATPAK_SYSTEM_LIST,
    ]


def test_collect_flatpak_keeps_system_only_inventory() -> None:
    # Given: user has no refs while the default system installation has an app update.
    runner = RecordingRunner(
        iter(
            (
                CommandSucceeded(b"", b""),
                _succeeded("system-list.tsv"),
                _succeeded("system-updates.tsv"),
            )
        )
    )

    # When: collection evaluates the two default scopes.
    result = collect_flatpak(runner)

    # Then: system-only records retain their own scope-qualified identity.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.NOT_APPLICABLE
    assert system.status is FlatpakScopeStatus.OK
    assert (
        system.records[0].item.item_id
        == "flatpak:system:app/org.mozilla.firefox/x86_64/stable"
    )


def test_collect_flatpak_rejects_duplicate_full_refs_within_a_scope() -> None:
    # Given: one inventory repeats a full ref that would otherwise duplicate a normalized ID.
    runner = RecordingRunner(
        iter(
            (
                _succeeded("duplicate-list.tsv"),
                CommandSucceeded(b"", b""),
                CommandSucceeded(b"", b""),
            )
        )
    )

    # When: collection validates the user inventory before producing records.
    result = collect_flatpak(runner)

    # Then: the invalid user scope cannot leak duplicate item IDs while system remains independent.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.INVALID
    assert user.diagnostic == "Flatpak inventory contains duplicate ref at row 2"
    assert system.status is FlatpakScopeStatus.NOT_APPLICABLE


def test_collect_flatpak_preserves_system_when_user_times_out() -> None:
    # Given: a timed-out user listing and a healthy default system installation.
    runner = RecordingRunner(
        iter(
            (
                CommandTimedOut(b"partial", b""),
                _succeeded("system-list.tsv"),
                _succeeded("system-updates.tsv"),
            )
        )
    )

    # When: collection reaches both scopes.
    result = collect_flatpak(runner)

    # Then: the timeout remains local and the system record remains usable.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.TIMEOUT
    assert not user.records
    assert system.status is FlatpakScopeStatus.OK
    assert len(system.records) == 1


def test_collect_flatpak_preserves_inventory_when_update_command_exits() -> None:
    # Given: valid user inventory followed by a nonzero read-only update query.
    runner = RecordingRunner(
        iter(
            (
                _succeeded("user-list.tsv"),
                CommandExited(23, b"", b"failure"),
                CommandSucceeded(b"", b""),
            )
        )
    )

    # When: collection joins the user update data.
    result = collect_flatpak(runner)

    # Then: the command failure is local while validated inventory remains available.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.ERROR
    assert len(user.records) == 2
    assert user.diagnostic == "Flatpak command exited with status 23"
    assert system.status is FlatpakScopeStatus.NOT_APPLICABLE


def test_collect_flatpak_bounds_rejected_command_diagnostics() -> None:
    # Given: the user command is rejected with an oversized diagnostic.
    runner = RecordingRunner(
        iter((CommandRejected("x" * 600), CommandSucceeded(b"", b"")))
    )

    # When: both default scopes are evaluated.
    result = collect_flatpak(runner)

    # Then: the user error is bounded and system evaluation still occurs.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.ERROR
    assert user.diagnostic == "x" * 512
    assert system.status is FlatpakScopeStatus.NOT_APPLICABLE


def test_collect_flatpak_reports_missing_binary_and_overflow_per_scope() -> None:
    # Given: Flatpak is missing for the user scope and the system inventory overflows.
    runner = RecordingRunner(
        iter(
            (
                CommandMissing("flatpak unavailable"),
                CommandOutputExceeded("stdout", b"", b"bounded"),
            )
        )
    )

    # When: both default scopes are collected.
    result = collect_flatpak(runner)

    # Then: each bounded runner failure is explicit and scoped.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.MISSING_DEPENDENCY
    assert system.status is FlatpakScopeStatus.OUTPUT_EXCEEDED
    assert user.diagnostic == "flatpak unavailable"
    assert system.diagnostic == "Flatpak stdout output exceeded its configured limit"


def test_collect_flatpak_rejects_malformed_explicit_columns() -> None:
    # Given: the user list no longer has the requested four tab-delimited columns.
    runner = RecordingRunner(
        iter(
            (
                _succeeded("malformed-list.tsv"),
                CommandSucceeded(b"", b""),
            )
        )
    )

    # When: collection parses the C-locale records.
    result = collect_flatpak(runner)

    # Then: changed output shape is invalid without preventing system evaluation.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.INVALID
    assert user.diagnostic == "Flatpak inventory row 1 has 2 columns; expected 4"
    assert system.status is FlatpakScopeStatus.NOT_APPLICABLE


def test_collect_flatpak_rejects_non_utf8_inventory_and_invalid_update_ref() -> None:
    # Given: user inventory is not UTF-8 and a system update has a non-Flatpak ref kind.
    runner = RecordingRunner(
        iter(
            (
                CommandSucceeded(b"\xff", b""),
                _succeeded("system-list.tsv"),
                CommandSucceeded(
                    b"extension/org.mozilla.firefox/x86_64/stable\t125\tflathub\n", b""
                ),
            )
        )
    )

    # When: the independent scopes parse external command output.
    result = collect_flatpak(runner)

    # Then: each malformed boundary is invalid without converting external text into exceptions.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.INVALID
    assert user.diagnostic == "Flatpak inventory output is not valid UTF-8"
    assert system.status is FlatpakScopeStatus.INVALID
    assert system.diagnostic == "Flatpak updates row 1 has an invalid ref"


def test_collect_flatpak_rejects_invalid_inventory_ref_and_non_utf8_updates() -> None:
    # Given: user inventory has too few ref segments and system updates are not UTF-8.
    runner = RecordingRunner(
        iter(
            (
                CommandSucceeded(
                    b"app/org.mozilla.firefox/x86_64\tapp\t124\tflathub\n", b""
                ),
                _succeeded("system-list.tsv"),
                CommandSucceeded(b"\xff", b""),
            )
        )
    )

    # When: collection parses the default user and system scopes.
    result = collect_flatpak(runner)

    # Then: both invalid boundaries are retained as per-scope diagnostics.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.INVALID
    assert user.diagnostic == "Flatpak inventory row 1 has an invalid ref"
    assert system.status is FlatpakScopeStatus.INVALID
    assert system.diagnostic == "Flatpak updates output is not valid UTF-8"


def test_collect_flatpak_keeps_candidate_ref_when_update_version_is_blank() -> None:
    # Given: a user update ref is present but its display version is empty.
    runner = RecordingRunner(
        iter(
            (
                _succeeded("user-list.tsv"),
                _succeeded("blank-version-updates.tsv"),
                CommandSucceeded(b"", b""),
            )
        )
    )

    # When: collection joins the candidate by exact full ref.
    result = collect_flatpak(runner)

    # Then: candidate evidence is preserved without inventing a display version.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.OK
    assert user.records[0].candidate_ref == "app/org.mozilla.firefox/x86_64/stable"
    assert user.records[0].item.candidate is None
    assert system.status is FlatpakScopeStatus.NOT_APPLICABLE


def test_collect_flatpak_rejects_malformed_update_columns_without_losing_inventory() -> (
    None
):
    # Given: valid inventory is followed by an update listing with a missing stable column.
    runner = RecordingRunner(
        iter(
            (
                _succeeded("user-list.tsv"),
                _succeeded("malformed-updates.tsv"),
                CommandSucceeded(b"", b""),
            )
        )
    )

    # When: collection joins the update candidates by full ref.
    result = collect_flatpak(runner)

    # Then: update parsing reports an invalid scope but preserves validated inventory records.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.INVALID
    assert len(user.records) == 2
    assert user.diagnostic == "Flatpak updates row 1 has 2 columns; expected 3"
    assert system.status is FlatpakScopeStatus.NOT_APPLICABLE


def test_flatpak_registry_is_read_only_and_uses_explicit_columns() -> None:
    # Given: the closed command registry.
    from opatchy_helper.runner_registry import COMMAND_SPECS

    # When: Flatpak specs are inspected.
    flatpak_specs = {
        name: spec.base_argv
        for name, spec in COMMAND_SPECS.items()
        if name.value.startswith("flatpak-")
    }

    # Then: all collection commands use stable columns and none invokes remediation.
    assert flatpak_specs == {
        CommandName.FLATPAK_USER_LIST: (
            "--user",
            "list",
            "--columns=ref,application,version,origin",
        ),
        CommandName.FLATPAK_SYSTEM_LIST: (
            "--system",
            "list",
            "--columns=ref,application,version,origin",
        ),
        CommandName.FLATPAK_USER_UPDATES: (
            "--user",
            "remote-ls",
            "--updates",
            "--columns=ref,version,origin",
        ),
        CommandName.FLATPAK_SYSTEM_UPDATES: (
            "--system",
            "remote-ls",
            "--updates",
            "--columns=ref,version,origin",
        ),
    }
    assert all("update" not in argv for argv in flatpak_specs.values())
    assert all("--installation" not in argv for argv in flatpak_specs.values())
