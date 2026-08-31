from __future__ import annotations

import os
import subprocess
from pathlib import Path
from shutil import which
from typing import Final

from opatchy_helper.models import SnapshotResponse
from opatchy_helper.protocol import encode_response

_ROOT = Path(__file__).resolve().parents[2]
_PRESENTATION_RUNNER = _ROOT / "tests" / "e2e" / "offline_presentation.mjs"


def resolve_node_path(repository_root: Path, executable_path: str) -> str | None:
    root = repository_root.resolve()
    host_path = os.pathsep.join(
        directory
        for directory in executable_path.split(os.pathsep)
        if not Path(directory).resolve().is_relative_to(root)
    )
    return which("node", path=host_path)


node_path = resolve_node_path(_ROOT, os.pathsep.join(os.get_exec_path()))
if node_path is None:
    raise RuntimeError("node is required for offline presentation tests")
_NODE: Final = node_path


def assert_qml_presentation(snapshot: SnapshotResponse) -> None:
    result = subprocess.run(
        [_NODE, str(_PRESENTATION_RUNNER)],
        check=False,
        capture_output=True,
        cwd=_ROOT,
        input=encode_response(snapshot),
    )
    assert result.returncode == 0, result.stderr.decode("utf-8")


def assert_qml_rejects(raw: bytes) -> None:
    result = subprocess.run(
        [_NODE, str(_PRESENTATION_RUNNER), "--reject"],
        check=False,
        capture_output=True,
        cwd=_ROOT,
        input=raw,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8")
