from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

SHA: Final = re.compile(r"^[0-9a-f]{40}$")
USES: Final = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)
WORKFLOW_PERMISSION: Final = re.compile(
    r"^permissions:\s*\n\s+contents:\s*read\s*$", re.MULTILINE
)


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


def workflow_violations(path: Path) -> tuple[PolicyViolation, ...]:
    text = path.read_text(encoding="utf-8")
    violations: list[PolicyViolation] = []
    if not WORKFLOW_PERMISSION.search(text):
        violations.append(
            PolicyViolation(path, "permissions must be exactly contents: read")
        )
    if "pull_request_target" in text:
        violations.append(PolicyViolation(path, "pull_request_target is prohibited"))
    for match in USES.finditer(text):
        reference = match.group(1)
        action, separator, revision = reference.partition("@")
        if not separator or not action or not SHA.fullmatch(revision):
            violations.append(
                PolicyViolation(path, f"mutable action reference: {reference}")
            )
    return tuple(violations)


def main() -> int:
    repository = parse_repository(tuple(sys.argv[1:]))
    workflows = tuple(sorted((repository / ".github" / "workflows").glob("*.yml")))
    if not workflows:
        print("ERROR(ci-policy): no workflow files found", file=sys.stderr)
        return 1
    violations = tuple(
        violation
        for workflow in workflows
        for violation in workflow_violations(workflow)
    )
    if violations:
        for violation in violations:
            print(
                f"ERROR(ci-policy): {violation.path.relative_to(repository)}: {violation.message}",
                file=sys.stderr,
            )
        return 1
    print("PASS(ci-policy)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
