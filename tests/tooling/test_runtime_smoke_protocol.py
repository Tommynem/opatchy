import os
import subprocess
from pathlib import Path

from tests.fixtures.factories import TemporaryRepository, temporary_repository

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def write_runtime_helper(repository: TemporaryRepository, source: str) -> None:
    helper_directory = repository.path("helper")
    helper_directory.mkdir()
    (repository.root / ".venv").symlink_to(
        REPOSITORY_ROOT / ".venv",
        target_is_directory=True,
    )
    _ = (helper_directory / "opatchy.py").write_text(source, encoding="utf-8")


def run_runtime_smoke(
    repository: TemporaryRepository,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["UV_PROJECT_ENVIRONMENT"] = str(REPOSITORY_ROOT / ".venv")
    return subprocess.run(
        ["/usr/bin/bash", str(repository.path("scripts/runtime_without_venv.sh"))],
        capture_output=True,
        check=False,
        cwd=repository.root,
        env=environment,
        text=True,
    )


def assert_runtime_smoke_rejects(source: str) -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        write_runtime_helper(repository, source)

        result = run_runtime_smoke(repository)

    assert result.returncode != 0


def test_runtime_smoke_accepts_typed_state_unavailable_exit_two() -> None:
    source = "\n".join(
        (
            '"""Typed runtime error fixture."""',
            "",
            "import json",
            "import sys",
            "",
            "payload = {",
            '    "protocolVersion": 1,',
            '    "kind": "error",',
            '    "error": {"code": "STATE_UNAVAILABLE"},',
            "}",
            'sys.stdout.write(json.dumps(payload) + "\\n")',
            "raise SystemExit(2)",
            "",
        )
    )
    with temporary_repository(REPOSITORY_ROOT) as repository:
        write_runtime_helper(repository, source)

        result = run_runtime_smoke(repository)

    assert result.returncode == 0
    assert "PASS(runtime)" in result.stdout


def test_runtime_smoke_rejects_malformed_exit_two_output() -> None:
    assert_runtime_smoke_rejects("raise SystemExit(2)\n")


def test_runtime_smoke_rejects_multiple_exit_two_objects() -> None:
    source = "\n".join(
        (
            "import sys",
            "",
            'sys.stdout.write("{}\\n{}\\n")',
            "raise SystemExit(2)",
            "",
        )
    )
    assert_runtime_smoke_rejects(source)


def test_runtime_smoke_rejects_traceback_output_with_exit_two() -> None:
    source = "\n".join(
        (
            "import sys",
            "",
            'sys.stdout.write("Traceback (most recent call last):\\n")',
            "raise SystemExit(2)",
            "",
        )
    )
    assert_runtime_smoke_rejects(source)


def test_runtime_smoke_rejects_stderr_with_exit_two() -> None:
    source = "\n".join(
        (
            "import sys",
            "",
            'sys.stderr.write("unexpected diagnostic\\n")',
            "raise SystemExit(2)",
            "",
        )
    )
    assert_runtime_smoke_rejects(source)


def test_runtime_smoke_rejects_stderr_with_exit_zero() -> None:
    source = "\n".join(
        (
            "import sys",
            "",
            'sys.stderr.write("unexpected diagnostic\\n")',
            "",
        )
    )
    assert_runtime_smoke_rejects(source)


def test_runtime_smoke_rejects_dev_package_visibility() -> None:
    source = "\n".join(
        (
            "import pytest",
            "",
            "raise SystemExit(2)",
            "",
        )
    )
    assert_runtime_smoke_rejects(source)
