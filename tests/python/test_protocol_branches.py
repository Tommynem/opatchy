import sys
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Final
from unittest.mock import patch

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
HELPER_ROOT: Final = REPOSITORY_ROOT / "helper"
sys.path.insert(0, str(HELPER_ROOT))

from opatchy_helper import cli
from opatchy_helper.json_value import decode_json
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
        SourceHealth(
            source, SourceStatus.OK, Provenance.LIVE, FIXED_TIME, FIXED_TIME, None
        )
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

    def assert_json_error(self, raw: str) -> None:
        with self.assertRaises(ProtocolError) as raised:
            _ = decode_json(raw)
        self.assertEqual(raised.exception.error.code, ErrorCode.MALFORMED_JSON)

    def test_json_value_parses_supported_scalar_container_and_escape_forms(
        self,
    ) -> None:
        value = decode_json(
            r'{"array":[true,false,null,0,-1,1.5,1e2],"escaped":"\"\\\/\b\f\n\r\t\u0061","emptyArray":[],"emptyObject":{}}'
        )

        self.assertEqual(
            value,
            {
                "array": [True, False, None, 0, -1, 1.5, 100.0],
                "escaped": '"\\/\b\f\n\r\ta',
                "emptyArray": [],
                "emptyObject": {},
            },
        )
        self.assertEqual(decode_json(r'"\u00af"'), "¯")

    def test_json_value_rejects_invalid_grammar_and_unicode_escapes(self) -> None:
        cases = (
            "",
            "0 1",
            "[1",
            "[1;",
            '{"a" 1}',
            '{"a":1',
            '{"a":1;',
            '"\\x"',
            '"\\u12G4"',
            '"\\uD83D"',
            '"\\uDE00"',
            '"\\uD83D\\u0041"',
            '"\\u123',
            '"unterminated',
            '"line\nbreak"',
            '"' + "\\",
        )

        for raw in cases:
            with self.subTest(raw=raw):
                self.assert_json_error(raw)

    def test_decoder_rejects_non_standard_json_constants_as_malformed(self) -> None:
        for raw in (b"NaN", b"Infinity", b"-Infinity"):
            with self.subTest(raw=raw):
                self.assert_decode_error(raw, ErrorCode.MALFORMED_JSON)

    def test_decoder_accepts_escaped_unicode_surrogate_pairs(self) -> None:
        raw = encode_response(valid_inventory()).replace(
            b'"label":"demo"', b'"label":"\\uD83D\\uDE00"'
        )

        response = decode_response(raw)

        match response:
            case InventoryResponse(payload=payload):
                self.assertEqual(payload.items[0].label, "😀")
            case _:
                self.fail("decoded response must be inventory")

    def test_decoder_rejects_duplicate_object_keys_as_malformed(self) -> None:
        self.assert_decode_error(
            b'{"protocolVersion":1,"protocolVersion":1}', ErrorCode.MALFORMED_JSON
        )

    def test_decoder_rejects_missing_fields_and_invalid_nested_shapes(self) -> None:
        inventory = encode_response(valid_inventory())
        snapshot = encode_response(valid_snapshot())
        error = encode_response(
            ErrorResponse(
                FIXED_TIME,
                GenerationId("generation-error"),
                ErrorInfo(ErrorCode.CLI_USAGE, "message"),
            )
        )
        cases = (
            (b"[]", ErrorCode.INVALID_TYPE),
            (b'{"protocolVersion":1}', ErrorCode.MISSING_FIELD),
            (
                inventory.replace(b'"protocolVersion":1', b'"protocolVersion":0'),
                ErrorCode.PROTOCOL_VERSION_INVALID,
            ),
            (
                inventory.replace(
                    b"2026-08-25T12:34:56.000000Z", b"2026-02-31T12:34:56.000000Z"
                ),
                ErrorCode.INVALID_TIMESTAMP,
            ),
            (
                inventory.replace(
                    b'"generationId":"generation-inventory"', b'"generationId":1'
                ),
                ErrorCode.INVALID_TYPE,
            ),
            (
                inventory.replace(b'"watchable":true', b'"watchable":1'),
                ErrorCode.INVALID_TYPE,
            ),
            (
                snapshot.replace(b'"notifications":[]', b'"notifications":{}'),
                ErrorCode.INVALID_TYPE,
            ),
            (
                inventory.replace(
                    b'"kind":"inventory"',
                    b'"error":{"code":"CLI_USAGE","message":"x"},"kind":"inventory"',
                ),
                ErrorCode.INVALID_ENVELOPE,
            ),
            (
                error.replace(
                    b'"message":"message"', b'"message":"' + b"x" * 513 + b'"'
                ),
                ErrorCode.INVALID_TYPE,
            ),
        )

        for raw, code in cases:
            with self.subTest(code=code):
                self.assert_decode_error(raw, code)

    def test_nested_snapshot_values_round_trip_and_timestamp_policy_rejects_non_utc(
        self,
    ) -> None:
        response = valid_snapshot()
        source = replace(
            response.payload.sources[0], cause=ErrorInfo(ErrorCode.CLI_USAGE, "cause")
        )
        payload = replace(
            response.payload,
            sources=(source, *response.payload.sources[1:]),
            notifications=(
                NotificationOutcome(
                    NotificationFingerprint("notification"),
                    NotificationStatus.DELIVERED,
                ),
            ),
        )
        nested_response = replace(response, payload=payload)

        self.assertEqual(
            decode_response(encode_response(nested_response)), nested_response
        )
        self.assert_encode_error(
            replace(valid_inventory(), generated_at=FIXED_TIME.replace(tzinfo=None)),
            ErrorCode.INVALID_TIMESTAMP,
        )
        self.assert_encode_error(
            replace(
                valid_inventory(),
                generated_at=datetime(2026, 8, 25, tzinfo=timezone(timedelta(hours=1))),
            ),
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
            (
                replace(inventory, protocol_version=ProtocolVersion(0)),
                ErrorCode.PROTOCOL_VERSION_INVALID,
            ),
            (
                replace(inventory, payload=replace(inventory.payload, total=2)),
                ErrorCode.INVALID_ENVELOPE,
            ),
            (
                replace(
                    inventory,
                    payload=replace(
                        inventory.payload,
                        items=(replace(valid_item(), source=ItemSource.AUR),),
                    ),
                ),
                ErrorCode.INVALID_ENVELOPE,
            ),
            (
                replace(snapshot, payload=replace(snapshot.payload, sources=())),
                ErrorCode.INVALID_ENVELOPE,
            ),
            (
                replace(
                    snapshot,
                    payload=replace(snapshot.payload, items=(replace(item, label=""),)),
                ),
                ErrorCode.INVALID_TYPE,
            ),
            (
                replace(
                    snapshot, payload=replace(snapshot.payload, findings=(group, group))
                ),
                ErrorCode.INVALID_ENVELOPE,
            ),
            (
                replace(
                    snapshot, payload=replace(snapshot.payload, items=(non_arch_item,))
                ),
                ErrorCode.INVALID_ENVELOPE,
            ),
            (
                replace(
                    snapshot,
                    payload=replace(
                        snapshot.payload, findings=(replace(group, findings=()),)
                    ),
                ),
                ErrorCode.INVALID_ENVELOPE,
            ),
            (
                replace(
                    snapshot,
                    payload=replace(
                        snapshot.payload,
                        findings=(
                            replace(
                                group,
                                findings=(
                                    replace(finding, item_id=ItemId("arch:other")),
                                ),
                            ),
                        ),
                    ),
                ),
                ErrorCode.INVALID_ENVELOPE,
            ),
            (
                replace(
                    snapshot,
                    payload=replace(
                        snapshot.payload,
                        summary=replace(snapshot.payload.summary, total_updates=-1),
                    ),
                ),
                ErrorCode.INVALID_TYPE,
            ),
        )

        for response, code in invalid:
            with self.subTest(code=code):
                self.assert_encode_error(response, code)

    def test_encoder_rejects_boolean_numeric_fields_and_invalid_error_messages(
        self,
    ) -> None:
        snapshot = valid_snapshot()
        invalid_cause = replace(
            snapshot.payload.sources[0], cause=ErrorInfo(ErrorCode.CLI_USAGE, "")
        )
        invalid_snapshot = replace(
            snapshot,
            payload=replace(
                snapshot.payload, sources=(invalid_cause, *snapshot.payload.sources[1:])
            ),
        )
        invalid = (
            (
                replace(valid_inventory(), protocol_version=ProtocolVersion(True)),
                ErrorCode.PROTOCOL_VERSION_INVALID,
            ),
            (
                replace(
                    valid_inventory(),
                    payload=replace(valid_inventory().payload, total=True),
                ),
                ErrorCode.INVALID_TYPE,
            ),
            (
                ErrorResponse(
                    FIXED_TIME,
                    GenerationId("empty-error"),
                    ErrorInfo(ErrorCode.CLI_USAGE, ""),
                ),
                ErrorCode.INVALID_TYPE,
            ),
            (
                ErrorResponse(
                    FIXED_TIME,
                    GenerationId("long-error"),
                    ErrorInfo(ErrorCode.CLI_USAGE, "x" * 513),
                ),
                ErrorCode.INVALID_TYPE,
            ),
            (invalid_snapshot, ErrorCode.INVALID_TYPE),
        )

        for response, code in invalid:
            with self.subTest(code=code):
                self.assert_encode_error(response, code)

    def test_decoder_rejects_excessive_json_nesting_with_a_protocol_error(self) -> None:
        self.assert_decode_error(b"[" * 1200 + b"]" * 1200, ErrorCode.MALFORMED_JSON)

    def test_cli_dispatch_covers_valid_and_invalid_argument_forms(self) -> None:
        commands = (
            (("snapshot",), ErrorCode.STATE_UNAVAILABLE),
            (("scan",), ErrorCode.STATE_UNAVAILABLE),
            (("scan", "--force"), ErrorCode.STATE_UNAVAILABLE),
            (
                (
                    "inventory",
                    "--source",
                    "arch",
                    "--query",
                    "demo",
                    "--limit",
                    "1",
                    "--offset",
                    "0",
                ),
                ErrorCode.STATE_UNAVAILABLE,
            ),
            (
                (
                    "inventory",
                    "--source",
                    "aur",
                    "--query",
                    "demo",
                    "--limit",
                    "0",
                    "--offset",
                    "0",
                ),
                ErrorCode.CLI_USAGE,
            ),
            (
                (
                    "inventory",
                    "--source",
                    "flatpak",
                    "--query",
                    "demo",
                    "--limit",
                    "101",
                    "--offset",
                    "0",
                ),
                ErrorCode.CLI_USAGE,
            ),
            (
                (
                    "inventory",
                    "--source",
                    "mise",
                    "--query",
                    "demo",
                    "--limit",
                    "1",
                    "--offset",
                    "invalid",
                ),
                ErrorCode.CLI_USAGE,
            ),
            (
                (
                    "inventory",
                    "--source",
                    "unknown",
                    "--query",
                    "demo",
                    "--limit",
                    "1",
                    "--offset",
                    "0",
                ),
                ErrorCode.CLI_USAGE,
            ),
            (
                ("set-star", "--item-id", "arch:demo", "--mode", "off"),
                ErrorCode.STATE_UNAVAILABLE,
            ),
            (
                ("set-star", "--item-id", "arch:demo", "--mode", "temporary"),
                ErrorCode.STATE_UNAVAILABLE,
            ),
            (
                ("set-star", "--item-id", "arch:demo", "--mode", "permanent"),
                ErrorCode.STATE_UNAVAILABLE,
            ),
            (("set-star", "--item-id", "", "--mode", "off"), ErrorCode.CLI_USAGE),
            (
                ("set-star", "--item-id", "x" * 129, "--mode", "off"),
                ErrorCode.CLI_USAGE,
            ),
            (
                ("set-star", "--item-id", "arch:demo", "--mode", "unknown"),
                ErrorCode.CLI_USAGE,
            ),
            (("unknown",), ErrorCode.CLI_USAGE),
        )

        for arguments, code in commands:
            with self.subTest(arguments=arguments):
                stdout = CapturedStandardOutput()
                with patch.object(sys, "stdout", stdout):
                    self.assertEqual(cli.main(arguments), cli.EXIT_ERROR)
                self.assertIn(f'"code":"{code}"'.encode(), stdout.buffer.getvalue())
