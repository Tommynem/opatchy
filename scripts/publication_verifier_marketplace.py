from __future__ import annotations

from scripts.publication_verifier_model import (
    APPROVED_PLUGIN_ID,
    MARKETPLACE_REPOSITORY,
    VerifierError,
    parse_default_branch,
    parse_marketplace_registry,
    require_sha,
)
from scripts.publication_verifier_runner import CommandRunner, require_result


def require_marketplace_absent(runner: CommandRunner) -> str:
    branch = parse_default_branch(
        require_result(
            runner,
            (
                "gh",
                "repo",
                "view",
                MARKETPLACE_REPOSITORY,
                "--json",
                "defaultBranchRef",
            ),
            "marketplace branch lookup",
        ).stdout,
        "marketplace repository",
    )
    sha = require_sha(
        require_result(
            runner,
            (
                "gh",
                "api",
                f"repos/{MARKETPLACE_REPOSITORY}/commits/{branch}",
                "--jq",
                ".sha",
            ),
            "marketplace SHA lookup",
        ).stdout,
        "marketplace SHA",
    )
    registry = require_result(
        runner,
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
        APPROVED_PLUGIN_ID in parsed.active_plugin_ids
        or APPROVED_PLUGIN_ID in parsed.retired_plugin_ids
    ):
        raise VerifierError("marketplace collision for the permanent plugin ID")
    return sha
