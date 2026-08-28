from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures.factories import TemporaryRepository, temporary_repository

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _run(repository: TemporaryRepository) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(repository.path("scripts/security_check.py"))],
        capture_output=True,
        check=False,
        cwd=repository.root,
        encoding="utf-8",
    )


def test_security_check_accepts_the_product_source_tree() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        result = _run(repository)

    assert result.returncode == 0
    assert "PASS(security-policy)" in result.stdout


@pytest.mark.parametrize(
    ("relative_path", "contents", "rule"),
    (
        (
            "helper/opatchy_helper/e2e_mutation.py",
            'COMMAND = ("/usr/bin/pacman", "-S", "unsafe")\n',
            "mutation-command",
        ),
        (
            "helper/opatchy_helper/e2e_mutation.py",
            'COMMAND = ("/usr/bin/pacman", "-Syu")\n',
            "mutation-command",
        ),
        (
            "qml/models/E2eMutation.qml",
            'QtObject { property var command: ["/usr/bin/pacman", "-Syu"] }\n',
            "mutation-command",
        ),
        (
            "helper/opatchy_helper/e2e_shell.py",
            'import os\nos.system("unsafe")\n',
            "shell-api",
        ),
        (
            "qml/components/E2eRichText.qml",
            'Item { property string text: "<b>unsafe</b>" }\n',
            "rich-text",
        ),
        (
            "Panel.qml",
            'Item { property string text: "<b>unsafe</b>" }\n',
            "rich-text",
        ),
        (
            "qml/models/E2eUnsafeUrl.js",
            'var URL = "http://unsafe.invalid"\n',
            "unsafe-url",
        ),
        (
            "qml/components/E2ePalette.qml",
            'Item { property color foreground: "#ff00ff" }\n',
            "hardcoded-palette",
        ),
        (
            "qml/components/E2ePalette.qml",
            "Item { property color foreground: Qt.rgba(1, 0, 1, 1) }\n",
            "hardcoded-palette",
        ),
        (
            "helper/opatchy_helper/e2e_dependency.py",
            "import requests\n",
            "runtime-dependency",
        ),
        (
            "helper/opatchy_helper/e2e_dependency.py",
            '__import__("requests")\n',
            "runtime-dependency",
        ),
        (
            "helper/opatchy_helper/e2e_oversized.py",
            "value = 0\n" * 251,
            "oversized-module",
        ),
        (
            "qml/models/E2eOversized.js",
            "value = 0\n" * 251,
            "oversized-module",
        ),
    ),
)
def test_security_check_rejects_each_prohibited_source_mutation(
    relative_path: str, contents: str, rule: str
) -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        path = repository.path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")
        result = _run(repository)

    assert result.returncode != 0
    assert f"SECURITY POLICY VIOLATION({rule})" in result.stderr


def test_security_check_rejects_unsafe_edits_to_the_process_boundary() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        path = repository.path("helper/opatchy_helper/runner_process.py")
        with path.open("a", encoding="utf-8") as handle:
            _ = handle.write('\nsubprocess.run(["/usr/bin/pacman", "-Syu"])\n')
        result = _run(repository)

    assert result.returncode != 0
    assert "SECURITY POLICY VIOLATION(mutation-command)" in result.stderr


def test_security_check_rejects_unsafe_qml_process_boundary_edits() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        path = repository.path("qml/models/TerminalHandoff.qml")
        with path.open("a", encoding="utf-8") as handle:
            _ = handle.write('\nvar unsafe = ["/usr/bin/pacman", "-Syu"]\n')
        result = _run(repository)

    assert result.returncode != 0
    assert "SECURITY POLICY VIOLATION(mutation-command)" in result.stderr
