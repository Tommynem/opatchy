import os
import subprocess
from pathlib import Path

from tests.fixtures.factories import TemporaryRepository, temporary_repository

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def write_helper_package(repository: TemporaryRepository) -> None:
    package_directory = repository.path("helper/opatchy_helper")
    package_directory.mkdir(parents=True)
    _ = (package_directory / "__init__.py").write_text("")
    _ = (package_directory / "cli.py").write_text("def main() -> int:\n    return 2\n")
    _ = repository.path("helper/opatchy.py").write_text(
        "from opatchy_helper.cli import main\n\nraise SystemExit(main())\n"
    )


def test_basedpyright_resolves_helper_package_from_helper_execution_root() -> None:
    with temporary_repository(REPOSITORY_ROOT) as repository:
        write_helper_package(repository)
        environment = os.environ.copy()
        environment["UV_PROJECT_ENVIRONMENT"] = str(REPOSITORY_ROOT / ".venv")
        result = subprocess.run(
            ["uv", "run", "--locked", "--no-sync", "basedpyright"],
            capture_output=True,
            check=False,
            cwd=repository.root,
            env=environment,
            text=True,
        )

    assert result.returncode == 0, result.stdout + result.stderr
