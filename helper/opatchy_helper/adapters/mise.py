"""Read-only mise global/home update collection for v0.1.

The adapter invokes only the closed MISE_OUTDATED runner command, whose registry
fixes cwd to HOME. It never walks projects; remediation remains full omarchy update.
"""

from dataclasses import dataclass
from typing import Protocol, assert_never

from ..json_value import JsonValue, decode_json
from ..models import (
    ItemId,
    ItemSource,
    NormalizedItem,
    ProtocolError,
    Provenance,
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
)

_RECORD_FIELDS = frozenset({"requested", "current", "latest"})


class CommandRunner(Protocol):
    """Runs only command names allowed by the shared closed registry."""

    def __call__(
        self, name: CommandName, arguments: tuple[str, ...], /
    ) -> CommandResult: ...


@dataclass(frozen=True, slots=True)
class MiseRecord:
    """One opaque mise update record plus its normalized display item."""

    item: NormalizedItem
    requested: str
    current: str
    latest: str


@dataclass(frozen=True, slots=True)
class MiseCollected:
    """Fresh mise update evidence; records are non-empty."""

    records: tuple[MiseRecord, ...]


@dataclass(frozen=True, slots=True)
class MiseNotApplicable:
    """mise is absent or has no applicable global/home updates."""


@dataclass(frozen=True, slots=True)
class MiseInvalid:
    """mise output was not valid complete JSON evidence."""

    diagnostic: str


@dataclass(frozen=True, slots=True)
class MiseTimedOut:
    """The bounded mise command exceeded its deadline."""


@dataclass(frozen=True, slots=True)
class MiseOutputExceeded:
    """The bounded mise command exceeded one output limit."""

    stream: str


@dataclass(frozen=True, slots=True)
class MiseCommandFailed:
    """mise exited nonzero without producing trusted update evidence."""

    returncode: int


@dataclass(frozen=True, slots=True)
class MiseCommandRejected:
    """The runner refused the closed mise command request."""

    diagnostic: str


type MiseResult = (
    MiseCollected
    | MiseNotApplicable
    | MiseInvalid
    | MiseTimedOut
    | MiseOutputExceeded
    | MiseCommandFailed
    | MiseCommandRejected
)


def collect_mise_updates(run: CommandRunner) -> MiseResult:
    """Collect global/home mise updates without comparing or executing version data."""
    result = run(CommandName.MISE_OUTDATED, ())
    match result:
        case CommandSucceeded(stdout=stdout):
            return _parse_output(stdout)
        case CommandMissing():
            return MiseNotApplicable()
        case CommandTimedOut():
            return MiseTimedOut()
        case CommandOutputExceeded(stream=stream):
            return MiseOutputExceeded(stream)
        case CommandExited(returncode=returncode):
            return MiseCommandFailed(returncode)
        case CommandRejected(diagnostic=diagnostic):
            return MiseCommandRejected(diagnostic)
    assert_never(result)


def _parse_output(stdout: bytes) -> MiseResult:
    try:
        decoded = decode_json(stdout.decode("utf-8"))
    except UnicodeDecodeError:
        return MiseInvalid("mise output is not UTF-8")
    except ProtocolError as error:
        return MiseInvalid(str(error))
    if type(decoded) is not dict:
        return MiseInvalid("mise output must be an object")
    if not decoded:
        return MiseNotApplicable()
    records: list[MiseRecord] = []
    for key, value in decoded.items():
        record = _parse_record(key, value)
        if isinstance(record, MiseInvalid):
            return record
        records.append(record)
    return MiseCollected(tuple(records))


def _parse_record(key: str, value: JsonValue) -> MiseRecord | MiseInvalid:
    if type(value) is not dict:
        return MiseInvalid(f"mise.{key} must be an object")
    if frozenset(value) != _RECORD_FIELDS:
        return MiseInvalid(f"mise.{key} must contain requested, current, and latest")
    requested = value["requested"]
    current = value["current"]
    latest = value["latest"]
    if type(requested) is not str:
        return MiseInvalid(f"mise.{key}.requested must be a string")
    if type(current) is not str:
        return MiseInvalid(f"mise.{key}.current must be a string")
    if type(latest) is not str:
        return MiseInvalid(f"mise.{key}.latest must be a string")
    return MiseRecord(
        item=NormalizedItem(
            item_id=ItemId(f"mise:{key}"),
            source=ItemSource.MISE,
            label=key,
            installed=current,
            candidate=latest,
            watch_mode=WatchMode.OFF,
            watchable=True,
            provenance=Provenance.LIVE,
        ),
        requested=requested,
        current=current,
        latest=latest,
    )
