from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Protocol, assert_never

from ..models import (
    ItemId,
    ItemSource,
    NormalizedItem,
    Provenance,
    SourceStatus,
    WatchMode,
)
from ..runner import (
    CommandExited,
    CommandMissing,
    CommandName,
    CommandOutputExceeded,
    CommandRejected,
    CommandResult,
    CommandSucceeded,
    CommandTimedOut,
    run_command,
)
from ..runner_types import redact_diagnostic

OMARCHY_DUPLICATE_FILTER: Final[frozenset[str]] = frozenset({"omarchy", "omarchy-dev"})
_UP_TO_DATE: Final[bytes] = b"Omarchy is up to date\n"
_DIAGNOSTIC_BYTES: Final[int] = 512
_PACKAGE_ROW: Final[re.Pattern[str]] = re.compile(
    r"^(?P<package>omarchy(?:-dev)?) (?P<installed>[!-~]+) (?P<candidate>[!-~]+)$"
)
_DEVELOPMENT_ROW: Final[re.Pattern[str]] = re.compile(
    r"^omarchy-dev-checkout (?P<behind>[1-9][0-9]*) new "
    + r"(?P<commit_word>commit|commits) on (?P<upstream>[!-~]+)$"
)


class CommandRunner(Protocol):
    def __call__(
        self, name: CommandName, arguments: tuple[str, ...] = ()
    ) -> CommandResult: ...


@dataclass(frozen=True, slots=True)
class OmarchyAvailability:
    status: SourceStatus
    items: tuple[NormalizedItem, ...]
    diagnostic: str | None


def collect_omarchy_availability(
    runner: CommandRunner = run_command,
) -> OmarchyAvailability:
    result = runner(CommandName.OMARCHY_UPDATE_AVAILABLE)
    match result:
        case CommandSucceeded(stdout=stdout, stderr=stderr):
            return _parse_available_rows(stdout, stderr)
        case CommandExited(returncode=1, stdout=stdout, stderr=b"") if (
            stdout == _UP_TO_DATE
        ):
            return OmarchyAvailability(SourceStatus.OK, (), None)
        case CommandExited(returncode=returncode, stdout=stdout, stderr=stderr):
            return _error("unexpected command exit " + str(returncode), stdout, stderr)
        case CommandMissing(diagnostic=diagnostic):
            return OmarchyAvailability(
                SourceStatus.MISSING_DEPENDENCY,
                (),
                _diagnostic("Omarchy command is unavailable", diagnostic.encode()),
            )
        case CommandTimedOut(stdout=stdout, stderr=stderr):
            return OmarchyAvailability(
                SourceStatus.TIMEOUT,
                (),
                _diagnostic("Omarchy command timed out", stdout, stderr),
            )
        case CommandOutputExceeded(stream=stream, stdout=stdout, stderr=stderr):
            return _error(
                "Omarchy command output exceeded " + stream + " limit", stdout, stderr
            )
        case CommandRejected(diagnostic=diagnostic):
            return OmarchyAvailability(
                SourceStatus.ERROR,
                (),
                _diagnostic("Omarchy command was rejected", diagnostic.encode()),
            )
    assert_never(result)


def _parse_available_rows(stdout: bytes, stderr: bytes) -> OmarchyAvailability:
    items: list[NormalizedItem] = []
    item_ids: set[ItemId] = set()
    for row in stdout.decode("utf-8", errors="replace").splitlines():
        item = _parse_row(row)
        if item is None:
            return _invalid("unrecognized Omarchy availability row", stdout, stderr)
        if item.item_id in item_ids:
            return _invalid("duplicate Omarchy availability row", stdout, stderr)
        item_ids.add(item.item_id)
        items.append(item)
    if not items:
        return _invalid("successful Omarchy command returned no rows", stdout, stderr)
    return OmarchyAvailability(SourceStatus.OK, tuple(items), None)


def _parse_row(row: str) -> NormalizedItem | None:
    package_match = _PACKAGE_ROW.fullmatch(row)
    if package_match is not None:
        package = package_match["package"]
        return NormalizedItem(
            ItemId("omarchy:" + package),
            ItemSource.OMARCHY,
            package,
            package_match["installed"],
            package_match["candidate"],
            WatchMode.OFF,
            True,
            Provenance.LIVE,
        )
    development_match = _DEVELOPMENT_ROW.fullmatch(row)
    if development_match is None:
        return None
    behind = int(development_match["behind"])
    commit_word = development_match["commit_word"]
    if (behind == 1) != (commit_word == "commit"):
        return None
    return NormalizedItem(
        ItemId("omarchy:dev-checkout"),
        ItemSource.OMARCHY,
        "Omarchy development checkout",
        None,
        f"{behind} new {commit_word} on {development_match['upstream']}",
        WatchMode.OFF,
        False,
        Provenance.LIVE,
    )


def _invalid(message: str, stdout: bytes, stderr: bytes) -> OmarchyAvailability:
    return OmarchyAvailability(
        SourceStatus.INVALID,
        (),
        _diagnostic(message, stdout, stderr),
    )


def _error(message: str, stdout: bytes, stderr: bytes) -> OmarchyAvailability:
    return OmarchyAvailability(
        SourceStatus.ERROR,
        (),
        _diagnostic(message, stdout, stderr),
    )


def _diagnostic(message: str, stdout: bytes = b"", stderr: bytes = b"") -> str:
    snippets = tuple(
        snippet for value in (stdout, stderr) if (snippet := _snippet(value))
    )
    return redact_diagnostic(" | ".join((message, *snippets)))


def _snippet(value: bytes) -> str:
    decoded = value[:_DIAGNOSTIC_BYTES].decode("utf-8", errors="replace")
    printable = "".join(
        character if character.isprintable() else " " for character in decoded
    )
    return " ".join(printable.split())
