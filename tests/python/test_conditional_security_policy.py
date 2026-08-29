from dataclasses import replace

import pytest
from opatchy_helper.cli_requests import ScanCommand, parse_command
from opatchy_helper.models import (
    ArchStatus,
    FindingId,
    ItemId,
    Provenance,
    SecurityFinding,
    SecurityFindingGroup,
    Severity,
)
from opatchy_helper.notification_types import NotificationSettings
from opatchy_helper.notifications import notification_candidates
from opatchy_helper.runner_types import CommandExited, CommandSucceeded
from opatchy_helper.storage_types import PersistentState

from tests.python.conditional_security_support import NOW, snapshot, versions, watch


@pytest.mark.parametrize(
    ("candidate", "result", "expected_kinds"),
    (
        (None, CommandSucceeded(b"1\n", b""), ()),
        ("1.9", CommandSucceeded(b"-1\n", b""), ()),
        ("2.0", CommandSucceeded(b"0\n", b""), ("security-condition",)),
        ("2.1", CommandSucceeded(b"1\n", b""), ("security-condition",)),
        ("2.1", CommandSucceeded(b"bad\n", b""), ()),
        ("2.1", CommandExited(1, b"", b""), ()),
    ),
)
def test_conditional_security_policy_owns_matching_finding_before_candidate_eligibility(
    candidate: str | None,
    result: CommandSucceeded | CommandExited,
    expected_kinds: tuple[str, ...],
) -> None:
    candidates = notification_candidates(
        PersistentState((watch(),), (), ()),
        snapshot(candidate=candidate),
        NOW,
        NotificationSettings(),
        versions(result),
    )
    assert tuple(item.kind.value for item in candidates) == expected_kinds


@pytest.mark.parametrize(
    ("arch_provenance", "security_provenance", "item_provenance", "finding_provenance"),
    (
        (Provenance.CACHE, Provenance.LIVE, Provenance.LIVE, Provenance.LIVE),
        (Provenance.LIVE, Provenance.FALLBACK, Provenance.LIVE, Provenance.LIVE),
        (Provenance.LIVE, Provenance.LIVE, Provenance.CACHE, Provenance.LIVE),
        (Provenance.LIVE, Provenance.LIVE, Provenance.LIVE, Provenance.FALLBACK),
    ),
)
def test_conditional_security_requires_live_arch_source_and_candidate_evidence(
    arch_provenance: Provenance,
    security_provenance: Provenance,
    item_provenance: Provenance,
    finding_provenance: Provenance,
) -> None:
    candidates = notification_candidates(
        PersistentState((watch(),), (), ()),
        snapshot(
            arch_provenance=arch_provenance,
            security_provenance=security_provenance,
            item_provenance=item_provenance,
            finding_provenance=finding_provenance,
        ),
        NOW,
        NotificationSettings(),
        versions(CommandSucceeded(b"0\n", b"")),
    )
    assert tuple(candidate.kind.value for candidate in candidates) == ()


def test_matching_conditional_watch_owns_its_generic_security_finding() -> None:
    candidates = notification_candidates(
        PersistentState((watch(),), (), ()),
        snapshot(),
        NOW,
        NotificationSettings(),
        versions(CommandSucceeded(b"0\n", b"")),
    )
    assert tuple(candidate.kind.value for candidate in candidates) == (
        "security-condition",
    )


@pytest.mark.parametrize(
    ("finding_id", "item_id", "advisory_id", "cve_ids", "fixed_version"),
    (
        (
            "arch:demo:AVG-20260002",
            "arch:demo",
            "AVG-20260002",
            ("CVE-2026-54321",),
            "2.0",
        ),
        (
            "arch:demo:AVG-20260001:other-fixed",
            "arch:demo",
            "AVG-20260001",
            ("CVE-2026-12345",),
            "2.1",
        ),
        (
            "arch:demo:AVG-20260001:other-cve",
            "arch:demo",
            "AVG-20260001",
            ("CVE-2026-54321",),
            "2.0",
        ),
    ),
)
def test_unmatched_finding_retains_its_generic_security_candidate(
    finding_id: str,
    item_id: str,
    advisory_id: str,
    cve_ids: tuple[str, ...],
    fixed_version: str,
) -> None:
    response = snapshot()
    unrelated = SecurityFinding(
        FindingId(finding_id),
        ItemId(item_id),
        advisory_id,
        cve_ids,
        Severity.HIGH,
        fixed_version,
        False,
        Provenance.LIVE,
        ArchStatus.FIXED,
    )
    response = replace(
        response,
        payload=replace(
            response.payload,
            findings=(
                SecurityFindingGroup(
                    ItemId("arch:demo"),
                    (*response.payload.findings[0].findings, unrelated),
                ),
            ),
        ),
    )
    candidates = notification_candidates(
        PersistentState((watch(),), (), ()),
        response,
        NOW,
        NotificationSettings(),
        versions(CommandSucceeded(b"0\n", b"")),
    )
    assert tuple(candidate.kind.value for candidate in candidates) == (
        "security",
        "security-condition",
    )


def test_scan_command_parses_typed_notification_settings() -> None:
    command = parse_command(
        (
            "scan",
            "--notify-permanent",
            "false",
            "--notify-security",
            "true",
            "--security-minimum-severity",
            "critical",
        )
    )
    assert command == ScanCommand(
        False, NotificationSettings(False, True, Severity.CRITICAL)
    )


@pytest.mark.parametrize("arch_stale,security_stale", ((True, False), (False, True)))
def test_conditional_security_policy_rejects_stale_arch_or_security_evidence(
    arch_stale: bool, security_stale: bool
) -> None:
    candidates = notification_candidates(
        PersistentState((watch(),), (), ()),
        snapshot(arch_stale=arch_stale, security_stale=security_stale),
        NOW,
        NotificationSettings(),
        versions(CommandSucceeded(b"0\n", b"")),
    )
    assert tuple(item.kind.value for item in candidates) == ()


def test_conditional_security_policy_rejects_aur_collision() -> None:
    candidates = notification_candidates(
        PersistentState((watch(),), (), ()),
        snapshot(item_id="aur:demo"),
        NOW,
        NotificationSettings(),
        versions(CommandSucceeded(b"0\n", b"")),
    )
    assert all(item.kind.value != "security-condition" for item in candidates)
