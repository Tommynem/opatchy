import os
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import IO

import pytest

from tests.fixtures.factories import temporary_repository

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_validate_terminates_child_groups_and_removes_temporary_xdg_roots() -> None:
    with tempfile.TemporaryDirectory(prefix="opatchy-validation-test-") as directory:
        temporary_root = Path(directory)
        with temporary_repository(REPOSITORY_ROOT) as repository:
            fake_bin = repository.path("fake-bin")
            fake_bin.mkdir()
            fake_node = fake_bin / "node"
            _ = fake_node.write_text(
                "\n".join(
                    (
                        "#!/usr/bin/env bash",
                        "sleep 60 &",
                        "child=$!",
                        "printf 'READY %s\\n' \"${child}\"",
                        'wait "${child}"',
                        "",
                    )
                ),
                encoding="utf-8",
            )
            fake_node.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
            environment["TMPDIR"] = str(temporary_root)
            environment["UV_PROJECT_ENVIRONMENT"] = str(REPOSITORY_ROOT / ".venv")
            validation = subprocess.Popen(
                ["/usr/bin/bash", str(repository.path("scripts/validate.sh"))],
                cwd=repository.root,
                env=environment,
                stderr=subprocess.STDOUT,
                stdout=subprocess.PIPE,
                start_new_session=True,
            )

            stdout: IO[bytes] | None = validation.stdout
            assert stdout is not None
            ready_line = b""
            while not ready_line.startswith(b"READY "):
                ready_line = stdout.readline()
                assert ready_line != b""

            child_pid = int(ready_line.removeprefix(b"READY ").strip())
            os.killpg(validation.pid, signal.SIGTERM)
            assert validation.wait(timeout=10) != 0
            stdout.close()
            with pytest.raises(ProcessLookupError):
                os.kill(child_pid, 0)
            assert list(temporary_root.glob("opatchy-validate.*")) == []
