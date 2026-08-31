import pytest

from scripts.publication_model import parse_backlog
from scripts.publication_verifier import CommandResult, PublicationVerifier
from scripts.publication_verifier_model import VerifierError

SHA = "a" * 40
REPOSITORY = "Tommynem/opatchy"
MARKETPLACE = "omacom/omarchy-plugin-marketplace"
BACKLOG = """# Roadmap

<!-- opatchy-roadmap: verifier -->
## Publication verifier

## Value
Verify public publication state before claiming it is ready.

## Scope
Read-only repository and marketplace checks.

## Safety constraints
No write commands or marketplace submission.

## Dependencies
GitHub CLI authentication and public repository APIs.

## Acceptance criteria
Exact matching evidence is required for success.

## Non-goals
Publishing a release or marketplace record.

## Labels
enhancement, roadmap
<!-- /opatchy-roadmap -->
"""


class FakeRunner:
    def __init__(self, results: tuple[CommandResult, ...]) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.results: list[CommandResult] = list(results)

    def run(self, arguments: tuple[str, ...]) -> CommandResult:
        self.calls.append(arguments)
        return self.results.pop(0)


def result(stdout: str) -> CommandResult:
    return CommandResult(0, stdout, "")


def target_response(is_empty: bool) -> str:
    return f'{{"nameWithOwner":"{REPOSITORY}","isEmpty":{str(is_empty).lower()},"viewerPermission":"ADMIN"}}'


def issue_response(*slugs: str) -> str:
    entries = tuple(
        "{"
        + ",".join(
            (
                f'"body":"<!-- opatchy-roadmap-slug: {slug} -->"',
                f'"url":"https://example.invalid/{index}"',
                '"labels":[{"name":"enhancement"},{"name":"roadmap"}]',
            )
        )
        + "}"
        for index, slug in enumerate(slugs, start=1)
    )
    return "[" + ",".join(entries) + "]"


def ci_response(conclusion: str) -> str:
    return (
        "[{"
        f'"headSha":"{SHA}",'
        '"status":"completed",'
        f'"conclusion":"{conclusion}",'
        '"url":"https://example.invalid/run"'
        "}]"
    )


def marketplace_results(
    *, plugin_id: str = "other.plugin"
) -> tuple[CommandResult, ...]:
    registry = (
        f'{{"sources":[{{"type":"suite"}},{{"plugins":{{"{plugin_id}":{{}}}}}}],'
        '"retiredPluginIds":[]}'
    )
    return (
        result('{"defaultBranchRef":{"name":"main"}}'),
        result(f"{SHA}\n"),
        result(registry),
    )


def published_prefix(issues: str, remote_sha: str = SHA) -> tuple[CommandResult, ...]:
    return (
        result("Tommynem\n"),
        result("main\n"),
        result(f"{remote_sha}\n"),
        result(issues),
    )


def test_prepublication_rejects_nonempty_target_before_marketplace_lookup() -> None:
    runner = FakeRunner(
        (
            result("Tommynem\n"),
            result(target_response(False)),
        )
    )

    with pytest.raises(VerifierError, match="target repository"):
        _ = PublicationVerifier(runner, REPOSITORY).verify_pre_publication(
            "io.github.tommynem.opatchy"
        )

    assert len(runner.calls) == 2


def test_prepublication_rejects_marketplace_collision_with_only_read_commands() -> None:
    plugin_id = "io.github.tommynem.opatchy"
    runner = FakeRunner(
        (
            result("Tommynem\n"),
            result(target_response(True)),
            *marketplace_results(plugin_id=plugin_id),
        )
    )

    with pytest.raises(VerifierError, match="marketplace collision"):
        _ = PublicationVerifier(runner, REPOSITORY).verify_pre_publication(plugin_id)

    assert all("create" not in command for call in runner.calls for command in call)
    assert runner.calls[-1] == (
        "gh",
        "api",
        f"repos/{MARKETPLACE}/contents/registry.json?ref={SHA}",
        "-H",
        "Accept: application/vnd.github.raw+json",
    )


def test_prepublication_rejects_malformed_registry_and_command_failures() -> None:
    malformed_runner = FakeRunner(
        (
            result("Tommynem\n"),
            result(target_response(True)),
            result('{"defaultBranchRef":{"name":"main"}}'),
            result(f"{SHA}\n"),
            result("{}"),
        )
    )
    failed_runner = FakeRunner((CommandResult(1, "", "denied"),))

    with pytest.raises(VerifierError, match="incomplete schema"):
        _ = PublicationVerifier(malformed_runner, REPOSITORY).verify_pre_publication(
            "io.github.tommynem.opatchy"
        )
    with pytest.raises(VerifierError, match="owner lookup failed"):
        _ = PublicationVerifier(failed_runner, REPOSITORY).verify_pre_publication(
            "io.github.tommynem.opatchy"
        )


def test_published_state_requires_exact_sha_roadmap_ci_and_no_release_records() -> None:
    runner = FakeRunner(
        (
            *published_prefix(issue_response("verifier")),
            result(ci_response("success")),
            result("[]"),
            result("[]"),
            *marketplace_results(),
        )
    )

    report = PublicationVerifier(runner, REPOSITORY).verify_published(
        parse_backlog(BACKLOG), "io.github.tommynem.opatchy", SHA
    )

    assert report.remote_sha == SHA
    assert report.marketplace_sha == SHA
    assert all("create" not in command for call in runner.calls for command in call)


def test_published_state_rejects_failed_ci_for_expected_sha() -> None:
    runner = FakeRunner(
        (
            *published_prefix(issue_response("verifier")),
            result(ci_response("failure")),
        )
    )

    with pytest.raises(VerifierError, match="successful Validate"):
        _ = PublicationVerifier(runner, REPOSITORY).verify_published(
            parse_backlog(BACKLOG), "io.github.tommynem.opatchy", SHA
        )

    assert len(runner.calls) == 5


def test_published_state_rejects_missing_ci_and_mismatched_remote_sha() -> None:
    missing_ci_runner = FakeRunner(
        (*published_prefix(issue_response("verifier")), result("[]"))
    )
    mismatch_runner = FakeRunner(
        (*published_prefix(issue_response("verifier"), "b" * 40),)
    )

    with pytest.raises(VerifierError, match="successful Validate"):
        _ = PublicationVerifier(missing_ci_runner, REPOSITORY).verify_published(
            parse_backlog(BACKLOG), "io.github.tommynem.opatchy", SHA
        )
    with pytest.raises(VerifierError, match="local reviewed SHA"):
        _ = PublicationVerifier(mismatch_runner, REPOSITORY).verify_published(
            parse_backlog(BACKLOG), "io.github.tommynem.opatchy", SHA
        )


@pytest.mark.parametrize(
    ("issues", "reason"),
    (
        (issue_response(), "roadmap issues"),
        (issue_response("unapproved"), "roadmap issues"),
        (issue_response("verifier", "verifier"), "roadmap issues"),
    ),
)
def test_published_state_rejects_any_remote_roadmap_drift(
    issues: str, reason: str
) -> None:
    runner = FakeRunner(published_prefix(issues))

    with pytest.raises(VerifierError, match=reason):
        _ = PublicationVerifier(runner, REPOSITORY).verify_published(
            parse_backlog(BACKLOG), "io.github.tommynem.opatchy", SHA
        )

    assert len(runner.calls) == 4


@pytest.mark.parametrize("records", ('[{"name":"v0.1.0"}]', '[{"tagName":"v0.1.0"}]'))
def test_published_state_rejects_any_tag_or_release_record(records: str) -> None:
    tags = records if "name" in records else "[]"
    releases = records if "tagName" in records else "[]"
    runner = FakeRunner(
        (
            *published_prefix(issue_response("verifier")),
            result(ci_response("success")),
            result(tags),
            result(releases),
        )
    )

    with pytest.raises(VerifierError, match="tags or releases"):
        _ = PublicationVerifier(runner, REPOSITORY).verify_published(
            parse_backlog(BACKLOG), "io.github.tommynem.opatchy", SHA
        )
