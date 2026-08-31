from __future__ import annotations

import hashlib
import io
import os
import signal
import ssl
import subprocess
import sys
import time
import urllib.error
from email.message import Message
from pathlib import Path
from types import MappingProxyType
from typing import final

import pytest

HELPER_ROOT = Path(__file__).resolve().parents[2] / "helper"
sys.path.insert(0, str(HELPER_ROOT))

from opatchy_helper import command_supervisor, runner


@final
class FakeResponse:
    status: int
    headers: dict[str, str]
    _body: io.BytesIO

    def __init__(self, status: int, headers: dict[str, str], body: bytes = b"") -> None:
        self.status = status
        self.headers = headers
        self._body = io.BytesIO(body)

    def read(self, amount: int = -1) -> bytes:
        return self._body.read(amount)

    def close(self) -> None:
        self._body.close()


def _metadata(body: bytes, etag: str, last_modified: str) -> bytes:
    return f"{etag}\n{last_modified}\n{hashlib.sha256(body).hexdigest()}\n".encode()


def _fake_command(tmp_path: Path, source: str) -> Path:
    executable = tmp_path / "fake-command"
    _ = executable.write_text(f"#!{sys.executable}\n{source}", encoding="utf-8")
    _ = executable.chmod(0o700)
    return executable


def _patch_command(
    monkeypatch: pytest.MonkeyPatch,
    executable: Path,
    *,
    timeout_seconds: float = 1.0,
    output_limit: int = 1024,
    argument_policy: runner.ArgumentPolicy = runner.ArgumentPolicy.NONE,
) -> None:
    spec = runner.CommandSpec(
        executable=executable,
        base_argv=(),
        argument_policy=argument_policy,
        timeout_seconds=timeout_seconds,
        stdout_limit=output_limit,
        stderr_limit=output_limit,
    )
    monkeypatch.setattr(
        runner,
        "COMMAND_SPECS",
        MappingProxyType({runner.CommandName.OMARCHY_UPDATE_AVAILABLE: spec}),
    )


def _wait_for_file(path: Path, timeout_seconds: float = 2) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert path.exists()


def test_outer_helper_death_kills_controlled_runner_descendants(tmp_path: Path) -> None:
    # Given: an outer helper whose controlled runner starts a target and descendant.
    child_pid = tmp_path / "child-pid"
    ready = tmp_path / "ready"
    sentinel = tmp_path / "descendant-survived"
    child_source = (
        "import pathlib, time; time.sleep(0.25); "
        f"pathlib.Path({str(sentinel)!r}).touch()"
    )
    target_directory = tmp_path / "target"
    outer_directory = tmp_path / "outer"
    target_directory.mkdir()
    outer_directory.mkdir()
    target = _fake_command(
        target_directory,
        "\n".join(
            (
                "import pathlib, subprocess, sys, time",
                f"child = subprocess.Popen([sys.executable, '-c', {child_source!r}])",
                f"pathlib.Path({str(child_pid)!r}).write_text(str(child.pid))",
                f"pathlib.Path({str(ready)!r}).touch()",
                "time.sleep(0.5)",
            )
        ),
    )
    outer = _fake_command(
        outer_directory,
        "\n".join(
            (
                "import sys",
                "from pathlib import Path",
                f"sys.path.insert(0, {str(HELPER_ROOT)!r})",
                "from opatchy_helper.runner_process import run_spec",
                "from opatchy_helper.runner_types import ArgumentPolicy, CommandSpec",
                f"run_spec(CommandSpec(Path({str(target)!r}), (), ArgumentPolicy.NONE, 30, 1024, 1024), ())",
            )
        ),
    )
    process = subprocess.Popen([str(outer)])
    _wait_for_file(ready)

    # When: the outer helper is killed without any QML-side cleanup.
    os.kill(process.pid, signal.SIGKILL)
    assert process.wait(timeout=2) == -signal.SIGKILL

    # Then: the target group prevents the delayed child side effect without test cleanup.
    _wait_for_file(child_pid)
    time.sleep(0.6)
    assert not sentinel.exists()
    with pytest.raises(ProcessLookupError):
        os.kill(int(child_pid.read_text(encoding="utf-8")), 0)


def test_runner_has_one_supervisor_command_launch_seam() -> None:
    # Given: the two production modules that participate in external command launch.
    process_source = (HELPER_ROOT / "opatchy_helper/runner_process.py").read_text(
        encoding="utf-8"
    )
    supervisor_source = (
        HELPER_ROOT / "opatchy_helper/command_supervisor.py"
    ).read_text(encoding="utf-8")

    # When: the production launch seams are inspected statically.
    process_launches = process_source.count("subprocess.Popen(")
    target_launches = supervisor_source.count("subprocess.Popen(")

    # Then: only the runner launches a supervisor and only it launches fixed targets.
    assert process_launches == 1
    assert "str(_SUPERVISOR_PATH)" in process_source
    assert target_launches == 1


def test_command_supervisor_forwards_fixed_target_exit_status(tmp_path: Path) -> None:
    # Given: a controlled target and the current test process as its expected parent.
    executable = _fake_command(tmp_path, "raise SystemExit(7)")

    # When: the supervisor arms parent-death handling and waits for the target.
    result = command_supervisor.main((str(os.getppid()), str(executable)))

    # Then: the target's ordinary exit status reaches the runner unchanged.
    assert result == 7


def test_command_supervisor_rejects_invalid_or_missing_targets(tmp_path: Path) -> None:
    # Given: malformed supervisor arguments and an absent fixed executable.
    missing = tmp_path / "missing"

    # When: each invalid launch shape reaches the supervisor boundary.
    malformed = command_supervisor.main(())
    absent = command_supervisor.main((str(os.getppid()), str(missing)))

    # Then: neither shape can start an uncontrolled target.
    assert malformed == command_supervisor.LAUNCH_FAILURE
    assert absent == command_supervisor.LAUNCH_FAILURE


def test_command_supervisor_fails_closed_when_parent_death_setup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a prctl boundary that cannot arm parent-death notification.
    def fail_setup() -> None:
        raise command_supervisor.SupervisorSetupError(1)

    monkeypatch.setattr(command_supervisor, "_set_parent_death_signal", fail_setup)

    # When: a trusted launch reaches the setup boundary.
    result = command_supervisor.main((str(os.getppid()), "/usr/bin/true"))
    _ = signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGUSR1})

    # Then: the supervisor returns before spawning the target.
    assert result == command_supervisor.LAUNCH_FAILURE


def test_run_command_rejects_hostile_argv_without_creating_sentinel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a command whose closed argument grammar allows no caller arguments.
    sentinel = Path("/tmp/opatchy-injection-sentinel")
    sentinel.unlink(missing_ok=True)
    executable = _fake_command(tmp_path, "print('must not run')")
    _patch_command(monkeypatch, executable)

    # When: an injection-shaped argument is supplied.
    result = runner.run_command(
        runner.CommandName.OMARCHY_UPDATE_AVAILABLE,
        ("$(touch /tmp/opatchy-injection-sentinel)",),
    )

    # Then: it is rejected before execution and the shell payload never runs.
    assert isinstance(result, runner.CommandRejected)
    assert not sentinel.exists()


def test_run_command_kills_descendants_after_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a process that starts a delayed descendant before hanging.
    sentinel = tmp_path / "descendant-survived"
    source = (
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', \"import pathlib, time; time.sleep(0.4); pathlib.Path({str(sentinel)!r}).touch()\"])\n"
        "time.sleep(30)\n"
    )
    executable = _fake_command(tmp_path, source)
    _patch_command(monkeypatch, executable, timeout_seconds=0.1)

    # When: the parent exceeds its bounded runtime.
    result = runner.run_command(runner.CommandName.OMARCHY_UPDATE_AVAILABLE)

    # Then: the whole process group is stopped, including the descendant.
    assert isinstance(result, runner.CommandTimedOut)
    time.sleep(0.6)
    assert not sentinel.exists()


def test_run_command_stops_when_stdout_or_stderr_exceeds_its_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a command that floods both output streams.
    executable = _fake_command(
        tmp_path,
        "\n".join(
            (
                "import sys, time",
                "sys.stdout.write('x' * 4096); sys.stdout.flush()",
                "sys.stderr.write('y' * 4096); sys.stderr.flush()",
                "time.sleep(30)",
            )
        ),
    )
    _patch_command(monkeypatch, executable, output_limit=64)

    # When: the bounded runner reads both streams.
    result = runner.run_command(runner.CommandName.OMARCHY_UPDATE_AVAILABLE)

    # Then: it kills the process and reports the typed overflow outcome.
    assert isinstance(result, runner.CommandOutputExceeded)
    assert len(result.stdout) <= 64
    assert len(result.stderr) <= 64


def test_fetch_endpoint_rejects_redirect_to_off_allowlist_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a named endpoint whose first response points off its fixed allowlist.
    def fake_open(
        request: runner.HttpsRequest, timeout: float, context: ssl.SSLContext
    ) -> FakeResponse:
        del request, timeout, context
        return FakeResponse(302, {"Location": "https://evil.invalid/all.json"})

    monkeypatch.setattr(runner, "_open_https", fake_open)

    # When: the named endpoint is fetched through the runner.
    result = runner.fetch_endpoint(
        runner.EndpointName.ARCH_SECURITY,
        runner.EndpointCache(tmp_path / "body", tmp_path / "metadata"),
    )

    # Then: the redirect is rejected before any off-allowlist request.
    assert isinstance(result, runner.EndpointRejected)


def test_fetch_endpoint_reports_tls_verification_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: the stdlib HTTPS transport rejects the peer certificate.
    def fake_open(
        request: runner.HttpsRequest, timeout: float, context: ssl.SSLContext
    ) -> FakeResponse:
        del request, timeout, context
        raise urllib.error.URLError(ssl.SSLCertVerificationError("bad peer"))

    monkeypatch.setattr(runner, "_open_https", fake_open)

    # When: the named endpoint is fetched.
    result = runner.fetch_endpoint(
        runner.EndpointName.ARCH_SECURITY,
        runner.EndpointCache(tmp_path / "body", tmp_path / "metadata"),
    )

    # Then: TLS failure is typed and no body cache is created.
    assert isinstance(result, runner.EndpointTlsFailed)
    assert not (tmp_path / "body").exists()


def test_run_command_returns_typed_exit_and_missing_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: one executable that exits nonzero and one absolute path that is absent.
    executable = _fake_command(tmp_path, "raise SystemExit(7)")
    _patch_command(monkeypatch, executable)

    # When: each closed command spec is invoked.
    exited = runner.run_command(runner.CommandName.OMARCHY_UPDATE_AVAILABLE)
    _patch_command(monkeypatch, tmp_path / "missing")
    missing = runner.run_command(runner.CommandName.OMARCHY_UPDATE_AVAILABLE)

    # Then: callers receive typed outcomes rather than subprocess exceptions.
    assert isinstance(exited, runner.CommandExited)
    assert exited.returncode == 7
    assert isinstance(missing, runner.CommandMissing)


def test_fetch_endpoint_uses_validators_and_replaces_cache_after_complete_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a previously cached validator and an HTTPS response with a complete replacement body.
    cache = runner.EndpointCache(tmp_path / "body", tmp_path / "metadata")
    _ = cache.body_path.write_bytes(b"old")
    _ = cache.metadata_path.write_bytes(
        _metadata(b"old", '"prior"', "Tue, 01 Jan 2030 00:00:00 GMT")
    )
    seen_headers: dict[str, str | None] = {}

    def fake_open(
        request: runner.HttpsRequest, timeout: float, context: ssl.SSLContext
    ) -> FakeResponse:
        del timeout, context
        seen_headers["etag"] = request.get_header("If-none-match")
        seen_headers["modified"] = request.get_header("If-modified-since")
        return FakeResponse(
            200,
            {"ETag": '"next"', "Last-Modified": "Wed, 02 Jan 2030 00:00:00 GMT"},
            b"new",
        )

    monkeypatch.setattr(runner, "_open_https", fake_open)

    # When: the fixed endpoint returns a valid full body.
    result = runner.fetch_endpoint(runner.EndpointName.ARCH_SECURITY, cache)

    # Then: conditional headers were sent and both cache files contain only the complete response.
    assert isinstance(result, runner.EndpointDownloaded)
    assert seen_headers == {
        "etag": '"prior"',
        "modified": "Tue, 01 Jan 2030 00:00:00 GMT",
    }
    assert cache.body_path.read_bytes() == b"new"
    assert cache.metadata_path.read_text(encoding="utf-8").splitlines() == [
        '"next"',
        "Wed, 02 Jan 2030 00:00:00 GMT",
        hashlib.sha256(b"new").hexdigest(),
    ]


@pytest.mark.parametrize(
    ("metadata", "conditional"),
    (
        (None, False),
        (b'"tag"\nTue, 01 Jan 2030 00:00:00 GMT\n', False),
        (b'"tag"\nTue, 01 Jan 2030 00:00:00 GMT\nnot-a-digest\n', False),
        (
            f"\n\n{hashlib.sha256(b'cached').hexdigest()}\n".encode(),
            False,
        ),
        (
            _metadata(b"different", '"tag"', "Tue, 01 Jan 2030 00:00:00 GMT"),
            False,
        ),
        (_metadata(b"cached", '"tag"', "Tue, 01 Jan 2030 00:00:00 GMT"), True),
    ),
)
def test_fetch_endpoint_accepts_304_only_after_digest_bound_conditional_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    metadata: bytes | None,
    conditional: bool,
) -> None:
    # Given: cached bytes with metadata of a known conditional-validity state.
    cache = runner.EndpointCache(tmp_path / "body", tmp_path / "metadata")
    _ = cache.body_path.write_bytes(b"cached")
    if metadata is not None:
        _ = cache.metadata_path.write_bytes(metadata)
    seen_headers: dict[str, str | None] = {}

    def fake_open(
        request: runner.HttpsRequest, timeout: float, context: ssl.SSLContext
    ) -> FakeResponse:
        del timeout, context
        seen_headers["etag"] = request.get_header("If-none-match")
        seen_headers["modified"] = request.get_header("If-modified-since")
        return FakeResponse(304, {})

    monkeypatch.setattr(runner, "_open_https", fake_open)

    # When: the endpoint returns status 304.
    result = runner.fetch_endpoint(runner.EndpointName.ARCH_SECURITY, cache)

    # Then: only a digest-bound conditional request can become not-modified.
    assert isinstance(result, runner.EndpointNotModified) is conditional
    assert seen_headers["etag"] == ('"tag"' if conditional else None)
    assert seen_headers["modified"] == (
        "Tue, 01 Jan 2030 00:00:00 GMT" if conditional else None
    )


@pytest.mark.parametrize(
    "metadata",
    (
        None,
        _metadata(b"cached", '"tag"', "Tue, 01 Jan 2030 00:00:00 GMT"),
    ),
)
def test_http_error_304_uses_the_same_conditional_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, metadata: bytes | None
) -> None:
    # Given: a response path that represents 304 as urllib HTTPError.
    cache = runner.EndpointCache(tmp_path / "body", tmp_path / "metadata")
    _ = cache.body_path.write_bytes(b"cached")
    if metadata is not None:
        _ = cache.metadata_path.write_bytes(metadata)

    def fake_open(
        request: runner.HttpsRequest, timeout: float, context: ssl.SSLContext
    ) -> FakeResponse:
        del timeout, context
        raise urllib.error.HTTPError(
            request.full_url, 304, "not modified", Message(), None
        )

    monkeypatch.setattr(runner, "_open_https", fake_open)

    # When: urllib signals 304 through its error path.
    result = runner.fetch_endpoint(runner.EndpointName.ARCH_SECURITY, cache)

    # Then: its classification matches the response-status path.
    assert isinstance(result, runner.EndpointNotModified) is (metadata is not None)


def test_fetch_endpoint_preserves_cache_when_response_is_oversized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: an existing cached body and a response exceeding the fixed endpoint ceiling.
    cache = runner.EndpointCache(tmp_path / "body", tmp_path / "metadata")
    _ = cache.body_path.write_bytes(b"old")
    spec = runner.EndpointSpec(
        url="https://security.archlinux.org/all.json",
        allowed_hosts=frozenset({"security.archlinux.org"}),
        allowed_paths=frozenset({"/all.json"}),
        redirect_limit=1,
        body_limit=2,
        timeout_seconds=1,
    )
    monkeypatch.setattr(
        runner,
        "ENDPOINT_SPECS",
        MappingProxyType({runner.EndpointName.ARCH_SECURITY: spec}),
    )

    def fake_open(
        request: runner.HttpsRequest, timeout: float, context: ssl.SSLContext
    ) -> FakeResponse:
        del request, timeout, context
        return FakeResponse(200, {}, b"too-large")

    monkeypatch.setattr(runner, "_open_https", fake_open)

    # When: the response crosses the body limit.
    result = runner.fetch_endpoint(runner.EndpointName.ARCH_SECURITY, cache)

    # Then: the typed oversize result leaves the previous cache intact.
    assert isinstance(result, runner.EndpointOversized)
    assert cache.body_path.read_bytes() == b"old"


def test_fetch_endpoint_follows_allowlisted_http_error_redirect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: urllib reports a same-host HTTPS redirect as an HTTPError before a valid body response.
    calls = 0

    def fake_open(
        request: runner.HttpsRequest, timeout: float, context: ssl.SSLContext
    ) -> FakeResponse:
        nonlocal calls
        del timeout, context
        calls += 1
        if calls == 1:
            headers = Message()
            headers["Location"] = "/all.json"
            raise urllib.error.HTTPError(
                request.full_url, 302, "redirect", headers, io.BytesIO()
            )
        return FakeResponse(200, {}, b"body")

    monkeypatch.setattr(runner, "_open_https", fake_open)

    # When: the named endpoint receives that redirect.
    result = runner.fetch_endpoint(
        runner.EndpointName.ARCH_SECURITY,
        runner.EndpointCache(tmp_path / "body", tmp_path / "metadata"),
    )

    # Then: it performs one validated follow-up request and returns the body.
    assert isinstance(result, runner.EndpointDownloaded)
    assert calls == 2


def test_run_command_timeout_does_not_wait_for_escaped_descendant_pipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a child that escapes the process group but retains inherited output pipes.
    executable = _fake_command(
        tmp_path,
        "\n".join(
            (
                "import os, subprocess, sys, time",
                "subprocess.Popen([sys.executable, '-c', 'import os, time; os.setsid(); time.sleep(2)'])",
                "time.sleep(30)",
            )
        ),
    )
    _patch_command(monkeypatch, executable, timeout_seconds=0.1)

    # When: the parent process times out.
    started = time.monotonic()
    result = runner.run_command(runner.CommandName.OMARCHY_UPDATE_AVAILABLE)

    # Then: retained child pipes cannot extend the bounded result wait.
    assert isinstance(result, runner.CommandTimedOut)
    assert time.monotonic() - started < 0.5


def test_fetch_endpoint_redacts_password_in_rejected_redirect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a hostile redirect containing a password-shaped query credential.
    def fake_open(
        request: runner.HttpsRequest, timeout: float, context: ssl.SSLContext
    ) -> FakeResponse:
        del request, timeout, context
        return FakeResponse(302, {"Location": "https://evil.invalid/?password=shh"})

    monkeypatch.setattr(runner, "_open_https", fake_open)

    # When: the named endpoint rejects that redirect.
    result = runner.fetch_endpoint(
        runner.EndpointName.ARCH_SECURITY,
        runner.EndpointCache(tmp_path / "body", tmp_path / "metadata"),
    )

    # Then: the typed diagnostic keeps no credential value.
    assert isinstance(result, runner.EndpointRejected)
    assert "shh" not in result.diagnostic


def test_run_command_preserves_host_context_and_forces_locale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: host HOME/XDG values and a fake executable that prints its inherited boundary.
    monkeypatch.setenv("HOME", "/tmp/opatchy-home")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/tmp/opatchy-xdg")
    executable = _fake_command(
        tmp_path,
        "import os; print('|'.join(os.environ[key] for key in ('HOME', 'XDG_RUNTIME_DIR', 'LC_ALL', 'LANG')))",
    )
    _patch_command(monkeypatch, executable)

    # When: a closed no-argument command runs.
    result = runner.run_command(runner.CommandName.OMARCHY_UPDATE_AVAILABLE)

    # Then: host integration survives while locale is deterministic.
    assert isinstance(result, runner.CommandSucceeded)
    assert result.stdout == b"/tmp/opatchy-home|/tmp/opatchy-xdg|C|C\n"


def test_dynamic_argument_policies_pass_hostile_literals_and_reject_invalid_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: fake vercmp and notify executables with their immutable dynamic policies.
    executable = _fake_command(tmp_path, "import sys; print(repr(sys.argv[1:]))")
    version = runner.CommandSpec(
        executable, (), runner.ArgumentPolicy.VERSION_PAIR, 1, 1024, 1024
    )
    notify = runner.CommandSpec(
        executable,
        ("-a", "io.github.tommynem.opatchy", "-u", "normal"),
        runner.ArgumentPolicy.NOTIFICATION_TEXT,
        1,
        1024,
        1024,
    )
    monkeypatch.setattr(
        runner,
        "COMMAND_SPECS",
        MappingProxyType(
            {runner.CommandName.VERCMP: version, runner.CommandName.NOTIFY: notify}
        ),
    )
    sentinel = Path("/tmp/opatchy-injection-sentinel")
    sentinel.unlink(missing_ok=True)

    # When: shell-shaped strings are supplied as the required literal pairs.
    compared = runner.run_command(
        runner.CommandName.VERCMP, ("$(touch /tmp/opatchy-injection-sentinel)", "2")
    )
    notified = runner.run_command(
        runner.CommandName.NOTIFY,
        ("headline; $(touch /tmp/opatchy-injection-sentinel)", "body"),
    )

    # Then: literal argv succeeds, while NUL, oversize, and wrong arity are rejected.
    assert isinstance(compared, runner.CommandSucceeded)
    assert isinstance(notified, runner.CommandSucceeded)
    assert not sentinel.exists()
    assert isinstance(
        runner.run_command(runner.CommandName.VERCMP, ("one",)), runner.CommandRejected
    )
    assert isinstance(
        runner.run_command(runner.CommandName.NOTIFY, ("a\0b", "body")),
        runner.CommandRejected,
    )
    assert isinstance(
        runner.run_command(runner.CommandName.VERCMP, ("x" * 4097, "two")),
        runner.CommandRejected,
    )


def test_endpoint_path_metadata_and_atomic_failure_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a lookalike endpoint path, malformed validators, and an existing cached body.
    cache = runner.EndpointCache(tmp_path / "body", tmp_path / "metadata")
    _ = cache.body_path.write_bytes(b"old")
    _ = cache.metadata_path.write_text("broken", encoding="utf-8")
    seen: dict[str, str | None] = {}

    def fake_open(
        request: runner.HttpsRequest, timeout: float, context: ssl.SSLContext
    ) -> FakeResponse:
        del timeout, context
        seen["etag"] = request.get_header("If-none-match")
        return FakeResponse(200, {}, b"new")

    def fail_replace(source: Path, target: Path) -> None:
        del source, target
        raise OSError("replace failed")

    monkeypatch.setattr(runner, "_open_https", fake_open)
    monkeypatch.setattr(os, "replace", fail_replace)

    # When: the named endpoint downloads through a failing atomic replacement.
    result = runner.fetch_endpoint(runner.EndpointName.ARCH_SECURITY, cache)

    # Then: no validators are sent, the old body survives, and no temporary body remains.
    assert isinstance(result, runner.EndpointFailed)
    assert seen["etag"] is None
    assert cache.body_path.read_bytes() == b"old"
    assert not list(tmp_path.glob("tmp*"))


def test_fetch_endpoint_rejects_exact_path_lookalike(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a named endpoint response redirects to a same-host path lookalike.
    def fake_open(
        request: runner.HttpsRequest, timeout: float, context: ssl.SSLContext
    ) -> FakeResponse:
        del request, timeout, context
        return FakeResponse(302, {"Location": "/all.json.evil"})

    monkeypatch.setattr(runner, "_open_https", fake_open)

    # When: the named endpoint follows its manually validated redirect loop.
    result = runner.fetch_endpoint(
        runner.EndpointName.ARCH_SECURITY,
        runner.EndpointCache(tmp_path / "body", tmp_path / "metadata"),
    )

    # Then: the lookalike fails the exact path policy.
    assert isinstance(result, runner.EndpointRejected)


def test_notify_registry_uses_fixed_opatchy_identity() -> None:
    # Given: the immutable notification command specification.
    spec = runner.COMMAND_SPECS[runner.CommandName.NOTIFY]

    # When: its fixed base argv is inspected.
    base_argv = spec.base_argv

    # Then: Opatchy identity and normal urgency precede literal caller text.
    assert base_argv == ("-a", "Opatchy", "-u", "normal")


def test_timeout_kills_term_ignoring_same_group_descendant_after_leader_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: an exited leader and a same-group child that ignores SIGTERM and retains pipes.
    sentinel = tmp_path / "term-ignored"
    executable = _fake_command(
        tmp_path,
        f"import subprocess, sys; subprocess.Popen([sys.executable, '-c', \"import pathlib, signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(0.4); pathlib.Path({str(sentinel)!r}).touch()\"])",
    )
    _patch_command(monkeypatch, executable, timeout_seconds=0.1)

    # When: timeout cleanup signals the original process group.
    result = runner.run_command(runner.CommandName.OMARCHY_UPDATE_AVAILABLE)

    # Then: SIGKILL removes the ignoring child before its delayed side effect.
    assert isinstance(result, runner.CommandTimedOut)
    time.sleep(0.6)
    assert not sentinel.exists()


def test_closed_pipe_sleeper_respects_command_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a child that closes both inherited output pipes before it hangs.
    executable = _fake_command(
        tmp_path,
        "import os, time; os.close(1); os.close(2); time.sleep(0.7)",
    )
    _patch_command(monkeypatch, executable, timeout_seconds=0.1)

    # When: the runner observes pipe EOF while the process still runs.
    started = time.monotonic()
    result = runner.run_command(runner.CommandName.OMARCHY_UPDATE_AVAILABLE)

    # Then: it applies timeout cleanup rather than waiting for the sleeper.
    assert isinstance(result, runner.CommandTimedOut)
    assert time.monotonic() - started < 0.5


def test_timeout_kills_same_group_descendant_after_leader_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a leader exits after spawning a same-group child that retains its output pipe.
    sentinel = tmp_path / "survived"
    executable = _fake_command(
        tmp_path,
        f"import subprocess, sys; subprocess.Popen([sys.executable, '-c', \"import pathlib, time; time.sleep(0.4); pathlib.Path({str(sentinel)!r}).touch()\"])",
    )
    _patch_command(monkeypatch, executable, timeout_seconds=0.1)

    # When: pipe retention reaches the runner timeout after the leader already exited.
    result = runner.run_command(runner.CommandName.OMARCHY_UPDATE_AVAILABLE)

    # Then: process-group cleanup kills the descendant before it can touch the sentinel.
    assert isinstance(result, runner.CommandTimedOut)
    time.sleep(0.6)
    assert not sentinel.exists()
