import subprocess
import sys
from pathlib import Path

import pytest

from scripts.publication_model import parse_backlog
from scripts.publish_repository import CommandResult, PublicationError, Publisher
from tests.tooling.test_publication_model import BACKLOG

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class FakeRunner:
    """Record fixed argv requests and return queued command outcomes."""

    def __init__(self, results: tuple[CommandResult, ...]) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.results: list[CommandResult] = list(results)

    def run(self, arguments: tuple[str, ...]) -> CommandResult:
        self.calls.append(arguments)
        return self.results.pop(0)


def test_seed_dry_run_avoids_write_commands_when_roadmap_issues_are_missing() -> None:
    # Given: an approved owner and a remote with no roadmap issues.
    runner = FakeRunner(
        (
            CommandResult(0, "Tommynem\n", ""),
            CommandResult(0, "[]", ""),
        )
    )
    publisher = Publisher(runner, "Tommynem/opatchy", "Tommynem")

    # When: seeding is requested as a dry run.
    publisher.seed(parse_backlog(BACKLOG), dry_run=True)

    # Then: only read-only owner and issue-list requests run.
    assert runner.calls == [
        ("gh", "api", "user", "--jq", ".login"),
        (
            "gh",
            "issue",
            "list",
            "--repo",
            "Tommynem/opatchy",
            "--state",
            "all",
            "--limit",
            "100",
            "--json",
            "title,body,url,labels",
        ),
    ]


def test_seed_rejects_wrong_owner_before_listing_or_creating_issues() -> None:
    # Given: a CLI session authenticated as another account.
    runner = FakeRunner((CommandResult(0, "other-owner\n", ""),))
    publisher = Publisher(runner, "Tommynem/opatchy", "Tommynem")

    # When: the seeder is invoked.
    # Then: owner validation stops every follow-on side effect.
    with pytest.raises(PublicationError):
        publisher.seed(parse_backlog(BACKLOG), dry_run=False)
    assert len(runner.calls) == 1


def test_seed_rejects_command_failure_before_issue_creation() -> None:
    # Given: the remote issue query fails after owner verification.
    runner = FakeRunner(
        (
            CommandResult(0, "Tommynem\n", ""),
            CommandResult(1, "", "denied"),
        )
    )
    publisher = Publisher(runner, "Tommynem/opatchy", "Tommynem")

    # When: the seeder is invoked.
    # Then: the command failure prevents label or issue creation.
    with pytest.raises(PublicationError):
        publisher.seed(parse_backlog(BACKLOG), dry_run=False)
    assert len(runner.calls) == 2


def test_cli_reports_usage_when_script_is_launched_directly() -> None:
    # Given: the tracked publisher launched as its documented script path.
    command = (sys.executable, str(REPOSITORY_ROOT / "scripts/publish_repository.py"))

    # When: it receives an invalid command shape before any GitHub request.
    result = subprocess.run(command, capture_output=True, check=False, text=True)

    # Then: its own fail-closed usage error is observable rather than an import error.
    assert result.returncode != 0
    assert "usage: publish_repository.py" in result.stderr
