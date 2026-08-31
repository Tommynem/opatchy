import subprocess
import sys
from pathlib import Path

from tests.fixtures.factories import temporary_repository

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
POLICY_SCRIPT = "scripts/ci_policy.py"
PINNED_CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"


def run_policy(repository_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(repository_root / POLICY_SCRIPT),
            "--repository",
            str(repository_root),
        ],
        capture_output=True,
        check=False,
        text=True,
    )


def write_workflow(repository_root: Path, content: str) -> None:
    workflow_directory = repository_root / ".github" / "workflows"
    workflow_directory.mkdir(parents=True, exist_ok=True)
    _ = (workflow_directory / "ci.yml").write_text(content, encoding="utf-8")


def valid_workflow() -> str:
    return "\n".join(
        (
            "name: CI",
            "on: [push]",
            "permissions:",
            "  contents: read",
            "jobs:",
            "  validate:",
            "    runs-on: ubuntu-24.04",
            "    steps:",
            f"      - uses: {PINNED_CHECKOUT}",
            "",
        )
    )


def test_ci_policy_accepts_immutable_actions_and_read_only_permissions() -> None:
    # Given: a workflow with a full action SHA and least-privilege permissions.
    with temporary_repository(REPOSITORY_ROOT) as repository:
        write_workflow(repository.root, valid_workflow())

        # When: the CI policy gate inspects it.
        result = run_policy(repository.root)

    # Then: the policy gate accepts the workflow.
    assert result.returncode == 0
    assert "PASS(ci-policy)" in result.stdout


def test_ci_policy_rejects_mutable_action_reference() -> None:
    # Given: a workflow whose action uses a mutable tag.
    with temporary_repository(REPOSITORY_ROOT) as repository:
        write_workflow(
            repository.root,
            valid_workflow().replace(PINNED_CHECKOUT, "actions/checkout@v4"),
        )

        # When: the CI policy gate inspects it.
        result = run_policy(repository.root)

    # Then: the policy gate fails closed.
    assert result.returncode != 0
    assert "mutable action reference" in result.stderr


def test_ci_policy_rejects_write_permission() -> None:
    # Given: a workflow that requests repository write access.
    with temporary_repository(REPOSITORY_ROOT) as repository:
        write_workflow(
            repository.root,
            valid_workflow().replace("contents: read", "contents: write"),
        )

        # When: the CI policy gate inspects it.
        result = run_policy(repository.root)

    # Then: the policy gate fails closed.
    assert result.returncode != 0
    assert "permissions must be exactly contents: read" in result.stderr


def test_ci_policy_rejects_job_level_write_override() -> None:
    # Given: a read-only workflow with one escalating job override.
    with temporary_repository(REPOSITORY_ROOT) as repository:
        write_workflow(
            repository.root,
            valid_workflow().replace(
                "    runs-on: ubuntu-24.04",
                "    permissions:\n      contents: write\n    runs-on: ubuntu-24.04",
            ),
        )

        # When: the policy gate parses the nested permission map.
        result = run_policy(repository.root)

    # Then: the job cannot escalate the workflow-level read grant.
    assert result.returncode != 0
    assert "permissions must be exactly contents: read" in result.stderr


def test_ci_policy_rejects_malformed_yaml() -> None:
    # Given: a workflow with unclosed YAML sequences.
    with temporary_repository(REPOSITORY_ROOT) as repository:
        write_workflow(
            repository.root,
            valid_workflow()
            .replace("on: [push]", "on: [push")
            .replace("jobs:", "jobs: ["),
        )

        # When: the policy gate parses the document.
        result = run_policy(repository.root)

    # Then: invalid YAML cannot receive a successful policy result.
    assert result.returncode != 0
    assert "invalid YAML" in result.stderr


def test_ci_policy_rejects_mutable_reusable_workflow() -> None:
    # Given: a job that calls a reusable workflow through a mutable branch.
    with temporary_repository(REPOSITORY_ROOT) as repository:
        write_workflow(
            repository.root,
            "\n".join(
                (
                    "name: CI",
                    "on: [push]",
                    "permissions:",
                    "  contents: read",
                    "jobs:",
                    "  validate:",
                    "    uses: example/repo/.github/workflows/ci.yml@main",
                    "",
                )
            ),
        )

        # When: the policy gate validates the reusable workflow job.
        result = run_policy(repository.root)

    # Then: a branch reference cannot execute as a workflow dependency.
    assert result.returncode != 0
    assert "reusable workflow must use an immutable action reference" in result.stderr


def test_ci_policy_rejects_scalar_step() -> None:
    # Given: a job containing a scalar rather than a step mapping.
    with temporary_repository(REPOSITORY_ROOT) as repository:
        write_workflow(
            repository.root,
            valid_workflow().replace(
                "      - uses:", "      - 'run: echo invalid scalar'\n      # uses:"
            ),
        )

        # When: the policy gate validates every step shape.
        result = run_policy(repository.root)

    # Then: malformed steps cannot be ignored.
    assert result.returncode != 0
    assert "step must be a mapping" in result.stderr
