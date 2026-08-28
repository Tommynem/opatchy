from __future__ import annotations

import subprocess
from pathlib import Path

from opatchy_helper.models import SnapshotResponse
from opatchy_helper.protocol import encode_response

_ROOT = Path(__file__).resolve().parents[2]
_PRESENTATION_RUNNER = _ROOT / "tests" / "e2e" / "offline_presentation.mjs"


def assert_qml_presentation(snapshot: SnapshotResponse) -> None:
    result = subprocess.run(
        ["/usr/bin/node", str(_PRESENTATION_RUNNER)],
        check=False,
        capture_output=True,
        cwd=_ROOT,
        input=encode_response(snapshot),
    )
    assert result.returncode == 0, result.stderr.decode("utf-8")


def assert_qml_rejects(raw: bytes) -> None:
    result = subprocess.run(
        ["/usr/bin/node", str(_PRESENTATION_RUNNER), "--reject"],
        check=False,
        capture_output=True,
        cwd=_ROOT,
        input=raw,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8")
