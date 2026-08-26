import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
HELPER_ENTRYPOINT: Final = REPOSITORY_ROOT / "helper" / "opatchy.py"
HELPER_ROOT: Final = REPOSITORY_ROOT / "helper"
sys.path.insert(0, str(HELPER_ROOT))

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
    KevStatus,
    NormalizedItem,
    ProtocolVersion,
    Provenance,
    ScanState,
    SecurityFinding,
    SecurityFindingGroup,
    Severity,
    SnapshotPayload,
    SnapshotResponse,
    SourceHealth,
    SourceName,
    SourceStatus,
    StarResultPayload,
    StarResultResponse,
    Summary,
    WatchMode,
)
from opatchy_helper.protocol import (
    MAX_PROTOCOL_BYTES,
    ProtocolError,
    decode_response,
    encode_response,
)

FIXED_TIME: Final = datetime(2026, 8, 25, 12, 34, 56, tzinfo=timezone.utc)
HOSTILE_LABEL: Final = (
    "$(touch /tmp/opatchy-injection-sentinel) https://example.invalid"
)


def sample_item(item_id: str = "arch:demo") -> NormalizedItem:
    return NormalizedItem(
        ItemId(item_id),
        ItemSource.ARCH,
        HOSTILE_LABEL,
        "1.0",
        "1.1",
        WatchMode.OFF,
        True,
        Provenance.LIVE,
    )


def inventory_response(item_id: str = "arch:demo") -> InventoryResponse:
    return InventoryResponse(
        FIXED_TIME,
        GenerationId("generation-0001"),
        InventoryPayload(ItemSource.ARCH, 1, (sample_item(item_id),)),
    )


def snapshot_response() -> SnapshotResponse:
    sources = tuple(
        SourceHealth(
            source,
            SourceStatus.OK,
            Provenance.LIVE,
            FIXED_TIME,
            FIXED_TIME,
            None,
        )
        for source in SourceName
    )
    item = sample_item()
    finding = SecurityFinding(
        FindingId("AVG-20260001"),
        item.item_id,
        "AVG-20260001",
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
            sources,
            Summary(1, 0, 1, 0),
            (item,),
            (SecurityFindingGroup(item.item_id, (finding,)),),
            (),
        ),
    )


class ProtocolCliTests(unittest.TestCase):
    def run_helper(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = os.environ.copy()
            environment["XDG_CACHE_HOME"] = temporary_directory
            environment["XDG_STATE_HOME"] = temporary_directory
            return subprocess.run(
                [sys.executable, str(HELPER_ENTRYPOINT), *arguments],
                check=False,
                capture_output=True,
                encoding="utf-8",
                env=environment,
            )

    def test_snapshot_emits_one_protocol_error_when_no_snapshot_exists(self) -> None:
        result = self.run_helper("snapshot")

        self.assertEqual(result.returncode, 2)
        self.assertTrue(
            result.stdout.startswith('{"error":{"code":"STATE_UNAVAILABLE"')
        )
        self.assertTrue(result.stdout.endswith("\n"))
        self.assertEqual(result.stdout.count("\n"), 1)
        self.assertEqual(result.stderr, "")

    def test_unknown_command_emits_one_protocol_error_without_traceback(self) -> None:
        result = self.run_helper("not-a-command")

        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stdout.startswith('{"error":{"code":"CLI_USAGE"'))
        self.assertTrue(result.stdout.endswith("\n"))
        self.assertEqual(result.stdout.count("\n"), 1)
        self.assertNotIn("Traceback", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def assert_decode_error(self, raw: bytes, code: ErrorCode) -> None:
        with self.assertRaises(ProtocolError) as raised:
            _ = decode_response(raw)
        self.assertEqual(raised.exception.error.code, code)

    def assert_encode_error(
        self,
        response: SnapshotResponse
        | InventoryResponse
        | StarResultResponse
        | ErrorResponse,
        code: ErrorCode,
    ) -> None:
        with self.assertRaises(ProtocolError) as raised:
            _ = encode_response(response)
        self.assertEqual(raised.exception.error.code, code)

    def test_inventory_round_trip_is_byte_stable_and_keeps_hostile_label_inert(
        self,
    ) -> None:
        sentinel = Path("/tmp/opatchy-injection-sentinel")
        sentinel.unlink(missing_ok=True)

        encoded = encode_response(inventory_response())

        self.assertEqual(
            encoded,
            b'{"generatedAt":"2026-08-25T12:34:56.000000Z","generationId":"generation-0001","kind":"inventory","payload":{"items":[{"candidate":"1.1","id":"arch:demo","installed":"1.0","label":"$(touch /tmp/opatchy-injection-sentinel) https://example.invalid","provenance":"live","source":"arch","watchArmed":false,"watchMode":"off","watchable":true}],"source":"arch","total":1},"protocolVersion":1}\n',
        )
        self.assertEqual(decode_response(encoded), inventory_response())
        self.assertFalse(sentinel.exists())

    def test_each_response_kind_round_trips_when_it_is_valid(self) -> None:
        responses = (
            snapshot_response(),
            inventory_response(),
            StarResultResponse(
                FIXED_TIME,
                GenerationId("generation-star"),
                StarResultPayload(ItemId("arch:demo"), WatchMode.PERMANENT, False),
            ),
            ErrorResponse(
                FIXED_TIME,
                GenerationId("generation-error"),
                ErrorInfo(
                    ErrorCode.CLI_USAGE, "unsupported helper command or arguments"
                ),
            ),
        )

        for response in responses:
            with self.subTest(response=response):
                self.assertEqual(decode_response(encode_response(response)), response)

    def test_star_result_rejects_armed_non_temporary_modes(self) -> None:
        for mode in (WatchMode.OFF, WatchMode.PERMANENT):
            response = StarResultResponse(
                FIXED_TIME,
                GenerationId("generation-star"),
                StarResultPayload(ItemId("arch:demo"), mode, True),
            )
            self.assert_encode_error(response, ErrorCode.INVALID_ENVELOPE)

    def test_duplicate_item_ids_are_rejected_when_inventory_is_decoded(self) -> None:
        item = b'{"candidate":"1.1","id":"arch:demo","installed":"1.0","label":"$(touch /tmp/opatchy-injection-sentinel) https://example.invalid","provenance":"live","source":"arch","watchArmed":false,"watchMode":"off","watchable":true}'
        raw = (
            encode_response(inventory_response())
            .replace(item, b",".join((item, item)))
            .replace(b'"total":1', b'"total":2')
        )

        self.assert_decode_error(raw, ErrorCode.DUPLICATE_ITEM_ID)

    def test_encoder_rejects_duplicate_inventory_item_ids(self) -> None:
        response = InventoryResponse(
            FIXED_TIME,
            GenerationId("generation-duplicate-output"),
            InventoryPayload(ItemSource.ARCH, 2, (sample_item(), sample_item())),
        )

        self.assert_encode_error(response, ErrorCode.DUPLICATE_ITEM_ID)

    def test_encoder_rejects_inventory_with_an_unsupported_source(self) -> None:
        response = InventoryResponse(
            FIXED_TIME,
            GenerationId("generation-unsupported-output"),
            InventoryPayload(ItemSource.OMARCHY, 1, (sample_item(),)),
        )

        self.assert_encode_error(response, ErrorCode.INVALID_ENVELOPE)

    def test_security_groups_must_attach_to_a_present_arch_item(self) -> None:
        response = snapshot_response()
        dangling_item_id = ItemId("aur:unrelated")
        dangling_finding = SecurityFinding(
            FindingId("AVG-20260002"),
            dangling_item_id,
            "AVG-20260002",
            (),
            Severity.HIGH,
            "1.1",
            False,
            Provenance.LIVE,
        )
        invalid_payload = SnapshotPayload(
            response.payload.scan_state,
            response.payload.sources,
            response.payload.summary,
            response.payload.items,
            (SecurityFindingGroup(dangling_item_id, (dangling_finding,)),),
            response.payload.notifications,
        )
        invalid_response = SnapshotResponse(
            response.generated_at,
            response.generation_id,
            invalid_payload,
            response.protocol_version,
        )

        self.assert_encode_error(invalid_response, ErrorCode.INVALID_ENVELOPE)

    def test_malformed_protocol_values_are_rejected_with_stable_codes(self) -> None:
        cases = (
            (b"{", ErrorCode.MALFORMED_JSON),
            (b"{}", ErrorCode.PROTOCOL_VERSION_MISSING),
            (b'{"protocolVersion":null}', ErrorCode.PROTOCOL_VERSION_INVALID),
            (b'{"protocolVersion":true}', ErrorCode.PROTOCOL_VERSION_INVALID),
            (b'{"protocolVersion":2}', ErrorCode.PROTOCOL_VERSION_FUTURE),
            (
                b'{"generatedAt":"2026-08-25 12:34:56Z","protocolVersion":1}',
                ErrorCode.INVALID_TIMESTAMP,
            ),
            (b'{"extra":0}', ErrorCode.UNKNOWN_FIELD),
            (
                b'{"generatedAt":"2026-08-25T12:34:56.000000Z","generationId":"generation-0001","kind":"unexpected","protocolVersion":1}',
                ErrorCode.UNKNOWN_ENUM,
            ),
            (
                b'{"generatedAt":"2026-08-25T12:34:56.000000Z","generationId":"generation-0001","kind":"inventory","payload":{"items":[],"source":"arch","total":true},"protocolVersion":1}',
                ErrorCode.INVALID_TYPE,
            ),
        )

        for raw, code in cases:
            with self.subTest(code=code):
                self.assert_decode_error(raw, code)

    def test_security_findings_require_avg_ids_unique_group_ids_and_consistent_kev(
        self,
    ) -> None:
        response = snapshot_response()
        group = response.payload.findings[0]
        finding = group.findings[0]
        invalid = (
            (
                replace(finding, finding_id=FindingId("ASA-2026-001")),
                ErrorCode.INVALID_TYPE,
            ),
            (
                replace(
                    finding,
                    known_exploited=False,
                    kev_status=KevStatus.LISTED,
                    kev_provenance=Provenance.LIVE,
                ),
                ErrorCode.INVALID_ENVELOPE,
            ),
            (
                replace(
                    finding,
                    known_exploited=True,
                    kev_status=KevStatus.NOT_LISTED,
                    kev_provenance=Provenance.CACHE,
                ),
                ErrorCode.INVALID_ENVELOPE,
            ),
            (
                replace(finding, known_exploited=True),
                ErrorCode.INVALID_ENVELOPE,
            ),
        )
        for invalid_finding, code in invalid:
            with self.subTest(code=code):
                invalid_group = SecurityFindingGroup(group.item_id, (invalid_finding,))
                payload = replace(response.payload, findings=(invalid_group,))
                self.assert_encode_error(replace(response, payload=payload), code)
        duplicate_group = SecurityFindingGroup(group.item_id, (finding, finding))
        duplicate_payload = replace(response.payload, findings=(duplicate_group,))
        self.assert_encode_error(
            replace(response, payload=duplicate_payload), ErrorCode.DUPLICATE_FINDING_ID
        )

    def test_non_utf8_and_five_mib_inputs_are_rejected_before_decoding(self) -> None:
        self.assert_decode_error(b"\xff", ErrorCode.INVALID_UTF8)
        self.assert_decode_error(b" " * MAX_PROTOCOL_BYTES, ErrorCode.PAYLOAD_TOO_LARGE)

    def test_encoder_rejects_future_protocol_version_and_oversized_output(self) -> None:
        future_response = InventoryResponse(
            FIXED_TIME,
            GenerationId("generation-future"),
            InventoryPayload(ItemSource.ARCH, 1, (sample_item(),)),
            ProtocolVersion(2),
        )
        oversized_items = tuple(
            NormalizedItem(
                ItemId(f"arch:{index}"),
                ItemSource.ARCH,
                "x" * 128,
                "1.0",
                "1.1",
                WatchMode.OFF,
                True,
                Provenance.LIVE,
            )
            for index in range(25_000)
        )
        oversized_response = InventoryResponse(
            FIXED_TIME,
            GenerationId("generation-large"),
            InventoryPayload(ItemSource.ARCH, len(oversized_items), oversized_items),
        )

        self.assert_encode_error(future_response, ErrorCode.PROTOCOL_VERSION_FUTURE)
        self.assert_encode_error(oversized_response, ErrorCode.OUTPUT_TOO_LARGE)


if __name__ == "__main__":
    _ = unittest.main()
