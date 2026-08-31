import pytest

from scripts.publication_model import parse_backlog
from scripts.publication_verifier import parse_arguments
from scripts.publication_verifier_model import APPROVED_PLUGIN_ID, VerifierError
from scripts.publication_verifier_service import PublicationVerifier
from tests.tooling.publication_verifier_fixtures import (
    FakeRunner,
    issue,
    marketplace,
    published_prefix,
    registry,
    result,
)
from tests.tooling.test_publication_model import BACKLOG


def test_published_verification_uses_exact_read_only_sequence() -> None:
    runner = FakeRunner(
        (*published_prefix(issue("firmware-inventory")), *marketplace(registry()))
    )
    report = PublicationVerifier(runner).verify_published(
        parse_backlog(BACKLOG), APPROVED_PLUGIN_ID
    )

    assert report.remote_sha == "a" * 40
    sha = "a" * 40
    assert runner.calls == [
        ("gh", "api", "user", "--jq", ".login"),
        ("git", "remote", "get-url", "origin"),
        ("git", "rev-parse", "HEAD"),
        (
            "gh",
            "repo",
            "view",
            "Tommynem/opatchy",
            "--json",
            "nameWithOwner,visibility,url,hasIssuesEnabled,defaultBranchRef",
        ),
        ("gh", "api", "repos/Tommynem/opatchy/commits/main", "--jq", ".sha"),
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
        (
            "gh",
            "run",
            "list",
            "--repo",
            "Tommynem/opatchy",
            "--workflow",
            "Validate",
            "--branch",
            "main",
            "--limit",
            "100",
            "--json",
            "headSha,status,conclusion,url",
        ),
        ("gh", "api", "repos/Tommynem/opatchy/tags", "--paginate"),
        (
            "gh",
            "release",
            "list",
            "--repo",
            "Tommynem/opatchy",
            "--limit",
            "100",
            "--json",
            "tagName",
        ),
        (
            "gh",
            "repo",
            "view",
            "omacom/omarchy-plugin-marketplace",
            "--json",
            "defaultBranchRef",
        ),
        (
            "gh",
            "api",
            "repos/omacom/omarchy-plugin-marketplace/commits/main",
            "--jq",
            ".sha",
        ),
        (
            "gh",
            "api",
            f"repos/omacom/omarchy-plugin-marketplace/contents/registry.json?ref={sha}",
            "-H",
            "Accept: application/vnd.github.raw+json",
        ),
    ]


@pytest.mark.parametrize(
    "arguments",
    (
        (
            "--mode",
            "published",
            "--repository",
            "other/repository",
            "--plugin-id",
            APPROVED_PLUGIN_ID,
            "--backlog",
            "docs/backlog.md",
        ),
        (
            "--mode",
            "published",
            "--repository",
            "Tommynem/opatchy",
            "--plugin-id",
            "wrong.plugin",
            "--backlog",
            "docs/backlog.md",
        ),
    ),
)
def test_cli_rejects_unapproved_identity_before_runner_construction(
    arguments: tuple[str, ...],
) -> None:
    with pytest.raises(VerifierError):
        _ = parse_arguments(arguments)


def test_cli_parses_exact_published_arguments() -> None:
    arguments = parse_arguments(
        (
            "--mode",
            "published",
            "--repository",
            "Tommynem/opatchy",
            "--plugin-id",
            APPROVED_PLUGIN_ID,
            "--backlog",
            "docs/backlog.md",
        )
    )

    assert arguments.mode == "published"
    assert arguments.plugin_id == APPROVED_PLUGIN_ID


@pytest.mark.parametrize(
    "issues,conclusion",
    (
        (f"{issue('firmware-inventory')},{issue('firmware-inventory')}", "success"),
        (issue("firmware-inventory"), "failure"),
    ),
)
def test_duplicate_issue_or_failed_ci_stops_at_its_boundary(
    issues: str, conclusion: str
) -> None:
    runner = FakeRunner(published_prefix(issues, conclusion))

    with pytest.raises(VerifierError):
        _ = PublicationVerifier(runner).verify_published(
            parse_backlog(BACKLOG), APPROVED_PLUGIN_ID
        )

    assert len(runner.calls) in {6, 7}


def test_published_rejects_noncanonical_origin_before_local_sha() -> None:
    runner = FakeRunner(
        (result("Tommynem\n"), result("git@github.com:other/repo.git\n"))
    )

    with pytest.raises(VerifierError, match="origin"):
        _ = PublicationVerifier(runner).verify_published(
            parse_backlog(BACKLOG), APPROVED_PLUGIN_ID
        )

    assert runner.calls == [
        ("gh", "api", "user", "--jq", ".login"),
        ("git", "remote", "get-url", "origin"),
    ]
