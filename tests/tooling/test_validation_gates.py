import os
import subprocess
from pathlib import Path

from tests.fixtures.factories import TemporaryRepository, temporary_repository

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def run_validation(repository: TemporaryRepository) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["UV_PROJECT_ENVIRONMENT"] = str(REPOSITORY_ROOT / ".venv")
    return subprocess.run(
        ["/usr/bin/bash", str(repository.path("scripts/validate.sh"))],
        capture_output=True,
        check=False,
        cwd=repository.root,
        env=environment,
        text=True,
    )


def test_validate_accepts_the_combined_manifest_fixture() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        result = run_validation(repository)

    assert result.returncode == 0
    assert "PASS(manifest)" in result.stdout


def test_validate_returns_nonzero_when_the_present_manifest_is_invalid() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        manifest_path = repository.path("manifest.json")
        manifest = manifest_path.read_text(encoding="utf-8")
        _ = manifest_path.write_text(
            manifest.replace('"schemaVersion": 1', '"schemaVersion": true'),
            encoding="utf-8",
        )

        result = run_validation(repository)

    assert result.returncode != 0
    assert "FAIL(manifest)" in result.stderr


def test_manifest_validation_hides_and_restores_the_development_environment() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        development_environment = repository.root / ".venv"
        development_environment.symlink_to(
            REPOSITORY_ROOT / ".venv",
            target_is_directory=True,
        )
        fake_bin = repository.path("fake-bin")
        fake_bin.mkdir()
        fake_omarchy = fake_bin / "omarchy"
        _ = fake_omarchy.write_text(
            "#!/usr/bin/env bash\nif [[ -e .venv ]]; then\n    exit 31\nfi\nexit 17\n",
            encoding="utf-8",
        )
        fake_omarchy.chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
        environment["UV_PROJECT_ENVIRONMENT"] = str(REPOSITORY_ROOT / ".venv")

        result = subprocess.run(
            ["/usr/bin/bash", str(repository.path("scripts/validate.sh"))],
            capture_output=True,
            check=False,
            cwd=repository.root,
            env=environment,
            text=True,
        )

        assert result.returncode == 17
        assert "FAIL(manifest): command exited 17" in result.stderr
        assert development_environment.is_symlink()
        assert development_environment.resolve() == REPOSITORY_ROOT / ".venv"


def test_validate_returns_nonzero_when_the_present_type_checker_fails() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        mutation_directory = repository.path("tests/temporary_gates")
        mutation_directory.mkdir()
        _ = (mutation_directory / "type_failure.py").write_text(
            "def result() -> str:\n    return 1\n",
            encoding="utf-8",
        )

        result = run_validation(repository)

    assert result.returncode != 0
    assert "FAIL(type)" in result.stderr


def test_validate_returns_nonzero_when_the_present_js_test_fails() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        _ = repository.path("tests/js/failure.test.mjs").write_text(
            "\n".join(
                (
                    'import assert from "node:assert/strict";',
                    'import test from "node:test";',
                    "",
                    'test("failure", () => {',
                    "  assert.equal(1, 2);",
                    "});",
                    "",
                )
            ),
            encoding="utf-8",
        )

        result = run_validation(repository)

    assert result.returncode != 0
    assert "FAIL(js)" in result.stderr


def test_validate_returns_nonzero_when_a_present_tool_prints_success_then_fails() -> (
    None
):
    with temporary_repository(REPOSITORY_ROOT) as repository:
        fake_bin = repository.path("fake-bin")
        fake_bin.mkdir()
        fake_node = fake_bin / "node"
        _ = fake_node.write_text(
            "#!/usr/bin/env bash\nprintf '%s\\n' success\nexit 7\n",
            encoding="utf-8",
        )
        fake_node.chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
        environment["UV_PROJECT_ENVIRONMENT"] = str(REPOSITORY_ROOT / ".venv")
        result = subprocess.run(
            ["/usr/bin/bash", str(repository.path("scripts/validate.sh"))],
            capture_output=True,
            check=False,
            cwd=repository.root,
            env=environment,
            text=True,
        )

    assert result.returncode == 7
    assert "success" in result.stdout
    assert "FAIL(js): command exited 7" in result.stderr


def test_validate_returns_nonzero_when_the_present_qml_offscreen_gate_fails() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        environment = os.environ.copy()
        environment["OPATCHY_QMLTESTRUNNER"] = str(
            repository.path("missing-qt6-qmltestrunner")
        )
        environment["UV_PROJECT_ENVIRONMENT"] = str(REPOSITORY_ROOT / ".venv")
        result = subprocess.run(
            ["/usr/bin/bash", str(repository.path("scripts/validate.sh"))],
            capture_output=True,
            check=False,
            cwd=repository.root,
            env=environment,
            text=True,
        )

    assert result.returncode != 0
    assert "FAIL(qml-offscreen)" in result.stderr


def test_runtime_smoke_hides_the_development_environment() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        (repository.root / ".venv").symlink_to(
            REPOSITORY_ROOT / ".venv",
            target_is_directory=True,
        )

        result = run_validation(repository)

    assert result.returncode == 0
    assert "PASS(runtime)" in result.stdout
