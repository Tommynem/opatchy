from __future__ import annotations

from dataclasses import dataclass

from scripts.publication_model import (
    BacklogError,
    RoadmapItem,
    compare_issue_sets,
    parse_existing_issues,
)
from scripts.publication_verifier_marketplace import require_marketplace_absent
from scripts.publication_verifier_model import (
    APPROVED_PLUGIN_ID,
    APPROVED_REPOSITORY,
    VerifierError,
    parse_array,
    parse_published_repository,
    parse_target,
    require_sha,
    require_successful_ci,
)
from scripts.publication_verifier_runner import (
    CommandResult,
    CommandRunner,
    require_result,
)


@dataclass(frozen=True, slots=True)
class VerificationReport:
    mode: str
    remote_sha: str
    marketplace_sha: str


@dataclass(frozen=True, slots=True)
class PublicationVerifier:
    runner: CommandRunner

    def verify_pre_publication(self, plugin_id: str) -> VerificationReport:
        self.require_plugin_id(plugin_id)
        self.require_owner()
        self.require_empty_target()
        return VerificationReport(
            "pre-publication", "", require_marketplace_absent(self.runner)
        )

    def verify_published(
        self, items: tuple[RoadmapItem, ...], plugin_id: str
    ) -> VerificationReport:
        self.require_plugin_id(plugin_id)
        self.require_owner()
        self.require_origin()
        local_sha = require_sha(
            self.run(("git", "rev-parse", "HEAD"), "local SHA").stdout, "local SHA"
        )
        branch = self.require_published_repository()
        remote_sha = require_sha(
            self.run(
                (
                    "gh",
                    "api",
                    f"repos/{APPROVED_REPOSITORY}/commits/{branch}",
                    "--jq",
                    ".sha",
                ),
                "remote SHA",
            ).stdout,
            "remote SHA",
        )
        if local_sha != remote_sha:
            raise VerifierError("local SHA does not match remote default branch")
        self.require_roadmap_match(items)
        self.require_validate_success(remote_sha, branch)
        self.require_no_tags_or_releases()
        return VerificationReport(
            "published", remote_sha, require_marketplace_absent(self.runner)
        )

    def require_plugin_id(self, plugin_id: str) -> None:
        if plugin_id != APPROVED_PLUGIN_ID:
            raise VerifierError("plugin ID does not match the approved identity")

    def require_owner(self) -> None:
        if (
            self.run(
                ("gh", "api", "user", "--jq", ".login"), "owner lookup"
            ).stdout.strip()
            != "Tommynem"
        ):
            raise VerifierError("GitHub CLI owner does not match the approved owner")

    def require_empty_target(self) -> None:
        result = self.run(
            (
                "gh",
                "repo",
                "view",
                APPROVED_REPOSITORY,
                "--json",
                "nameWithOwner,isEmpty,viewerPermission",
            ),
            "target lookup",
        )
        parse_target(result.stdout)

    def require_origin(self) -> None:
        origin = self.run(
            ("git", "remote", "get-url", "origin"), "origin lookup"
        ).stdout.strip()
        if origin not in {
            "git@github.com:Tommynem/opatchy.git",
            "https://github.com/Tommynem/opatchy.git",
            "https://github.com/Tommynem/opatchy",
        }:
            raise VerifierError("origin does not identify the approved repository")

    def require_published_repository(self) -> str:
        result = self.run(
            (
                "gh",
                "repo",
                "view",
                APPROVED_REPOSITORY,
                "--json",
                "nameWithOwner,visibility,url,hasIssuesEnabled,defaultBranchRef",
            ),
            "published repository lookup",
        )
        return parse_published_repository(result.stdout)

    def require_roadmap_match(self, items: tuple[RoadmapItem, ...]) -> None:
        result = self.run(
            (
                "gh",
                "issue",
                "list",
                "--repo",
                APPROVED_REPOSITORY,
                "--state",
                "all",
                "--limit",
                "100",
                "--json",
                "title,body,url,labels",
            ),
            "roadmap issue lookup",
        )
        try:
            comparison = compare_issue_sets(items, parse_existing_issues(result.stdout))
        except BacklogError as error:
            raise VerifierError(
                "roadmap issue response cannot be parsed safely"
            ) from error
        if (
            comparison.missing
            or comparison.unexpected
            or comparison.duplicate
            or comparison.missing_labels
        ):
            raise VerifierError(
                "remote roadmap issues do not exactly match the backlog"
            )

    def require_validate_success(self, sha: str, branch: str) -> None:
        result = self.run(
            (
                "gh",
                "run",
                "list",
                "--repo",
                APPROVED_REPOSITORY,
                "--workflow",
                "Validate",
                "--branch",
                branch,
                "--limit",
                "100",
                "--json",
                "headSha,status,conclusion,url",
            ),
            "Validate lookup",
        )
        require_successful_ci(result.stdout, sha)

    def require_no_tags_or_releases(self) -> None:
        tags = self.run(
            ("gh", "api", f"repos/{APPROVED_REPOSITORY}/tags", "--paginate"),
            "tag lookup",
        )
        releases = self.run(
            (
                "gh",
                "release",
                "list",
                "--repo",
                APPROVED_REPOSITORY,
                "--limit",
                "100",
                "--json",
                "tagName",
            ),
            "release lookup",
        )
        if parse_array(tags.stdout, "tag response") or parse_array(
            releases.stdout, "release response"
        ):
            raise VerifierError(
                "published repository unexpectedly has tags or releases"
            )

    def run(self, arguments: tuple[str, ...], operation: str) -> CommandResult:
        return require_result(self.runner, arguments, operation)
