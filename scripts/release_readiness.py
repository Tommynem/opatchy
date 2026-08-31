#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

PROJECT_FILES: Final = ("manifest.json", "pyproject.toml", "CHANGELOG.md")
RELEASE_PREFIX: Final = "v"
MANIFEST_VERSION: Final = re.compile(r'^\s*"version"\s*:\s*"([^"]+)"', re.MULTILINE)
PROJECT_VERSION: Final = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


@dataclass(frozen=True, slots=True)
class Arguments:
    repository: Path
    tag: str
    output_directory: Path


@dataclass(frozen=True, slots=True)
class ReleaseIdentity:
    version: str
    commit: str


def fail(message: str, status: int = 1) -> None:
    print(f"ERROR(release-readiness): {message}", file=sys.stderr)
    raise SystemExit(status)


def parse_arguments(arguments: tuple[str, ...]) -> Arguments:
    if (
        len(arguments) != 7
        or arguments[0] != "--repository"
        or arguments[2] != "--tag"
        or arguments[4] != "--dry-run"
        or arguments[5] != "--output-directory"
    ):
        fail(
            "usage: release_readiness.py --repository PATH --tag vVERSION --dry-run --output-directory PATH"
        )
    repository = Path(arguments[1]).resolve()
    output_directory = Path(arguments[6]).resolve()
    if not repository.is_dir():
        fail(f"repository is unavailable: {repository}")
    if not arguments[3].startswith(RELEASE_PREFIX) or len(arguments[3]) == 1:
        fail("prospective tag must use vVERSION form")
    return Arguments(repository, arguments[3], output_directory)


def run(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/usr/bin/git", *arguments],
        capture_output=True,
        check=False,
        cwd=repository,
        text=True,
    )


def require_clean_tree(repository: Path) -> None:
    tracked = run(repository, "diff", "--quiet")
    staged = run(repository, "diff", "--cached", "--quiet")
    untracked = run(repository, "ls-files", "--others", "--exclude-standard")
    allowed = (".omo/", ".codegraph/", ".playwright-mcp/")
    product_entries = tuple(
        entry
        for entry in untracked.stdout.splitlines()
        if not entry.startswith(allowed)
    )
    if tracked.returncode != 0 or staged.returncode != 0 or product_entries:
        fail("release requires a clean worktree")


def git_output(repository: Path, *arguments: str) -> str:
    result = run(repository, *arguments)
    if result.returncode != 0:
        fail(f"git command failed: {' '.join(arguments)}", result.returncode)
    return result.stdout.strip()


def require_regular_archive_tree(repository: Path) -> None:
    entries = git_output(repository, "ls-files", "-s").splitlines()
    if any(entry.startswith("120000 ") for entry in entries):
        fail("tracked symlink is not allowed in a release")


def release_identity(repository: Path, tag: str) -> ReleaseIdentity:
    missing = tuple(path for path in PROJECT_FILES if not (repository / path).is_file())
    if missing:
        fail(f"required release files are unavailable: {', '.join(missing)}")
    manifest_text = (repository / "manifest.json").read_text(encoding="utf-8")
    project_text = (repository / "pyproject.toml").read_text(encoding="utf-8")
    manifest_match = MANIFEST_VERSION.search(manifest_text)
    project_match = PROJECT_VERSION.search(project_text)
    manifest_version = manifest_match.group(1) if manifest_match is not None else ""
    project_version = project_match.group(1) if project_match is not None else ""
    version = tag.removeprefix(RELEASE_PREFIX)
    changelog = (repository / "CHANGELOG.md").read_text(encoding="utf-8")
    if (
        not isinstance(manifest_version, str)
        or not isinstance(project_version, str)
        or manifest_version != version
        or project_version != version
        or f"## [{version}]" not in changelog
    ):
        fail("manifest, pyproject, changelog, and prospective tag versions must match")
    commit = git_output(repository, "rev-parse", "HEAD")
    if len(commit) != 40:
        fail("release requires an exact full commit SHA")
    return ReleaseIdentity(version, commit)


def run_local_gates(repository: Path) -> None:
    result = subprocess.run(["make", "validate"], cwd=repository, check=False)
    if result.returncode != 0:
        fail("local validation gate failed", result.returncode)


def archive_release(
    arguments: Arguments, identity: ReleaseIdentity
) -> tuple[Path, str]:
    arguments.output_directory.mkdir(parents=True, exist_ok=True)
    archive = arguments.output_directory / f"opatchy-{identity.version}.tar"
    with archive.open("wb") as stream:
        result = subprocess.run(
            [
                "/usr/bin/git",
                "archive",
                "--format=tar",
                f"--prefix=opatchy-{identity.version}/",
                identity.commit,
            ],
            check=False,
            cwd=arguments.repository,
            stdout=stream,
        )
    if result.returncode != 0:
        fail("unable to archive exact release commit", result.returncode)
    with tarfile.open(archive) as contents:
        if any(entry.issym() or entry.islnk() for entry in contents.getmembers()):
            fail("release archive contains a symlink")
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return archive, digest


def write_manifest(
    arguments: Arguments, identity: ReleaseIdentity, digest: str
) -> Path:
    manifest = arguments.output_directory / f"opatchy-{identity.version}.release.json"
    metadata = {
        "archive": f"opatchy-{identity.version}.tar",
        "archiveSha256": digest,
        "commit": identity.commit,
        "tag": arguments.tag,
        "version": identity.version,
    }
    _ = manifest.write_text(
        json.dumps(metadata, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    arguments = parse_arguments(tuple(sys.argv[1:]))
    require_clean_tree(arguments.repository)
    require_regular_archive_tree(arguments.repository)
    identity = release_identity(arguments.repository, arguments.tag)
    run_local_gates(arguments.repository)
    archive, digest = archive_release(arguments, identity)
    manifest = write_manifest(arguments, identity, digest)
    print(f"PASS(release-readiness): {identity.commit} {digest} {archive} {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
