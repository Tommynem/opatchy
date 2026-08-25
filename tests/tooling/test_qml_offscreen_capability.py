import os
import subprocess
from pathlib import Path

from tests.fixtures.factories import temporary_repository

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_offscreen_qml_gate_fails_when_its_required_runner_is_unavailable() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        qml_directory = repository.path("tests/qml")
        qml_directory.mkdir()
        _ = (qml_directory / "Fixture.qml").write_text("Item {}\n")
        fake_bin = repository.path("fake-bin")
        fake_bin.mkdir()
        for command_name in ("dirname", "find", "grep"):
            (fake_bin / command_name).symlink_to(f"/usr/bin/{command_name}")
        environment = os.environ.copy()
        environment["PATH"] = str(fake_bin)
        result = subprocess.run(
            ["/usr/bin/bash", str(repository.path("scripts/qml_offscreen.sh"))],
            capture_output=True,
            check=False,
            cwd=repository.root,
            env=environment,
            text=True,
        )

    assert result.returncode == 127
    assert "ERROR(required capability)" in result.stderr
