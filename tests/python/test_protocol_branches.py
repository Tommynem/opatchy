from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import sys
from typing import Final
import unittest
from unittest.mock import patch


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
HELPER_ROOT: Final = REPOSITORY_ROOT / "helper"
sys.path.insert(0, str(HELPER_ROOT))

from opatchy_helper import cli
from opatchy_helper.models import (
    ErrorCode,
    ErrorInfo,
    ErrorResponse,
    FindingId,
    GenerationId,
    InventoryPayload,
    InventoryResponse,
    ItemId,
    ItemSource,
    NormalizedItem,
    NotificationFingerprint,
    NotificationOutcome,
    NotificationStatus,
    ProtocolError,
    ProtocolVersion,
    Provenance,
    Response,
    ScanState,
    SecurityFinding,
    SecurityFindingGroup,
    Severity,
    SnapshotPayload,
    SnapshotResponse,
    SourceHealth,
    SourceName,
    SourceStatus,
    Summary,
    WatchMode,
)
from opatchy_helper.protocol import decode_response, encode_response, utc_now


FIXED_TIME: Final = datetime(2026, 8, 25, 12, 34, 56, tzinfo=timezone.utc)


class CapturedStandardOutput:
    def __init__(self) -> None:
        self.buffer: BytesIO = BytesIO()


def valid_item() -> NormalizedItem:
    return NormalizedItem(
        ItemId("arch:demo"),
        ItemSource.ARCH,
        "demo",
        "1.0",
        "1.1",
        WatchMode.OFF,
        True,
        Provenance.LIVE,
    )


def valid_inventory() -> InventoryResponse:
    return InventoryResponse(
        FIXED_TIME,
        GenerationId("generation-inventory"),
        InventoryPayload(ItemSource.ARCH, 1, (valid_item(),)),
    )


def valid_sources() -> tuple[SourceHealth, ...]:
    return tuple(
        SourceHealth(source, SourceStatus.OK, Provenance.LIVE, FIXED_TIME, FIXED_TIME, None)
        for source in SourceName
    )


def valid_snapshot() -> SnapshotResponse:
    item = valid_item()
    finding = SecurityFinding(
        FindingId("ASA-2026-001"),
        item.item_id,
        "ASA-2026-001",
        ("CVE-2026-0001",),
        Severity.HIGH,
        "1.1",
        False,
        Provenance.LIVE,
    )
    return SnapshotResponse(
        FIXED_TIME,
        GenerationId("generation-snapshot"),
        SnapshotPayload(
            ScanState.COMPLETE,
            valid_sources(),
            Summary(1, 0, 1, 0),
            (item,),
            (SecurityFindingGroup(item.item_id, (finding,)),),
            (),
        ),
    )


class ProtocolBranchTests(unittest.TestCase):
    def assert_decode_error(self, raw: bytes, code: ErrorCode) -> None:
        with self.assertRaises(ProtocolError) as raised:
            _ = decode_response(raw)
        self.assertEqual(raised.exception.error.code, code)

    def assert_encode_error(self, response: Response, code: ErrorCode) -> None:
        with self.assertRaises(ProtocolError) as raised:
            _ = encode_response(response)
        self.assertEqual(raised.exception.error.code, code)

    def test_decoder_normalizes_nonfinite_json_numbers_before_schema_validation(self) -> None:
        self.assert_decode_error(b"NaN", ErrorCode.INVALID_TYPE)

    def test_decoder_rejects_missing_fields_and_invalid_nested_shapes(self) -> None:
        inventory = encode_response(valid_inventory())
        snapshot = encode_response(valid_snapshot())
        error = encode_response(ErrorResponse(FIXED_TIME, GenerationId("generation-error"), ErrorInfo(ErrorCode.CLI_USAGE, "message")))
        cases = (
            (b"[]", ErrorCode.INVALID_TYPE),
            (b'{"protocolVersion":1}', ErrorCode.MISSING_FIELD),
            (inventory.replace(b'"protocolVersion":1', b'"protocolVersion":0'), ErrorCode.PROTOCOL_VERSION_INVALID),
            (inventory.replace(b"2026-08-25T12:34:56.000000Z", b"2026-02-31T12:34:56.000000Z"), ErrorCode.INVALID_TIMESTAMP),
            (inventory.replace(b'"generationId":"generation-inventory"', b'"generationId":1'), ErrorCode.INVALID_TYPE),
            (inventory.replace(b'"watchable":true', b'"watchable":1'), ErrorCode.INVALID_TYPE),
            (snapshot.replace(b'"notifications":[]', b'"notifications":{}'), ErrorCode.INVALID_TYPE),
            (inventory.replace(b'"kind":"inventory"', b'"error":{"code":"CLI_USAGE","message":"x"},"kind":"inventory"'), ErrorCode.INVALID_ENVELOPE),
            (error.replace(b'"message":"message"', b'"message":"' + b"x" * 513 + b'"'), ErrorCode.INVALID_TYPE),
        )

        for raw, code in cases:
            with self.subTest(code=code):
                self.assert_decode_error(raw, code)

    def test_nested_snapshot_values_round_trip_and_timestamp_policy_rejects_non_utc(self) -> None:
        response = valid_snapshot()
        source = replace(response.payload.sources[0], cause=ErrorInfo(ErrorCode.CLI_USAGE, "cause"))
        payload = replace(
            response.payload,
            sources=(source, *response.payload.sources[1:]),
            notifications=(NotificationOutcome(NotificationFingerprint("notification"), NotificationStatus.DELIVERED),),
        )
        nested_response = replace(response, payload=payload)

        self.assertEqual(decode_response(encode_response(nested_response)), nested_response)
        self.assert_encode_error(replace(valid_inventory(), generated_at=datetime(2026, 8, 25)), ErrorCode.INVALID_TIMESTAMP)
        self.assert_encode_error(
            replace(valid_inventory(), generated_at=datetime(2026, 8, 25, tzinfo=timezone(timedelta(hours=1)))),
            ErrorCode.INVALID_TIMESTAMP,
        )
        self.assertEqual(utc_now().utcoffset(), timedelta())

    def test_encoder_rejects_invalid_inventory_and_snapshot_graphs(self) -> None:
        inventory = valid_inventory()
        snapshot = valid_snapshot()
        item = snapshot.payload.items[0]
        group = snapshot.payload.findings[0]
        finding = group.findings[0]
        non_arch_item = replace(item, source=ItemSource.AUR)
        invalid = (
            (replace(inventory, protocol_version=ProtocolVersion(0)), ErrorCode.PROTOCOL_VERSION_INVALID),
            (replace(inventory, payload=replace(inventory.payload, total=2)), ErrorCode.INVALID_ENVELOPE),
            (replace(inventory, payload=replace(inventory.payload, items=(replace(valid_item(), source=ItemSource.AUR),))), ErrorCode.INVALID_ENVELOPE),
            (replace(snapshot, payload=replace(snapshot.payload, sources=())), ErrorCode.INVALID_ENVELOPE),
            (replace(snapshot, payload=replace(snapshot.payload, items=(replace(item, label=""),))), ErrorCode.INVALID_TYPE),
            (replace(snapshot, payload=replace(snapshot.payload, findings=(group, group))), ErrorCode.INVALID_ENVELOPE),
            (replace(snapshot, payload=replace(snapshot.payload, items=(non_arch_item,))), ErrorCode.INVALID_ENVELOPE),
            (replace(snapshot, payload=replace(snapshot.payload, findings=(replace(group, findings=()),))), ErrorCode.INVALID_ENVELOPE),
            (replace(snapshot, payload=replace(snapshot.payload, findings=(replace(group, findings=(replace(finding, item_id=ItemId("arch:other")),)),))), ErrorCode.INVALID_ENVELOPE),
            (replace(snapshot, payload=replace(snapshot.payload, summary=replace(snapshot.payload.summary, total_updates=-1))), ErrorCode.INVALID_TYPE),
        )

        for response, code in invalid:
            with self.subTest(code=code):
                self.assert_encode_error(response, code)

    def test_cli_dispatch_covers_valid_and_invalid_argument_forms(self) -> None:
        commands = (
            (("snapshot",), ErrorCode.STATE_UNAVAILABLE),
            (("scan",), ErrorCode.STATE_UNAVAILABLE),
            (("scan", "--force"), ErrorCode.STATE_UNAVAILABLE),
            (("inventory", "--source", "arch", "--query", "demo", "--limit", "1", "--offset", "0"), ErrorCode.STATE_UNAVAILABLE),
            (("inventory", "--source", "aur", "--query", "demo", "--limit", "0", "--offset", "0"), ErrorCode.CLI_USAGE),
            (("inventory", "--source", "flatpak", "--query", "demo", "--limit", "101", "--offset", "0"), ErrorCode.CLI_USAGE),
            (("inventory", "--source", "mise", "--query", "demo", "--limit", "1", "--offset", "invalid"), ErrorCode.CLI_USAGE),
            (("inventory", "--source", "unknown", "--query", "demo", "--limit", "1", "--offset", "0"), ErrorCode.CLI_USAGE),
            (("set-star", "--item-id", "arch:demo", "--mode", "off"), ErrorCode.STATE_UNAVAILABLE),
            (("set-star", "--item-id", "arch:demo", "--mode", "temporary"), ErrorCode.STATE_UNAVAILABLE),
            (("set-star", "--item-id", "arch:demo", "--mode", "permanent"), ErrorCode.STATE_UNAVAILABLE),
            (("set-star", "--item-id", "", "--mode", "off"), ErrorCode.CLI_USAGE),
            (("set-star", "--item-id", "x" * 129, "--mode", "off"), ErrorCode.CLI_USAGE),
            (("set-star", "--item-id", "arch:demo", "--mode", "unknown"), ErrorCode.CLI_USAGE),
            (("unknown",), ErrorCode.CLI_USAGE),
        )

        for arguments, code in commands:
            with self.subTest(arguments=arguments):
                stdout = CapturedStandardOutput()
                with patch.object(sys, "stdout", stdout):
                    self.assertEqual(cli.main(arguments), cli.EXIT_ERROR)
                self.assertIn(f'"code":"{code}"'.encode(), stdout.buffer.getvalue())
