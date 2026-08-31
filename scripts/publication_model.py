from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Final, TypeAlias, cast, override

JsonValue: TypeAlias = (
    bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"] | None
)
ENTRY_PATTERN: Final = re.compile(
    r"<!-- opatchy-roadmap: (?P<slug>[a-z0-9-]+) -->\n"
    + r"## (?P<title>[^\n]+)\n(?P<body>.*?)<!-- /opatchy-roadmap -->",
    re.DOTALL,
)
SLUG_PATTERN: Final = re.compile(r"<!-- opatchy-roadmap-slug: ([a-z0-9-]+) -->")
REQUIRED_SECTIONS: Final = (
    "Value",
    "Scope",
    "Safety constraints",
    "Dependencies",
    "Acceptance criteria",
    "Non-goals",
    "Labels",
)
REQUIRED_LABELS: Final = frozenset({"enhancement", "roadmap"})


@dataclass(frozen=True, slots=True)
class BacklogError(Exception):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class RoadmapItem:
    slug: str
    title: str
    issue_body: str
    labels: frozenset[str]


@dataclass(frozen=True, slots=True)
class ExistingIssue:
    slug: str
    url: str
    labels: frozenset[str]


@dataclass(frozen=True, slots=True)
class IssueSetComparison:
    missing: frozenset[str]
    unexpected: frozenset[str]
    duplicate: frozenset[str]
    missing_labels: frozenset[str]

    @property
    def can_seed(self) -> bool:
        return not self.unexpected and not self.duplicate and not self.missing_labels


def parse_backlog(markdown: str) -> tuple[RoadmapItem, ...]:
    matches = tuple(ENTRY_PATTERN.finditer(markdown))
    if not matches:
        raise BacklogError("backlog has no roadmap entries")
    items = tuple(parse_entry(match) for match in matches)
    slugs = tuple(item.slug for item in items)
    duplicates = {slug for slug, count in Counter(slugs).items() if count > 1}
    if duplicates:
        raise BacklogError(
            f"backlog has duplicate slugs: {', '.join(sorted(duplicates))}"
        )
    return items


def parse_entry(match: re.Match[str]) -> RoadmapItem:
    slug = match.group("slug")
    title = match.group("title").strip()
    body = match.group("body").strip()
    if not title:
        raise BacklogError(f"roadmap entry {slug} has no title")
    missing_sections = tuple(
        section for section in REQUIRED_SECTIONS if f"## {section}\n" not in body
    )
    if missing_sections:
        raise BacklogError(
            f"roadmap entry {slug} misses: {', '.join(missing_sections)}"
        )
    labels = parse_labels(slug, body)
    marker = f"<!-- opatchy-roadmap-slug: {slug} -->"
    return RoadmapItem(
        slug, title, f"{marker}\n\n# [{slug}] {title}\n\n{body}\n", labels
    )


def parse_labels(slug: str, body: str) -> frozenset[str]:
    labels_match = re.search(r"## Labels\n([^\n]+)", body)
    if labels_match is None:
        raise BacklogError(f"roadmap entry {slug} has no labels")
    labels = frozenset(part.strip() for part in labels_match.group(1).split(","))
    if labels != REQUIRED_LABELS:
        raise BacklogError(
            f"roadmap entry {slug} must use roadmap and enhancement labels"
        )
    return labels


def parse_existing_issues(document: str) -> tuple[ExistingIssue, ...]:
    try:
        decoded = cast(JsonValue, json.loads(document))
    except json.JSONDecodeError as error:
        raise BacklogError("GitHub issue response is invalid JSON") from error
    match decoded:
        case list() as entries:
            return tuple(
                parse_existing_issue(entry) for entry in entries if is_roadmap(entry)
            )
        case _:
            raise BacklogError("GitHub issue response must be an array")


def is_roadmap(entry: JsonValue) -> bool:
    match entry:
        case {"body": str(body)}:
            return SLUG_PATTERN.search(body) is not None
        case _:
            raise BacklogError("GitHub issue response contains an invalid issue")


def parse_existing_issue(entry: JsonValue) -> ExistingIssue:
    match entry:
        case {"body": str(body), "url": str(url), "labels": list(labels)}:
            slug_match = SLUG_PATTERN.search(body)
            if slug_match is None:
                raise BacklogError("roadmap issue lacks its slug marker")
            return ExistingIssue(slug_match.group(1), url, parse_remote_labels(labels))
        case _:
            raise BacklogError("GitHub issue response contains an invalid issue")


def parse_remote_labels(labels: list[JsonValue]) -> frozenset[str]:
    names: set[str] = set()
    for label in labels:
        match label:
            case {"name": str(name)}:
                names.add(name)
            case _:
                raise BacklogError("GitHub issue response contains an invalid label")
    return frozenset(names)


def compare_issue_sets(
    expected: tuple[RoadmapItem, ...], existing: tuple[ExistingIssue, ...]
) -> IssueSetComparison:
    expected_slugs = frozenset(item.slug for item in expected)
    counts = Counter(item.slug for item in existing)
    existing_slugs = frozenset(counts)
    duplicate = frozenset(slug for slug, count in counts.items() if count > 1)
    missing_labels = frozenset(
        issue.slug for issue in existing if not REQUIRED_LABELS.issubset(issue.labels)
    )
    return IssueSetComparison(
        expected_slugs - existing_slugs,
        existing_slugs - expected_slugs,
        duplicate,
        missing_labels,
    )
