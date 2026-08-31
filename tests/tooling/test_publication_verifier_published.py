import pytest

from scripts.publication_model import parse_backlog
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
    assert len(runner.calls) == 12
    assert runner.calls[1] == ("git", "remote", "get-url", "origin")
    assert runner.calls[3][0:3] == ("gh", "repo", "view")


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
