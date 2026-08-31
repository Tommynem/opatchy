from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

SHA_LENGTH: Final = 40


@dataclass(frozen=True, slots=True)
class PolicyViolation:
    path: Path
    message: str


def parse_repository(arguments: tuple[str, ...]) -> Path:
    if len(arguments) != 2 or arguments[0] != "--repository":
        raise SystemExit("Usage: ci_policy.py --repository /absolute/path")
    repository = Path(arguments[1]).resolve()
    if not repository.is_dir():
        raise SystemExit(f"ERROR(ci-policy): repository is unavailable: {repository}")
    return repository


def scalar(node: Node | None) -> str | None:
    return cast(str, node.value) if isinstance(node, ScalarNode) else None


def mapping(node: Node | None) -> dict[str, Node] | None:
    if not isinstance(node, MappingNode):
        return None
    values: dict[str, Node] = {}
    for key_node, value_node in cast(list[tuple[Node, Node]], node.value):
        key = scalar(key_node)
        if key is None or key in values:
            return None
        values[key] = value_node
    return values


def immutable_action(reference: str | None) -> bool:
    if reference is None:
        return False
    action, separator, revision = reference.partition("@")
    return bool(
        action
        and separator
        and len(revision) == SHA_LENGTH
        and all(character in "0123456789abcdef" for character in revision)
    )


def read_yaml(path: Path) -> Node | None:
    loader = yaml.SafeLoader(path.read_text(encoding="utf-8"))
    try:
        return loader.get_single_node()
    except yaml.YAMLError:
        return None


def workflow_violations(path: Path) -> tuple[PolicyViolation, ...]:
    document = read_yaml(path)
    document_map = mapping(document)
    if document is None or document_map is None:
        return (PolicyViolation(path, "invalid YAML"),)
    violations: list[PolicyViolation] = []
    permissions = document_map.get("permissions")
    if not permission_is_read_only(permissions):
        violations.append(
            PolicyViolation(path, "permissions must be exactly contents: read")
        )
    triggers = document_map.get("on")
    if trigger_contains_pull_request_target(triggers):
        violations.append(PolicyViolation(path, "pull_request_target is prohibited"))
    jobs = mapping(document_map.get("jobs"))
    if jobs is None:
        return (*violations, PolicyViolation(path, "jobs must be a mapping"))
    for job in jobs.values():
        violations.extend(job_violations(path, job))
    return tuple(violations)


def permission_is_read_only(node: Node | None) -> bool:
    permissions = mapping(node)
    return (
        permissions is not None
        and set(permissions) == {"contents"}
        and scalar(permissions["contents"]) == "read"
    )


def trigger_contains_pull_request_target(node: Node | None) -> bool:
    trigger = scalar(node)
    if trigger == "pull_request_target":
        return True
    if isinstance(node, SequenceNode):
        return any(
            scalar(item) == "pull_request_target"
            for item in cast(list[Node], node.value)
        )
    triggers = mapping(node)
    return triggers is not None and "pull_request_target" in triggers


def job_violations(path: Path, node: Node) -> tuple[PolicyViolation, ...]:
    job = mapping(node)
    if job is None:
        return (PolicyViolation(path, "job must be a mapping"),)
    violations: list[PolicyViolation] = []
    if "permissions" in job and not permission_is_read_only(job["permissions"]):
        violations.append(
            PolicyViolation(path, "permissions must be exactly contents: read")
        )
    uses = job.get("uses")
    steps = job.get("steps")
    if uses is not None:
        if steps is not None or not immutable_action(scalar(uses)):
            violations.append(
                PolicyViolation(
                    path, "reusable workflow must use an immutable action reference"
                )
            )
        return tuple(violations)
    if not isinstance(steps, SequenceNode):
        return (*violations, PolicyViolation(path, "job steps must be a sequence"))
    for step in cast(list[Node], steps.value):
        step_map = mapping(step)
        if step_map is None:
            violations.append(PolicyViolation(path, "step must be a mapping"))
            continue
        if "uses" in step_map and not immutable_action(scalar(step_map["uses"])):
            violations.append(PolicyViolation(path, "mutable action reference"))
    return tuple(violations)


def main() -> int:
    repository = parse_repository(tuple(sys.argv[1:]))
    directory = repository / ".github" / "workflows"
    workflows = tuple(sorted((*directory.glob("*.yml"), *directory.glob("*.yaml"))))
    if not workflows:
        print("ERROR(ci-policy): no workflow files found", file=sys.stderr)
        return 1
    violations = tuple(item for path in workflows for item in workflow_violations(path))
    for violation in violations:
        print(
            f"ERROR(ci-policy): {violation.path.relative_to(repository)}: {violation.message}",
            file=sys.stderr,
        )
    if violations:
        return 1
    print("PASS(ci-policy)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
