import os
import subprocess
from pathlib import Path

from tests.fixtures.factories import temporary_repository

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_validate_returns_nonzero_when_the_present_formatter_fails() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        mutation_directory = repository.path("tests/temporary_gates")
        mutation_directory.mkdir()
        _ = (mutation_directory / "unformatted.py").write_text(
            "value=1\n",
            encoding="utf-8",
        )
        environment = os.environ.copy()
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
    assert "FAIL(format)" in result.stderr
