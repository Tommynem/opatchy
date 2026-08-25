from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

HELPER_ROOT = Path(__file__).resolve().parents[3] / "helper"
sys.path.insert(0, str(HELPER_ROOT))

from opatchy_helper.adapters.flatpak import FlatpakScopeStatus, collect_flatpak
from opatchy_helper.runner_registry import COMMAND_SPECS
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
EMPTY = CommandSucceeded(b"", b"")


class RecordingRunner:
    def __init__(self, results: Mapping[CommandName, CommandResult]) -> None:
        self._results: Mapping[CommandName, CommandResult] = results
        self.calls: list[CommandName] = []

    def __call__(self, name: CommandName) -> CommandResult:
        self.calls.append(name)
        return self._results[name]


def _succeeded(name: str) -> CommandSucceeded:
    return CommandSucceeded((FIXTURES / name).read_bytes(), b"")


def _inputs(
    user_apps: CommandResult,
    user_runtimes: CommandResult,
    system_apps: CommandResult,
    system_runtimes: CommandResult,
    *,
    user_updates: CommandResult | None = None,
    system_updates: CommandResult | None = None,
) -> RecordingRunner:
    results: dict[CommandName, CommandResult] = {
        CommandName.FLATPAK_USER_APP_LIST: user_apps,
        CommandName.FLATPAK_USER_RUNTIME_LIST: user_runtimes,
        CommandName.FLATPAK_SYSTEM_APP_LIST: system_apps,
        CommandName.FLATPAK_SYSTEM_RUNTIME_LIST: system_runtimes,
    }
    if user_updates is not None:
        results[CommandName.FLATPAK_USER_UPDATES] = user_updates
    if system_updates is not None:
        results[CommandName.FLATPAK_SYSTEM_UPDATES] = system_updates
    return RecordingRunner(results)


def test_collect_flatpak_reconstructs_native_app_and_runtime_refs_per_scope() -> None:
    # Given: app/runtime five-column inventory and opaque update versions in both scopes.
    runner = _inputs(
        _succeeded("native-app-list.tsv"),
        _succeeded("native-runtime-list.tsv"),
        _succeeded("native-system-app-list.tsv"),
        _succeeded("native-system-runtime-list.tsv"),
        user_updates=_succeeded("native-app-updates.tsv"),
        system_updates=_succeeded("native-system-app-updates.tsv"),
    )

    # When: default user and system collections run independently.
    result = collect_flatpak(runner)

    # Then: kind evidence reconstructs unique scope-qualified full refs and native candidate evidence.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.OK
    assert system.status is FlatpakScopeStatus.OK
    assert [record.ref for record in user.records] == [
        "app/com.example.App/x86_64/stable",
        "runtime/org.example.Platform/x86_64/24.08",
    ]
    assert (
        user.records[0].item.item_id == "flatpak:user:app/com.example.App/x86_64/stable"
    )
    assert user.records[0].candidate_ref == "app/com.example.App/x86_64/stable"
    assert user.records[0].candidate_origin == "flathub"
    assert user.records[0].item.watchable is True
    assert user.records[1].item.candidate is None
    assert user.records[1].item.watchable is True
    assert (
        system.records[0].item.item_id
        == "flatpak:system:app/com.example.App/x86_64/stable"
    )
    assert system.records[0].item.candidate == "2026.08-rc1+build.7"
    assert runner.calls == [
        CommandName.FLATPAK_USER_APP_LIST,
        CommandName.FLATPAK_USER_RUNTIME_LIST,
        CommandName.FLATPAK_USER_UPDATES,
        CommandName.FLATPAK_SYSTEM_APP_LIST,
        CommandName.FLATPAK_SYSTEM_RUNTIME_LIST,
        CommandName.FLATPAK_SYSTEM_UPDATES,
    ]


def test_collect_flatpak_keeps_user_only_inventory() -> None:
    # Given: only the user installation has a native app row.
    runner = _inputs(
        _succeeded("native-app-list.tsv"), EMPTY, EMPTY, EMPTY, user_updates=EMPTY
    )

    # When: both default installations are queried.
    result = collect_flatpak(runner)

    # Then: only system is not-applicable and no system update query occurs.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.OK
    assert system.status is FlatpakScopeStatus.NOT_APPLICABLE
    assert CommandName.FLATPAK_SYSTEM_UPDATES not in runner.calls


def test_collect_flatpak_keeps_system_only_inventory() -> None:
    # Given: only the system installation has a native app row.
    runner = _inputs(
        EMPTY,
        EMPTY,
        _succeeded("native-system-app-list.tsv"),
        EMPTY,
        system_updates=EMPTY,
    )

    # When: both default installations are queried.
    result = collect_flatpak(runner)

    # Then: only user is not-applicable and system retains its scoped record.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.NOT_APPLICABLE
    assert system.status is FlatpakScopeStatus.OK
    assert system.records[0].ref == "app/com.example.App/x86_64/stable"


def test_collect_flatpak_marks_empty_scopes_not_applicable() -> None:
    # Given: neither default installation has apps or runtimes.
    runner = _inputs(EMPTY, EMPTY, EMPTY, EMPTY)

    # When: the collector evaluates both scopes.
    result = collect_flatpak(runner)

    # Then: both scopes are not-applicable and no update command runs.
    assert [scope.status for scope in result.scopes] == [
        FlatpakScopeStatus.NOT_APPLICABLE,
        FlatpakScopeStatus.NOT_APPLICABLE,
    ]
    assert not any("updates" in name.value for name in runner.calls)


def test_collect_flatpak_preserves_system_when_user_app_list_times_out() -> None:
    # Given: the user app inventory times out while system inventory is healthy.
    runner = _inputs(
        CommandTimedOut(b"", b""),
        EMPTY,
        _succeeded("native-system-app-list.tsv"),
        EMPTY,
        system_updates=EMPTY,
    )

    # When: the collector evaluates both scopes.
    result = collect_flatpak(runner)

    # Then: user is timed out while the system record remains fresh.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.TIMEOUT
    assert system.status is FlatpakScopeStatus.OK
    assert len(system.records) == 1


def test_collect_flatpak_keeps_valid_runtime_when_app_binary_is_missing() -> None:
    # Given: the user app command is unavailable while user runtime inventory succeeds.
    runner = _inputs(
        CommandMissing("flatpak unavailable"),
        _succeeded("native-runtime-list.tsv"),
        EMPTY,
        EMPTY,
    )

    # When: the collector evaluates the incomplete user inventory.
    result = collect_flatpak(runner)

    # Then: missing dependency is explicit and the validated runtime record is preserved.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.MISSING_DEPENDENCY
    assert user.records[0].ref == "runtime/org.example.Platform/x86_64/24.08"
    assert system.status is FlatpakScopeStatus.NOT_APPLICABLE


def test_collect_flatpak_reports_output_overflow_per_scope() -> None:
    # Given: the system app list exceeds its configured output cap.
    runner = _inputs(
        EMPTY,
        EMPTY,
        CommandOutputExceeded("stdout", b"", b""),
        EMPTY,
    )

    # When: both scopes are collected.
    result = collect_flatpak(runner)

    # Then: only system reports the bounded runner failure.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.NOT_APPLICABLE
    assert system.status is FlatpakScopeStatus.OUTPUT_EXCEEDED


def test_collect_flatpak_rejects_malformed_native_inventory() -> None:
    # Given: the user app command no longer returns its five requested columns.
    runner = _inputs(_succeeded("malformed-list.tsv"), EMPTY, EMPTY, EMPTY)

    # When: the collector parses the native output boundary.
    result = collect_flatpak(runner)

    # Then: only user becomes invalid with a shape diagnostic.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.INVALID
    assert user.diagnostic == "Flatpak inventory row 1 has 2 columns; expected 5"
    assert system.status is FlatpakScopeStatus.NOT_APPLICABLE


def test_collect_flatpak_rejects_non_utf8_inventory() -> None:
    # Given: the user app command emits bytes outside the explicit UTF-8 boundary.
    runner = _inputs(CommandSucceeded(b"\xff", b""), EMPTY, EMPTY, EMPTY)

    # When: the collector parses native app inventory.
    result = collect_flatpak(runner)

    # Then: only the affected user scope is invalid.
    user, system = result.scopes
    assert user.diagnostic == "Flatpak inventory output is not valid UTF-8"
    assert user.status is FlatpakScopeStatus.INVALID
    assert system.status is FlatpakScopeStatus.NOT_APPLICABLE


def test_collect_flatpak_rejects_invalid_native_inventory_component() -> None:
    # Given: the native app row has an empty architecture component.
    runner = _inputs(
        CommandSucceeded(b"com.example.App\t\tstable\t2.8.0\tflathub\n", b""),
        EMPTY,
        EMPTY,
        EMPTY,
    )

    # When: the collector reconstructs the full app ref.
    result = collect_flatpak(runner)

    # Then: malformed components cannot produce a normalized ID.
    user, _system = result.scopes
    assert user.status is FlatpakScopeStatus.INVALID
    assert user.diagnostic == "Flatpak inventory row 1 has an invalid component"


def test_collect_flatpak_rejects_duplicate_inventory_refs() -> None:
    # Given: one app inventory repeats the same native app row.
    runner = _inputs(_succeeded("duplicate-native-app-list.tsv"), EMPTY, EMPTY, EMPTY)

    # When: the parser reconstructs the app refs.
    result = collect_flatpak(runner)

    # Then: duplicate normalized IDs are rejected before records escape.
    user, _system = result.scopes
    assert user.status is FlatpakScopeStatus.INVALID
    assert user.diagnostic == "Flatpak inventory contains duplicate ref at row 2"


def test_collect_flatpak_rejects_duplicate_update_refs() -> None:
    # Given: a valid app inventory has repeated native update evidence.
    runner = _inputs(
        _succeeded("native-app-list.tsv"),
        EMPTY,
        EMPTY,
        EMPTY,
        user_updates=_succeeded("duplicate-updates.tsv"),
    )

    # When: candidate rows are parsed.
    result = collect_flatpak(runner)

    # Then: duplicate updates invalidate the scope without dictionary collapse.
    user, _system = result.scopes
    assert user.status is FlatpakScopeStatus.INVALID
    assert user.diagnostic == "Flatpak updates contains duplicate ref at row 2"
    assert len(user.records) == 1


def test_collect_flatpak_rejects_malformed_update_columns() -> None:
    # Given: a valid app inventory is followed by a truncated update row.
    runner = _inputs(
        _succeeded("native-app-list.tsv"),
        EMPTY,
        EMPTY,
        EMPTY,
        user_updates=_succeeded("malformed-updates.tsv"),
    )

    # When: the collector parses update evidence.
    result = collect_flatpak(runner)

    # Then: user becomes invalid while inventory remains available.
    user, _system = result.scopes
    assert user.status is FlatpakScopeStatus.INVALID
    assert user.diagnostic == "Flatpak updates row 1 has 2 columns; expected 3"
    assert len(user.records) == 1


def test_collect_flatpak_rejects_invalid_update_ref() -> None:
    # Given: an update row uses a kind not supported by Flatpak inventory reconstruction.
    runner = _inputs(
        _succeeded("native-app-list.tsv"),
        EMPTY,
        EMPTY,
        EMPTY,
        user_updates=CommandSucceeded(
            b"extension/com.example.App/x86_64/stable\t2.9.0\tflathub\n", b""
        ),
    )

    # When: the collector validates the native candidate ref.
    result = collect_flatpak(runner)

    # Then: invalid candidate grammar cannot be joined into inventory.
    user, _system = result.scopes
    assert user.status is FlatpakScopeStatus.INVALID
    assert user.diagnostic == "Flatpak updates row 1 has an invalid ref"


def test_collect_flatpak_rejects_update_ref_absent_from_inventory() -> None:
    # Given: native update evidence names a ref absent from the app/runtime inventory.
    runner = _inputs(
        _succeeded("native-app-list.tsv"),
        EMPTY,
        EMPTY,
        EMPTY,
        user_updates=_succeeded("unmatched-updates.tsv"),
    )

    # When: the collector reconciles candidate evidence.
    result = collect_flatpak(runner)

    # Then: user is invalid while its validated inventory record remains available.
    user, _system = result.scopes
    assert user.status is FlatpakScopeStatus.INVALID
    assert user.diagnostic == "Flatpak updates contains unmatched ref at row 1"
    assert len(user.records) == 1


def test_collect_flatpak_preserves_blank_and_opaque_candidate_versions() -> None:
    # Given: Flatpak reports blank and non-SemVer candidate display strings.
    blank = _inputs(
        _succeeded("native-app-list.tsv"),
        EMPTY,
        EMPTY,
        EMPTY,
        user_updates=_succeeded("native-app-blank-version-updates.tsv"),
    )
    opaque = _inputs(
        _succeeded("native-app-list.tsv"),
        EMPTY,
        EMPTY,
        EMPTY,
        user_updates=_succeeded("native-app-opaque-updates.tsv"),
    )

    # When: each update evidence stream is joined by exact full ref.
    blank_result = collect_flatpak(blank)
    opaque_result = collect_flatpak(opaque)

    # Then: display values remain opaque while candidate refs remain native evidence.
    assert blank_result.scopes[0].records[0].item.candidate is None
    assert (
        blank_result.scopes[0].records[0].candidate_ref
        == "app/com.example.App/x86_64/stable"
    )
    assert opaque_result.scopes[0].records[0].item.candidate == "2026.08-rc1+build.7"


def test_collect_flatpak_preserves_inventory_when_update_command_exits() -> None:
    # Given: a valid user inventory is followed by a nonzero read-only update query.
    runner = _inputs(
        _succeeded("native-app-list.tsv"),
        EMPTY,
        EMPTY,
        EMPTY,
        user_updates=CommandExited(23, b"", b"failure"),
    )

    # When: the collector requests update evidence.
    result = collect_flatpak(runner)

    # Then: failure is explicit but validated inventory survives.
    user, _system = result.scopes
    assert user.status is FlatpakScopeStatus.ERROR
    assert len(user.records) == 1
    assert user.diagnostic == "Flatpak command exited with status 23"


def test_collect_flatpak_bounds_rejected_command_diagnostics() -> None:
    # Given: the user app command is rejected with an oversized diagnostic.
    runner = _inputs(CommandRejected("x" * 600), EMPTY, EMPTY, EMPTY)

    # When: both scopes are collected.
    result = collect_flatpak(runner)

    # Then: the diagnostic remains bounded and system is independent.
    user, system = result.scopes
    assert user.status is FlatpakScopeStatus.ERROR
    assert user.diagnostic == "x" * 512
    assert system.status is FlatpakScopeStatus.NOT_APPLICABLE


def test_flatpak_registry_uses_only_read_only_explicit_columns() -> None:
    # Given: the closed Flatpak command registry.
    flatpak_specs = {
        name: spec.base_argv
        for name, spec in COMMAND_SPECS.items()
        if name.value.startswith("flatpak-")
    }

    # When: the fixed argv tuples are inspected.
    inventory_columns = "--columns=application,arch,branch,version,origin"

    # Then: inventories provide kind evidence and no remediation or named installation is available.
    assert flatpak_specs == {
        CommandName.FLATPAK_USER_APP_LIST: (
            "--user",
            "list",
            "--app",
            inventory_columns,
        ),
        CommandName.FLATPAK_USER_RUNTIME_LIST: (
            "--user",
            "list",
            "--runtime",
            inventory_columns,
        ),
        CommandName.FLATPAK_SYSTEM_APP_LIST: (
            "--system",
            "list",
            "--app",
            inventory_columns,
        ),
        CommandName.FLATPAK_SYSTEM_RUNTIME_LIST: (
            "--system",
            "list",
            "--runtime",
            inventory_columns,
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
