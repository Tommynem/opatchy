from __future__ import annotations

import os
import select
import signal
import subprocess
import time
from collections.abc import Mapping
from typing import IO

from .runner_types import (
    CommandExited,
    CommandMissing,
    CommandOutputExceeded,
    CommandRejected,
    CommandResult,
    CommandSpec,
    CommandSucceeded,
    CommandTimedOut,
    redact_diagnostic,
)


def run_spec(spec: CommandSpec, arguments: tuple[str, ...]) -> CommandResult:
    if arguments not in spec.allowed_arguments:
        return CommandRejected("arguments are not permitted for this command")
    environment: Mapping[str, str] = {"LC_ALL": "C", "PATH": "/usr/bin:/bin"}
    try:
        process = subprocess.Popen(  # noqa: S603 - immutable closed CommandSpec registry only
            (str(spec.executable), *spec.base_argv, *arguments),
            cwd=spec.cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except FileNotFoundError:
        return CommandMissing(redact_diagnostic(str(spec.executable)))
    except PermissionError as error:
        return CommandMissing(redact_diagnostic(str(error)))
    return _collect(process, spec)


def _collect(process: subprocess.Popen[bytes], spec: CommandSpec) -> CommandResult:
    if process.stdout is None or process.stderr is None:
        return CommandMissing("command output pipes are unavailable")
    stdout_pipe: IO[bytes] = process.stdout
    stderr_pipe: IO[bytes] = process.stderr
    pipes = {
        stdout_pipe.fileno(): (stdout_pipe, "stdout"),
        stderr_pipe.fileno(): (stderr_pipe, "stderr"),
    }
    for pipe, _ in pipes.values():
        os.set_blocking(pipe.fileno(), False)
    stdout = bytearray()
    stderr = bytearray()
    deadline = time.monotonic() + spec.timeout_seconds
    try:
        while pipes:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _stop_group(process)
                _drain(pipes, stdout, stderr, spec, time.monotonic() + 0.2)
                return CommandTimedOut(bytes(stdout), bytes(stderr))
            readable, _, _ = select.select(list(pipes), [], [], min(remaining, 0.05))
            for descriptor in readable:
                pipe, stream = pipes[descriptor]
                chunk = os.read(descriptor, 65536)
                if not chunk:
                    del pipes[descriptor]
                    continue
                target, limit = (
                    (stdout, spec.stdout_limit)
                    if stream == "stdout"
                    else (stderr, spec.stderr_limit)
                )
                available = limit - len(target)
                target.extend(chunk[: max(available, 0)])
                if len(chunk) > available:
                    _stop_group(process)
                    _drain(pipes, stdout, stderr, spec, time.monotonic() + 0.2)
                    return CommandOutputExceeded(stream, bytes(stdout), bytes(stderr))
        returncode = process.wait()
        if returncode == 0:
            return CommandSucceeded(bytes(stdout), bytes(stderr))
        return CommandExited(returncode, bytes(stdout), bytes(stderr))
    finally:
        stdout_pipe.close()
        stderr_pipe.close()


def _drain(
    pipes: dict[int, tuple[IO[bytes], str]],
    stdout: bytearray,
    stderr: bytearray,
    spec: CommandSpec,
    deadline: float,
) -> None:
    while pipes and time.monotonic() < deadline:
        readable, _, _ = select.select(
            list(pipes), [], [], min(deadline - time.monotonic(), 0.05)
        )
        for descriptor in readable:
            _, stream = pipes[descriptor]
            chunk = os.read(descriptor, 65536)
            if not chunk:
                del pipes[descriptor]
                continue
            target, limit = (
                (stdout, spec.stdout_limit)
                if stream == "stdout"
                else (stderr, spec.stderr_limit)
            )
            target.extend(chunk[: max(limit - len(target), 0)])


def _stop_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        _ = process.wait(timeout=0.2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        _ = process.wait()
