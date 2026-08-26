import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HELPER_ROOT = REPOSITORY_ROOT / "helper"
SMOKE_FIXTURE = REPOSITORY_ROOT / "tests/qml/controlled-runner-smoke.qml"


def _write_controlled_target(path: Path, pid_log: Path, sentinel: Path) -> None:
    child_source = (
        "import os, pathlib, time; "
        f"open({str(pid_log)!r}, 'a', encoding='utf-8').write(f'{{os.getpid()}}\\n'); "
        f"time.sleep(0.5); pathlib.Path({str(sentinel)!r}).touch()"
    )
    _ = path.write_text(
        "\n".join(
            (
                f"#!{sys.executable}",
                "import os, subprocess, sys, time",
                f"open({str(pid_log)!r}, 'a', encoding='utf-8').write(f'{{os.getpid()}}\\n')",
                f"subprocess.Popen([sys.executable, '-c', {child_source!r}])",
                "time.sleep(30)",
                "",
            )
        ),
        encoding="utf-8",
    )
    path.chmod(0o700)


def _write_outer_helper(path: Path, target: Path) -> None:
    _ = path.write_text(
        "\n".join(
            (
                f"#!{sys.executable}",
                "from pathlib import Path",
                "import sys",
                f"sys.path.insert(0, {str(HELPER_ROOT)!r})",
                "from opatchy_helper.runner_process import run_spec",
                "from opatchy_helper.runner_types import ArgumentPolicy, CommandSpec",
                f"run_spec(CommandSpec(Path({str(target)!r}), (), ArgumentPolicy.NONE, 30, 1024, 1024), ())",
                "",
            )
        ),
        encoding="utf-8",
    )
    path.chmod(0o700)


def _wait_for_dead(pid: int) -> bool:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.01)
    return False


@pytest.mark.parametrize(
    ("mode", "interruptions"),
    (("stop", 1), ("timeout", 1), ("destroy", 1), ("destroy", 20)),
)
def test_quickshell_controlled_runner_cleans_every_known_group_member(
    tmp_path: Path, mode: str, interruptions: int
) -> None:
    # Given: the actual Quickshell transport and a helper using the controlled runner.
    pid_log = tmp_path / "pids"
    sentinel = tmp_path / "descendant-survived"
    target = tmp_path / "controlled-target"
    outer_helper = tmp_path / "controlled-helper"
    _write_controlled_target(target, pid_log, sentinel)
    _write_outer_helper(outer_helper, target)
    environment = os.environ | {
        "OPATCHY_CONTROLLED_HELPER": str(outer_helper),
        "OPATCHY_CONTROLLED_MODE": mode,
        "OPATCHY_INTERRUPTION_COUNT": str(interruptions),
        "OPATCHY_TEST_ROOT": str(REPOSITORY_ROOT),
    }

    # When: the real QML Process stops, times out, or directly destroys each helper.
    result = subprocess.run(
        ["/usr/bin/qs", "--path", str(SMOKE_FIXTURE)],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
        timeout=30,
    )

    # Then: every recorded target and same-group child is gone without test cleanup.
    assert result.returncode == 0, result.stdout + result.stderr
    pids = [int(value) for value in pid_log.read_text(encoding="utf-8").splitlines()]
    assert len(pids) == interruptions * 2
    assert all(_wait_for_dead(pid) for pid in pids)
    assert not sentinel.exists()
