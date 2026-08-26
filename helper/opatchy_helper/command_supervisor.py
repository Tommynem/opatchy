"""Linux-only parent-death cleanup for controlled runner process groups.

The guarantee covers target descendants that remain in the assigned PGID. A
target that deliberately calls setsid or otherwise leaves that group is outside
the controlled-runner boundary.
"""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from types import FrameType
from typing import Final, override

PR_SET_PDEATHSIG: Final = 1
PARENT_DEATH_SIGNAL: Final = signal.SIGUSR1
LAUNCH_FAILURE: Final = 127


@dataclass(frozen=True, slots=True)
class SupervisorSetupError(Exception):
    errno: int

    @override
    def __str__(self) -> str:
        return os.strerror(self.errno)


@dataclass(frozen=True, slots=True)
class SupervisorArgumentsError(Exception):
    @override
    def __str__(self) -> str:
        return "supervisor arguments are invalid"


def main(arguments: Sequence[str]) -> int:
    try:
        parent_pid, target_argv = _arguments(arguments)
    except SupervisorArgumentsError:
        return LAUNCH_FAILURE
    try:
        _arm_parent_death(parent_pid)
    except SupervisorSetupError:
        return LAUNCH_FAILURE
    return _run_target(target_argv)


def _arguments(arguments: Sequence[str]) -> tuple[int, tuple[str, ...]]:
    if len(arguments) < 2:
        raise SupervisorArgumentsError()
    try:
        parent_pid = int(arguments[0])
    except ValueError as error:
        raise SupervisorArgumentsError() from error
    if parent_pid <= 0 or not arguments[1]:
        raise SupervisorArgumentsError()
    return parent_pid, tuple(arguments[1:])


def _arm_parent_death(expected_parent_pid: int) -> None:
    _ = signal.pthread_sigmask(signal.SIG_BLOCK, {PARENT_DEATH_SIGNAL})
    _set_parent_death_signal()
    if os.getppid() != expected_parent_pid:
        _kill_own_group()
    _ = signal.signal(PARENT_DEATH_SIGNAL, _parent_died)
    _ = signal.pthread_sigmask(signal.SIG_UNBLOCK, {PARENT_DEATH_SIGNAL})


def _set_parent_death_signal() -> None:
    """Call Linux prctl at the sole ctypes boundary for parent-death delivery."""
    library = ctypes.CDLL(None, use_errno=True)
    prctl = library.prctl
    prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    prctl.restype = ctypes.c_int
    if prctl(PR_SET_PDEATHSIG, int(PARENT_DEATH_SIGNAL), 0, 0, 0) != 0:
        raise SupervisorSetupError(ctypes.get_errno())


def _parent_died(_: int, _frame: FrameType | None) -> None:
    _kill_own_group()


def _kill_own_group() -> None:
    os.killpg(os.getpgrp(), signal.SIGKILL)


def _run_target(argv: tuple[str, ...]) -> int:
    try:
        target = subprocess.Popen(argv)  # noqa: S603 - runner supplies fixed argv
    except FileNotFoundError, PermissionError, OSError:
        return LAUNCH_FAILURE
    returncode = target.wait()
    if returncode >= 0:
        return returncode
    target_signal = signal.Signals(-returncode)
    _ = signal.signal(target_signal, signal.SIG_DFL)
    os.kill(os.getpid(), target_signal)
    return LAUNCH_FAILURE


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
