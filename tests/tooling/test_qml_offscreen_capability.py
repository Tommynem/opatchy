import os
import subprocess
from pathlib import Path

from tests.fixtures.factories import temporary_repository

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def write_fake_runner(path: Path, label: str) -> None:
    _ = path.write_text(
        "\n".join(
            (
                "#!/usr/bin/bash",
                'if [[ "${1:-}" == "-help" ]]; then',
                f'    printf "%s\\n" "{("-repeat n" if label == "qt6" else "Qt 5")}"',
                "    exit 0",
                "fi",
                f'printf %s "{label}" > "${{OPATCHY_QML_RUNNER_LOG}}"',
                "",
            )
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def prepare_qml_test(repository_root: Path) -> tuple[Path, Path]:
    qml_directory = repository_root / "tests/qml"
    qml_directory.mkdir()
    _ = (qml_directory / "tst_fixture.qml").write_text(
        "\n".join(
            (
                "import QtQuick 2.15",
                "import QtTest 1.3",
                "",
                "TestCase {",
                "    when: true",
                '    name: "Fixture"',
                "    function test_passes() {",
                "        verify(true)",
                "    }",
                "}",
                "",
            )
        )
    )
    fake_bin = repository_root / "fake-bin"
    fake_bin.mkdir()
    for command_name in ("dirname", "find", "grep"):
        (fake_bin / command_name).symlink_to(f"/usr/bin/{command_name}")
    return fake_bin, repository_root / "runner.log"


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
        environment["OPATCHY_QMLTESTRUNNER"] = str(
            repository.path("missing-qt6-qmltestrunner")
        )
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


def test_offscreen_qml_gate_selects_qt6_runner_over_qt5_path_runner() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        fake_bin, runner_log = prepare_qml_test(repository.root)
        write_fake_runner(fake_bin / "qmltestrunner", "qt5")
        qt6_runner = repository.path("qt6-qmltestrunner")
        write_fake_runner(qt6_runner, "qt6")
        environment = os.environ.copy()
        environment["PATH"] = str(fake_bin)
        environment["OPATCHY_QMLTESTRUNNER"] = str(qt6_runner)
        environment["OPATCHY_QML_RUNNER_LOG"] = str(runner_log)
        result = subprocess.run(
            ["/usr/bin/bash", str(repository.path("scripts/qml_offscreen.sh"))],
            capture_output=True,
            check=False,
            cwd=repository.root,
            env=environment,
            text=True,
        )

        selected_runner = runner_log.read_text(encoding="utf-8")

    assert result.returncode == 0
    assert selected_runner == "qt6"


def test_offscreen_qml_gate_uses_the_system_qt6_runner_when_path_has_qt5() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        fake_bin, runner_log = prepare_qml_test(repository.root)
        write_fake_runner(fake_bin / "qmltestrunner", "qt5")
        environment = os.environ.copy()
        environment["PATH"] = str(fake_bin)
        environment["OPATCHY_QML_RUNNER_LOG"] = str(runner_log)
        result = subprocess.run(
            ["/usr/bin/bash", str(repository.path("scripts/qml_offscreen.sh"))],
            capture_output=True,
            check=False,
            cwd=repository.root,
            env=environment,
            text=True,
        )

    assert result.returncode == 0
    assert not runner_log.exists()


def test_offscreen_qml_gate_rejects_qt5_when_qt6_runner_is_missing() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        fake_bin, runner_log = prepare_qml_test(repository.root)
        write_fake_runner(fake_bin / "qmltestrunner", "qt5")
        environment = os.environ.copy()
        environment["PATH"] = str(fake_bin)
        environment["OPATCHY_QMLTESTRUNNER"] = str(repository.path("missing-qt6"))
        environment["OPATCHY_QML_RUNNER_LOG"] = str(runner_log)
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


def test_offscreen_qml_gate_rejects_the_system_qt5_runner() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        _, _ = prepare_qml_test(repository.root)
        environment = os.environ.copy()
        environment["OPATCHY_QMLTESTRUNNER"] = "/usr/bin/qmltestrunner"
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
