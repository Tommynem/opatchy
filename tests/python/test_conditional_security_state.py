import pytest
from opatchy_helper.cli_requests import CliUsageError, SetStarCommand, parse_command
from opatchy_helper.models import ItemId, WatchMode
from opatchy_helper.storage_state import decode_state, encode_state
from opatchy_helper.storage_types import StateCorruptError, StateSchemaIncompatible

from tests.python.conditional_security_support import CONDITION, NOW


def test_v1_state_migrates_to_conditionless_v2_without_losing_ordinary_watch() -> None:
    raw = b'{"schemaVersion":1,"watches":[{"itemId":"arch:demo","mode":"temporary","installedFingerprint":"installed","candidateFingerprint":"candidate","armed":true}],"ledger":[],"sources":[]}'
    migrated = decode_state(raw)
    encoded = encode_state(migrated, NOW)
    assert migrated.watches[0].condition is None
    assert b'"schemaVersion":2' in encoded


@pytest.mark.parametrize(
    "raw",
    (
        b'{"schemaVersion":2,"watches":[{"itemId":"arch:demo","mode":"temporary","installedFingerprint":"installed","candidateFingerprint":"candidate","armed":true,"condition":{"advisoryId":"bad","cveIds":[],"fixedVersion":"2.0"}}],"ledger":[],"sources":[]}',
        b'{"schemaVersion":2,"watches":[{"itemId":"arch:demo","mode":"temporary","installedFingerprint":"installed","candidateFingerprint":"candidate","armed":true,"condition":{"advisoryId":"AVG-20260001","cveIds":["CVE-2026-12345"],"fixedVersion":"2.0","future":"x"}}],"ledger":[],"sources":[]}',
        b'{"schemaVersion":3,"watches":[],"ledger":[],"sources":[]}',
    ),
)
def test_condition_state_rejects_malformed_or_unknown_future_values(raw: bytes) -> None:
    with pytest.raises((StateCorruptError, StateSchemaIncompatible)):
        _ = decode_state(raw)


def test_set_star_condition_contract_preserves_existing_response_and_identity() -> None:
    ordinary = parse_command(
        ("set-star", "--item-id", "arch:demo", "--mode", "temporary")
    )
    conditional = parse_command(
        (
            "set-star",
            "--item-id",
            "arch:demo",
            "--mode",
            "temporary",
            "--security-advisory",
            "AVG-20260001",
            "--fixed-version",
            "2.0",
            "--cve-ids",
            "CVE-2026-12345",
        )
    )
    assert ordinary == SetStarCommand(ItemId("arch:demo"), WatchMode.TEMPORARY)
    assert conditional == SetStarCommand(
        ItemId("arch:demo"), WatchMode.TEMPORARY, CONDITION
    )
    with pytest.raises(CliUsageError):
        _ = parse_command(
            (
                "set-star",
                "--item-id",
                "aur:demo",
                "--mode",
                "temporary",
                "--security-advisory",
                "AVG-20260001",
                "--fixed-version",
                "2.0",
                "--cve-ids",
                "CVE-2026-12345",
            )
        )
