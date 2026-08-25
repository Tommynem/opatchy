import json
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


def write_valid_plugin_fixture(repository: TemporaryRepository) -> Path:
    manifest_path = repository.path("manifest.json")
    _ = manifest_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "id": "io.github.tomge.opatchy",
                "name": "Opatchy",
                "version": "0.1.0",
                "kinds": ["service", "bar-widget"],
                "entryPoints": {
                    "service": "Service.qml",
                    "barWidget": "BarWidget.qml",
                },
                "barWidget": {"defaultSection": "right"},
            }
        ),
        encoding="utf-8",
    )
    _ = repository.path("Service.qml").write_text("import QtQuick\n\nItem {}\n")
    _ = repository.path("BarWidget.qml").write_text(
        "import QtQuick\nimport qs.Ui\n\nBarWidget {}\n"
    )
    return manifest_path


def test_validate_accepts_the_combined_manifest_fixture() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        _ = write_valid_plugin_fixture(repository)

        result = run_validation(repository)

    assert result.returncode == 0
    assert "PASS(manifest)" in result.stdout


def test_validate_returns_nonzero_when_the_present_manifest_is_invalid() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        manifest_path = write_valid_plugin_fixture(repository)
        manifest = manifest_path.read_text(encoding="utf-8")
        _ = manifest_path.write_text(
            manifest.replace('"schemaVersion": 1', '"schemaVersion": true'),
            encoding="utf-8",
        )

        result = run_validation(repository)

    assert result.returncode != 0
    assert "FAIL(manifest)" in result.stderr


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
        qml_directory = repository.path("tests/qml")
        qml_directory.mkdir()
        _ = (qml_directory / "Invalid.qml").write_text(
            "import QtQuick 2.15\nimport Opatchy.Invalid\n\nItem {}\n",
            encoding="utf-8",
        )

        result = run_validation(repository)

    assert result.returncode != 0
    assert "FAIL(qml-offscreen)" in result.stderr


def test_runtime_smoke_hides_the_development_environment() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        helper_directory = repository.path("helper")
        helper_directory.mkdir()
        (repository.root / ".venv").symlink_to(
            REPOSITORY_ROOT / ".venv",
            target_is_directory=True,
        )
        _ = (helper_directory / "opatchy.py").write_text(
            "\n".join(
                (
                    '"""Temporary runtime smoke sentinel."""',
                    "",
                    "from importlib.util import find_spec",
                    "",
                    'if find_spec("pytest") is not None:',
                    "    raise SystemExit(1)",
                    "",
                )
            ),
            encoding="utf-8",
        )

        result = run_validation(repository)

    assert result.returncode == 0
    assert "PASS(runtime)" in result.stdout
