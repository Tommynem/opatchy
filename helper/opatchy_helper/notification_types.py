from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Protocol

from .models import NotificationFingerprint, Severity
from .runner_types import CommandName, CommandResult


@unique
class NotificationKind(StrEnum):
    WATCH = "watch"
    SECURITY = "security"
    SECURITY_CONDITION = "security-condition"


@unique
class NotificationChange(StrEnum):
    FIRST = "first"
    NEW = "new"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class NotificationSettings:
    notify_permanent: bool = True
    notify_security: bool = True
    security_minimum_severity: Severity = Severity.HIGH


@dataclass(frozen=True, slots=True)
class NotificationCandidate:
    fingerprint: NotificationFingerprint
    reference: str
    kind: NotificationKind
    change: NotificationChange
    title: str
    body: str


class NotificationRunner(Protocol):
    def __call__(
        self, name: CommandName, arguments: tuple[str, ...], /
    ) -> CommandResult: ...
