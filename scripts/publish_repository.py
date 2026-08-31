from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, override

if __package__:
    from .publication_model import (
        BacklogError,
        ExistingIssue,
        RoadmapItem,
        compare_issue_sets,
        parse_backlog,
        parse_existing_issues,
    )
else:
    from publication_model import (
        BacklogError,
        ExistingIssue,
        RoadmapItem,
        compare_issue_sets,
        parse_backlog,
        parse_existing_issues,
    )


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class PublicationError(Exception):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


class CommandRunner(Protocol):
    def run(self, arguments: tuple[str, ...]) -> CommandResult: ...


class GhRunner:
    def run(self, arguments: tuple[str, ...]) -> CommandResult:
        result = subprocess.run(arguments, capture_output=True, check=False, text=True)
        return CommandResult(result.returncode, result.stdout, result.stderr)


@dataclass(frozen=True, slots=True)
class Publisher:
    runner: CommandRunner
    repository: str
    owner: str

    def seed(self, items: tuple[RoadmapItem, ...], *, dry_run: bool) -> None:
        self.require_owner()
        existing = self.list_existing_issues()
        comparison = compare_issue_sets(items, existing)
        if not comparison.can_seed:
            raise PublicationError(
                "remote roadmap issues do not match the committed model"
            )
        missing = tuple(item for item in items if item.slug in comparison.missing)
        if dry_run:
            for item in missing:
                print(f"DRY-RUN(create issue): {item.slug}")
            return
        if not missing:
            print("PASS(publication): issue set already matches")
            return
        self.create_labels()
        for item in missing:
            self.create_issue(item)
        print(f"PASS(publication): created {len(missing)} roadmap issues")

    def require_owner(self) -> None:
        result = self.run(("gh", "api", "user", "--jq", ".login"), "owner lookup")
        if result.stdout.strip() != self.owner:
            raise PublicationError("GitHub CLI owner does not match the approved owner")

    def list_existing_issues(self) -> tuple[ExistingIssue, ...]:
        result = self.run(
            (
                "gh",
                "issue",
                "list",
                "--repo",
                self.repository,
                "--state",
                "all",
                "--limit",
                "100",
                "--json",
                "title,body,url,labels",
            ),
            "issue list",
        )
        try:
            return parse_existing_issues(result.stdout)
        except BacklogError as error:
            raise PublicationError(
                "GitHub issue list cannot be parsed safely"
            ) from error

    def create_labels(self) -> None:
        for label in ("enhancement", "roadmap"):
            _ = self.run(
                ("gh", "label", "create", label, "--repo", self.repository, "--force"),
                f"label create {label}",
            )

    def create_issue(self, item: RoadmapItem) -> None:
        _ = self.run(
            (
                "gh",
                "issue",
                "create",
                "--repo",
                self.repository,
                "--title",
                f"[{item.slug}] {item.title}",
                "--body",
                item.issue_body,
                "--label",
                "enhancement",
                "--label",
                "roadmap",
            ),
            f"issue create {item.slug}",
        )

    def run(self, arguments: tuple[str, ...], operation: str) -> CommandResult:
        result = self.runner.run(arguments)
        if result.returncode != 0:
            raise PublicationError(f"{operation} failed")
        return result


def parse_arguments(arguments: tuple[str, ...]) -> tuple[str, Path, bool]:
    if len(arguments) not in (4, 5) or arguments[:1] != ("--repository",):
        raise PublicationError(
            "usage: publish_repository.py --repository OWNER/NAME --backlog PATH [--dry-run]"
        )
    if arguments[2] != "--backlog" or (
        len(arguments) == 5 and arguments[4] != "--dry-run"
    ):
        raise PublicationError(
            "usage: publish_repository.py --repository OWNER/NAME --backlog PATH [--dry-run]"
        )
    repository = arguments[1]
    owner, separator, name = repository.partition("/")
    if not owner or not separator or not name or "/" in name:
        raise PublicationError("repository must use OWNER/NAME form")
    return repository, Path(arguments[3]), len(arguments) == 5


def main() -> int:
    try:
        repository, backlog_path, dry_run = parse_arguments(tuple(sys.argv[1:]))
        items = parse_backlog(backlog_path.read_text(encoding="utf-8"))
        owner = repository.partition("/")[0]
        Publisher(GhRunner(), repository, owner).seed(items, dry_run=dry_run)
    except (BacklogError, OSError, PublicationError) as error:
        print(f"ERROR(publication): {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
