from pathlib import Path

import pytest

from scripts.publication_model import (
    BacklogError,
    ExistingIssue,
    compare_issue_sets,
    parse_backlog,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
COMMITTED_SLUGS = frozenset(
    {
        "fwupd-firmware-inventory",
        "podman-container-digests",
        "lockfile-sbom-osv-adapters",
        "arch-news-release-note-gates",
        "maintenance-windows-reminders",
        "post-update-analysis",
        "deterministic-impact-labels",
        "aur-local-trust-context",
        "scan-history",
        "battery-metered-scheduling",
        "sanitized-support-bundle",
        "project-local-mise-discovery",
        "named-flatpak-installations",
        "assistive-technology-research",
        "verified-sha-installation-trust",
    }
)


BACKLOG = """# Roadmap

<!-- opatchy-roadmap: firmware-inventory -->
## Firmware inventory and handoff

## Value
Protect firmware updates with visible inventory and an explicit handoff.

## Scope
Read-only discovery and a fixed native handoff.

## Safety constraints
No flashing, privilege escalation, automatic update, or unattended action.

## Dependencies
fwupd and an approved host workflow.

## Acceptance criteria
Validated inventory and a disabled state when capability is absent.

## Non-goals
Firmware mutation or rollback.

## Labels
enhancement, roadmap
<!-- /opatchy-roadmap -->
"""


def test_parse_backlog_returns_machine_identified_issue_when_entry_is_complete() -> (
    None
):
    # Given: one structurally complete deferred-feature entry.
    # When: the canonical backlog is parsed.
    items = parse_backlog(BACKLOG)

    # Then: the issue body retains its stable hidden slug marker.
    assert items[0].slug == "firmware-inventory"
    assert "<!-- opatchy-roadmap-slug: firmware-inventory -->" in items[0].issue_body


def test_parse_backlog_rejects_duplicate_slug_when_entries_repeat() -> None:
    # Given: two entries that claim the same permanent issue identity.
    duplicate = BACKLOG + BACKLOG

    # When: the canonical backlog is parsed.
    # Then: duplicate issue creation is rejected before command planning.
    with pytest.raises(BacklogError):
        _ = parse_backlog(duplicate)


def test_compare_issue_sets_reports_missing_duplicate_and_unexpected_slugs() -> None:
    # Given: one expected issue and three malformed remote issue identities.
    expected = parse_backlog(BACKLOG)
    existing = (
        ExistingIssue(
            "firmware-inventory",
            "https://example.invalid/1",
            frozenset({"roadmap", "enhancement"}),
        ),
        ExistingIssue(
            "firmware-inventory",
            "https://example.invalid/2",
            frozenset({"roadmap", "enhancement"}),
        ),
        ExistingIssue(
            "unapproved-feature",
            "https://example.invalid/3",
            frozenset({"roadmap", "enhancement"}),
        ),
    )

    # When: the seeder compares exact stable issue identities.
    result = compare_issue_sets(expected, existing)

    # Then: duplicates and non-roadmap content prevent side effects.
    assert result.duplicate == frozenset({"firmware-inventory"})
    assert result.unexpected == frozenset({"unapproved-feature"})


def test_committed_backlog_has_exactly_the_approved_deferred_feature_slugs() -> None:
    # Given: the committed public roadmap source.
    roadmap = (REPOSITORY_ROOT / "docs/backlog.md").read_text(encoding="utf-8")

    # When: its issue entries are parsed.
    items = parse_backlog(roadmap)

    # Then: it seeds the exact approved scope, once per stable identity.
    assert frozenset(item.slug for item in items) == COMMITTED_SLUGS
    assert len(items) == 15
