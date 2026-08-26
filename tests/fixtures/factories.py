import shutil
import subprocess
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

LOCAL_METADATA_NAMES: Final = frozenset(
    {
        ".codegraph",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "htmlcov",
    }
)


def isolated_copy_ignore(_: str, names: list[str]) -> set[str]:
    return set(names).intersection(LOCAL_METADATA_NAMES)


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
            ignore=isolated_copy_ignore,
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
