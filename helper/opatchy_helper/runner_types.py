from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import Path
from typing import Final


@unique
class CommandName(StrEnum):
    OMARCHY_UPDATE_AVAILABLE = "omarchy-update-available"
    PACMAN_NATIVE = "pacman-native"
    CHECKUPDATES = "checkupdates"
    VERCMP = "vercmp"
    PACMAN_FOREIGN = "pacman-foreign"
    YAY_UPDATES = "yay-updates"
    PARU_UPDATES = "paru-updates"
    FLATPAK_USER_LIST = "flatpak-user-list"
    FLATPAK_SYSTEM_LIST = "flatpak-system-list"
    FLATPAK_USER_UPDATES = "flatpak-user-updates"
    FLATPAK_SYSTEM_UPDATES = "flatpak-system-updates"
    MISE_OUTDATED = "mise-outdated"
    ARCH_AUDIT = "arch-audit"
    NOTIFY = "notify"


@unique
class EndpointName(StrEnum):
    ARCH_SECURITY = "arch-security"
    CISA_KEV = "cisa-kev"


@dataclass(frozen=True, slots=True)
class CommandSpec:
    executable: Path
    base_argv: tuple[str, ...]
    allowed_arguments: tuple[tuple[str, ...], ...]
    timeout_seconds: float
    stdout_limit: int
    stderr_limit: int
    cwd: Path | None = None

    def __post_init__(self) -> None:
        if not self.executable.is_absolute():
            raise ValueError("command executable must be absolute")
        if (
            self.timeout_seconds <= 0
            or self.stdout_limit <= 0
            or self.stderr_limit <= 0
        ):
            raise ValueError("command limits must be positive")


@dataclass(frozen=True, slots=True)
class EndpointSpec:
    url: str
    allowed_hosts: frozenset[str]
    allowed_path_prefixes: tuple[str, ...]
    redirect_limit: int
    body_limit: int
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class EndpointCache:
    body_path: Path
    metadata_path: Path


@dataclass(frozen=True, slots=True)
class CommandSucceeded:
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True, slots=True)
class CommandExited:
    returncode: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True, slots=True)
class CommandTimedOut:
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True, slots=True)
class CommandOutputExceeded:
    stream: str
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True, slots=True)
class CommandMissing:
    diagnostic: str


@dataclass(frozen=True, slots=True)
class CommandRejected:
    diagnostic: str


type CommandResult = (
    CommandSucceeded
    | CommandExited
    | CommandTimedOut
    | CommandOutputExceeded
    | CommandMissing
    | CommandRejected
)


@dataclass(frozen=True, slots=True)
class EndpointDownloaded:
    body: bytes
    etag: str | None
    last_modified: str | None


@dataclass(frozen=True, slots=True)
class EndpointNotModified:
    pass


@dataclass(frozen=True, slots=True)
class EndpointRejected:
    diagnostic: str


@dataclass(frozen=True, slots=True)
class EndpointTlsFailed:
    diagnostic: str


@dataclass(frozen=True, slots=True)
class EndpointTimedOut:
    diagnostic: str


@dataclass(frozen=True, slots=True)
class EndpointOversized:
    diagnostic: str


@dataclass(frozen=True, slots=True)
class EndpointFailed:
    diagnostic: str


type EndpointResult = (
    EndpointDownloaded
    | EndpointNotModified
    | EndpointRejected
    | EndpointTlsFailed
    | EndpointTimedOut
    | EndpointOversized
    | EndpointFailed
)


_HOME: Final[str] = str(Path.home())
_TOKEN: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?:bearer\s+|(?:token|api[_-]?key|password|secret)[=:]\s*)[^\s,;]+"
)


def redact_diagnostic(value: str) -> str:
    return _TOKEN.sub("<redacted>", value.replace(_HOME, "<home>"))[:512]
