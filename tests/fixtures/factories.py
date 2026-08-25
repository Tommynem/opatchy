import shutil
import subprocess
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TemporaryRepository:
    """A disposable copy of the checkout for harness mutation tests."""

    root: Path

    def path(self, relative_path: str) -> Path:
        """Return a checked-in path inside this temporary checkout."""
        return self.root / relative_path


@contextmanager
def temporary_repository(source: Path) -> Generator[TemporaryRepository, None, None]:
    """Copy a checkout without generated local state and remove it afterwards."""
    with tempfile.TemporaryDirectory(prefix="opatchy-harness-") as temporary_directory:
        root = Path(temporary_directory) / "checkout"
        _ = shutil.copytree(
            source,
            root,
            ignore=shutil.ignore_patterns(
                ".git",
                ".mypy_cache",
                ".pytest_cache",
                ".ruff_cache",
                ".venv",
                "__pycache__",
                "htmlcov",
            ),
        )
        shutil.rmtree(root / "tests" / "tooling")
        _ = subprocess.run(
            ["/usr/bin/git", "init", "--quiet"],
            capture_output=True,
            check=True,
            cwd=root,
            text=True,
        )
        yield TemporaryRepository(root)
