from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.publication_model import (
    BacklogError,
    RoadmapItem,
    compare_issue_sets,
    parse_backlog,
    parse_existing_issues,
)
from scripts.publication_verifier_model import (
    VerifierError,
    parse_array,
    parse_default_branch,
    parse_marketplace_registry,
    parse_target,
    require_sha,
    require_successful_ci,
)

APPROVED_REPOSITORY = "Tommynem/opatchy"
MARKETPLACE_REPOSITORY = "omacom/omarchy-plugin-marketplace"


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, arguments: tuple[str, ...]) -> CommandResult: ...


class SubprocessRunner:
    def run(self, arguments: tuple[str, ...]) -> CommandResult:
        result = subprocess.run(  # noqa: S603
            arguments, capture_output=True, check=False, text=True
        )
        return CommandResult(result.returncode, result.stdout, result.stderr)


@dataclass(frozen=True, slots=True)
class VerificationReport:
    mode: str
    repository: str
    remote_sha: str
    marketplace_sha: str


@dataclass(frozen=True, slots=True)
class Arguments:
    mode: str
    repository: str
    plugin_id: str
    backlog: Path | None


@dataclass(frozen=True, slots=True)
class PublicationVerifier:
    runner: CommandRunner
    repository: str

    def verify_pre_publication(self, plugin_id: str) -> VerificationReport:
        self.require_owner()
        self.require_empty_target()
        marketplace_sha = self.require_marketplace_absent(plugin_id)
        return VerificationReport(
            "pre-publication", self.repository, "", marketplace_sha
        )

    def verify_published(
        self, items: tuple[RoadmapItem, ...], plugin_id: str, local_sha: str
    ) -> VerificationReport:
        self.require_owner()
        reviewed_sha = require_sha(local_sha, "local reviewed SHA")
        branch = self.target_default_branch()
        remote_sha = require_sha(
            self.run(
                (
                    "gh",
                    "api",
                    f"repos/{self.repository}/commits/{branch}",
                    "--jq",
                    ".sha",
                ),
                "remote default-branch SHA lookup",
            ).stdout,
            "remote default-branch SHA",
        )
        if remote_sha != reviewed_sha:
            raise VerifierError(
                "local reviewed SHA does not match the remote default branch"
            )
        self.require_roadmap_match(items)
        self.require_validate_success(remote_sha, branch)
        self.require_no_tags_or_releases()
        marketplace_sha = self.require_marketplace_absent(plugin_id)
        return VerificationReport(
            "published", self.repository, remote_sha, marketplace_sha
        )

    def resolve_local_sha(self) -> str:
        return require_sha(
            self.run(("git", "rev-parse", "HEAD"), "local reviewed SHA lookup").stdout,
            "local reviewed SHA",
        )

    def require_owner(self) -> None:
        owner = self.repository.partition("/")[0]
        result = self.run(("gh", "api", "user", "--jq", ".login"), "owner lookup")
        if result.stdout.strip() != owner:
            raise VerifierError("GitHub CLI owner does not match the approved owner")

    def require_empty_target(self) -> None:
        result = self.run(
            (
                "gh",
                "repo",
                "view",
                self.repository,
                "--json",
                "nameWithOwner,isEmpty,viewerPermission",
            ),
            "target repository lookup",
        )
        parse_target(result.stdout, self.repository)

    def target_default_branch(self) -> str:
        result = self.run(
            ("gh", "api", f"repos/{self.repository}", "--jq", ".default_branch"),
            "target default-branch lookup",
        )
        branch = result.stdout.strip()
        if not branch:
            raise VerifierError("target repository has no usable default branch")
        return branch

    def require_roadmap_match(self, items: tuple[RoadmapItem, ...]) -> None:
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
                self.repository,
                "--workflow",
                "Validate",
                "--branch",
                branch,
                "--limit",
                "100",
                "--json",
                "headSha,status,conclusion,url",
            ),
            "Validate workflow lookup",
        )
        require_successful_ci(result.stdout, sha)

    def require_no_tags_or_releases(self) -> None:
        tags = self.run(
            ("gh", "api", f"repos/{self.repository}/tags", "--paginate"),
            "tag lookup",
        )
        releases = self.run(
            (
                "gh",
                "release",
                "list",
                "--repo",
                self.repository,
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

    def require_marketplace_absent(self, plugin_id: str) -> str:
        branch_result = self.run(
            (
                "gh",
                "repo",
                "view",
                MARKETPLACE_REPOSITORY,
                "--json",
                "defaultBranchRef",
            ),
            "marketplace default-branch lookup",
        )
        branch = parse_default_branch(branch_result.stdout, "marketplace repository")
        sha = require_sha(
            self.run(
                (
                    "gh",
                    "api",
                    f"repos/{MARKETPLACE_REPOSITORY}/commits/{branch}",
                    "--jq",
                    ".sha",
                ),
                "marketplace branch SHA lookup",
            ).stdout,
            "marketplace branch SHA",
        )
        registry = self.run(
            (
                "gh",
                "api",
                f"repos/{MARKETPLACE_REPOSITORY}/contents/registry.json?ref={sha}",
                "-H",
                "Accept: application/vnd.github.raw+json",
            ),
            "marketplace registry lookup",
        )
        parsed = parse_marketplace_registry(registry.stdout)
        if (
            plugin_id in parsed.active_plugin_ids
            or plugin_id in parsed.retired_plugin_ids
        ):
            raise VerifierError("marketplace collision for the permanent plugin ID")
        return sha

    def run(self, arguments: tuple[str, ...], operation: str) -> CommandResult:
        result = self.runner.run(arguments)
        if result.returncode != 0:
            raise VerifierError(f"{operation} failed")
        return result


def parse_arguments(arguments: tuple[str, ...]) -> Arguments:
    if (
        len(arguments) not in (6, 8)
        or arguments[:1] != ("--mode",)
        or arguments[2:3] != ("--repository",)
        or arguments[4:5] != ("--plugin-id",)
        or (len(arguments) == 8 and arguments[6:7] != ("--backlog",))
    ):
        raise VerifierError(
            "usage: publication_verifier.py --mode MODE --repository OWNER/NAME --plugin-id ID [--backlog PATH]"
        )
    mode, repository, plugin_id = arguments[1], arguments[3], arguments[5]
    backlog = Path(arguments[7]) if len(arguments) == 8 else None
    if (
        mode not in {"pre-publication", "published"}
        or repository != APPROVED_REPOSITORY
    ):
        raise VerifierError("mode or approved repository is invalid")
    if not plugin_id or any(character.isspace() for character in plugin_id):
        raise VerifierError("plugin ID is invalid")
    if (mode == "published") != (backlog is not None):
        raise VerifierError(
            "published mode requires --backlog and pre-publication mode forbids it"
        )
    return Arguments(mode, repository, plugin_id, backlog)


def main() -> int:
    try:
        arguments = parse_arguments(tuple(sys.argv[1:]))
        verifier = PublicationVerifier(SubprocessRunner(), arguments.repository)
        if arguments.mode == "pre-publication":
            report = verifier.verify_pre_publication(arguments.plugin_id)
        else:
            if arguments.backlog is None:
                raise VerifierError("published mode requires a backlog")
            items = parse_backlog(arguments.backlog.read_text(encoding="utf-8"))
            report = verifier.verify_published(
                items, arguments.plugin_id, verifier.resolve_local_sha()
            )
        fields = (
            f"mode={report.mode}",
            f"repository={report.repository}",
            f"remoteSha={report.remote_sha or 'not-applicable'}",
            f"marketplaceSha={report.marketplace_sha}",
        )
        print("PASS(publication-verifier): " + " ".join(fields))
    except (BacklogError, OSError, VerifierError) as error:
        print(f"ERROR(publication-verifier): {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
