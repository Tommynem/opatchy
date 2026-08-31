import os
import re
import subprocess
import sys
from pathlib import Path

from tests.fixtures.factories import TemporaryRepository, temporary_repository

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RELEASE_SCRIPT = "scripts/release_readiness.py"
FIXTURE_IDENTITY = ("Fixture", "fixture@example.invalid")


def git(
    repository: TemporaryRepository, *arguments: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/usr/bin/git", *arguments],
        capture_output=True,
        check=True,
        cwd=repository.root,
        text=True,
    )


def commit_fixture(repository: TemporaryRepository) -> str:
    disposable_paths = (".omo", ".playwright-mcp")
    for path in disposable_paths:
        candidate = repository.root / path
        if candidate.exists():
            if candidate.is_dir():
                for child in sorted(candidate.rglob("*"), reverse=True):
                    if child.is_file() or child.is_symlink():
                        child.unlink()
                    elif child.is_dir():
                        child.rmdir()
                candidate.rmdir()
            else:
                candidate.unlink()
    _ = git(repository, "add", ".")
    _ = git(
        repository,
        "-c",
        f"user.name={FIXTURE_IDENTITY[0]}",
        "-c",
        f"user.email={FIXTURE_IDENTITY[1]}",
        "commit",
        "--quiet",
        "-m",
        "fixture release",
    )
    return git(repository, "rev-parse", "HEAD").stdout.strip()


def write_fake_make(repository: TemporaryRepository, exit_code: int) -> Path:
    fake_bin = repository.root.parent / "fake-bin"
    fake_bin.mkdir(exist_ok=True)
    fake_make = fake_bin / "make"
    _ = fake_make.write_text(
        f"#!/usr/bin/env bash\nexit {exit_code}\n", encoding="utf-8"
    )
    fake_make.chmod(0o755)
    return fake_bin


def run_release(
    repository: TemporaryRepository, fake_bin: Path, output_directory: Path
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    return subprocess.run(
        [
            sys.executable,
            str(repository.path(RELEASE_SCRIPT)),
            "--repository",
            str(repository.root),
            "--tag",
            "v0.1.0",
            "--dry-run",
            "--output-directory",
            str(output_directory),
        ],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )


def test_release_dry_run_creates_exact_commit_manifest_and_archive() -> None:
    # Given: a clean committed repository and a passing local validation mirror.
    with temporary_repository(REPOSITORY_ROOT) as repository:
        commit = commit_fixture(repository)
        fake_bin = write_fake_make(repository, 0)
        output_directory = repository.root / "release-output"

        # When: the release dry-run is requested for the prospective version tag.
        result = run_release(repository, fake_bin, output_directory)

        # Then: the emitted metadata binds a deterministic archive to that full commit.
        metadata = (output_directory / "opatchy-0.1.0.release.json").read_text(
            encoding="utf-8"
        )
        assert result.returncode == 0
        assert f'"commit":"{commit}"' in metadata
        assert re.search(r'"archiveSha256":"[0-9a-f]{64}"', metadata) is not None
        assert (output_directory / "opatchy-0.1.0.tar").is_file()


def test_release_dry_run_rejects_dirty_tree() -> None:
    # Given: a repository changed after its release commit.
    with temporary_repository(REPOSITORY_ROOT) as repository:
        _ = commit_fixture(repository)
        _ = repository.path("README.md").write_text("dirty\n", encoding="utf-8")

        # When: release readiness inspects the worktree.
        result = run_release(
            repository, write_fake_make(repository, 0), repository.root / "out"
        )

    # Then: it fails before making an archive.
    assert result.returncode != 0
    assert "clean worktree" in result.stderr


def test_release_dry_run_rejects_version_mismatch_and_symlink() -> None:
    # Given: committed fixture mutations that violate release identity and tree safety.
    with temporary_repository(REPOSITORY_ROOT) as repository:
        manifest = repository.path("manifest.json")
        _ = manifest.write_text(
            manifest.read_text(encoding="utf-8").replace('"0.1.0"', '"0.1.1"'),
            encoding="utf-8",
        )
        _ = commit_fixture(repository)

        # When: release readiness compares released version sources.
        mismatch = run_release(
            repository, write_fake_make(repository, 0), repository.root / "mismatch"
        )

        # Then: it rejects the inconsistent committed release.
        assert mismatch.returncode != 0
        assert "version" in mismatch.stderr

    with temporary_repository(REPOSITORY_ROOT) as repository:
        unsafe_link = repository.path("unsafe-link")
        unsafe_link.symlink_to("README.md")
        _ = commit_fixture(repository)

        # When: release readiness inspects a tracked symbolic link.
        symlink = run_release(
            repository, write_fake_make(repository, 0), repository.root / "symlink"
        )

    # Then: it fails closed rather than packaging the link.
    assert symlink.returncode != 0
    assert "symlink" in symlink.stderr


def test_release_dry_run_rejects_red_local_gate() -> None:
    # Given: a clean committed repository whose local mirror exits nonzero.
    with temporary_repository(REPOSITORY_ROOT) as repository:
        _ = commit_fixture(repository)

        # When: release readiness executes that gate.
        result = run_release(
            repository, write_fake_make(repository, 17), repository.root / "out"
        )

    # Then: publication preparation fails closed.
    assert result.returncode == 17
    assert "local validation gate failed" in result.stderr
