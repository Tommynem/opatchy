from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from scripts.publication_verifier_model import VerifierError


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, arguments: tuple[str, ...]) -> CommandResult: ...


def require_result(
    runner: CommandRunner, arguments: tuple[str, ...], operation: str
) -> CommandResult:
    result = runner.run(arguments)
    if result.returncode != 0:
        raise VerifierError(f"{operation} failed")
    return result
