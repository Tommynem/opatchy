import subprocess
from pathlib import Path

from opatchy_helper.models import (
    ErrorResponse,
    InventoryResponse,
    ItemId,
    ItemSource,
    ResponseKind,
    SourceName,
    StarResultResponse,
    WatchMode,
)
from opatchy_helper.storage_types import PersistentState, SourceMetadata, WatchRecord

from tests.python.cli_support import (
    NOW,
    concurrent_star,
    inventory_cli,
    item,
    kind,
    response,
    run_cli,
    star_cli,
    storage,
    write_inventory,
)


def error_code(result: subprocess.CompletedProcess[str]) -> str:
    match response(result):
        case ErrorResponse(error=error):
            return error.code.value
        case InventoryResponse() | StarResultResponse():
            raise AssertionError("expected an error response")
        case _:
            raise AssertionError("expected an error response")


def inventory(result: subprocess.CompletedProcess[str]) -> InventoryResponse:
    match response(result):
        case InventoryResponse() as value:
            return value
        case ErrorResponse() | StarResultResponse():
            raise AssertionError("expected an inventory response")
        case _:
            raise AssertionError("expected an inventory response")


def test_routes_emit_each_success_protocol_kind(tmp_path: Path) -> None:
    # Given: no source is due, allowing a scan with no external I/O.
    store = storage(tmp_path)
    store.save_state(
        PersistentState(
            (), (), tuple(SourceMetadata(source, NOW, None) for source in SourceName)
        )
    )

    # When: scan publishes a snapshot before each cache-only route executes.
    scan = run_cli(tmp_path, "scan")
    write_inventory(store, ItemSource.ARCH, item("arch:demo", ItemSource.ARCH, "Demo"))
    snapshot = run_cli(tmp_path, "snapshot")
    listed = inventory_cli(tmp_path, "arch", "", "1", "0")
    starred = star_cli(tmp_path, "arch:demo", "temporary")

    # Then: every process returns exactly one successful protocol object.
    assert all(result.returncode == 0 for result in (scan, snapshot, listed, starred))
    assert tuple(
        kind(response(value)) for value in (scan, snapshot, listed, starred)
    ) == (
        ResponseKind.SNAPSHOT,
        ResponseKind.SNAPSHOT,
        ResponseKind.INVENTORY,
        ResponseKind.STAR_RESULT,
    )


def test_inventory_casefolds_unicode_sorts_duplicate_labels_and_pages(
    tmp_path: Path,
) -> None:
    # Given: duplicate labels and a Unicode label in one validated source cache.
    store = storage(tmp_path)
    write_inventory(
        store,
        ItemSource.ARCH,
        item("arch:zeta", ItemSource.ARCH, "same"),
        item("arch:alpha", ItemSource.ARCH, "same"),
        item("arch:strasse", ItemSource.ARCH, "Straße"),
    )

    # When: literal casefolding and the second deterministic page are requested.
    matched = inventory(inventory_cli(tmp_path, "arch", "STRASSE", "1", "0"))
    paged = inventory(inventory_cli(tmp_path, "arch", "same", "1", "1"))

    # Then: Unicode matches and canonical identity breaks display-label ties.
    assert matched.payload.items[0].item_id == ItemId("arch:strasse")
    assert paged.payload.items[0].item_id == ItemId("arch:zeta")


def test_inventory_reports_full_filtered_total_across_pages(tmp_path: Path) -> None:
    # Given: three sorted query matches and one unrelated cached item.
    store = storage(tmp_path)
    write_inventory(
        store,
        ItemSource.ARCH,
        item("arch:gamma", ItemSource.ARCH, "same"),
        item("arch:alpha", ItemSource.ARCH, "same"),
        item("arch:beta", ItemSource.ARCH, "same"),
        item("arch:other", ItemSource.ARCH, "other"),
    )

    # When: empty, first, middle, and beyond-end pages are requested.
    empty = inventory(inventory_cli(tmp_path, "arch", "missing", "1", "0"))
    first = inventory(inventory_cli(tmp_path, "arch", "same", "1", "0"))
    middle = inventory(inventory_cli(tmp_path, "arch", "same", "1", "1"))
    beyond = inventory(inventory_cli(tmp_path, "arch", "same", "1", "3"))

    # Then: each response reports the complete filtered count, not page size.
    assert (empty.payload.total, empty.payload.items) == (0, ())
    assert (first.payload.total, first.payload.items[0].item_id) == (
        3,
        ItemId("arch:alpha"),
    )
    assert (middle.payload.total, middle.payload.items[0].item_id) == (
        3,
        ItemId("arch:beta"),
    )
    assert (beyond.payload.total, beyond.payload.items) == (3, ())


def test_inventory_rejects_boundaries_and_supports_every_approved_source(
    tmp_path: Path,
) -> None:
    # Given: invalid source/query/pagination values and all approved source caches.
    invalid = (
        ("omarchy", "", "1", "0"),
        ("future", "", "1", "0"),
        ("arch", "x" * 129, "1", "0"),
        ("arch", "", "0", "0"),
        ("arch", "", "101", "0"),
        ("arch", "", "1", "-1"),
    )
    store = storage(tmp_path)
    sources = (ItemSource.ARCH, ItemSource.AUR, ItemSource.FLATPAK, ItemSource.MISE)
    for source in sources:
        write_inventory(store, source, item(f"{source.value}:shared", source, "shared"))

    # When: each rejected request and each allowed source runs through the CLI.
    errors = tuple(
        error_code(inventory_cli(tmp_path, *arguments)) for arguments in invalid
    )
    items = tuple(
        inventory(inventory_cli(tmp_path, source.value, "shared", "100", "0"))
        for source in sources
    )

    # Then: invalid values fail and duplicate labels remain source-qualified IDs.
    assert errors == ("CLI_USAGE",) * len(invalid)
    assert tuple(value.payload.items[0].item_id for value in items) == tuple(
        ItemId(f"{source.value}:shared") for source in sources
    )


def test_permanent_missing_watch_is_visible_and_can_be_cleared(tmp_path: Path) -> None:
    # Given: a permanent watch whose source cache has no corresponding item.
    store = storage(tmp_path)
    write_inventory(store, ItemSource.ARCH)
    store.save_state(
        PersistentState(
            (
                WatchRecord(
                    ItemId("arch:missing"), WatchMode.PERMANENT, None, None, False
                ),
            ),
            (),
            (),
        )
    )

    # When: inventory is read and the existing missing permanent watch is cleared.
    listed = inventory(inventory_cli(tmp_path, "arch", "", "100", "0"))
    cleared = response(star_cli(tmp_path, "arch:missing", "off"))

    # Then: no version evidence is invented and the durable watch is removable.
    missing = listed.payload.items[0]
    assert (missing.item_id, missing.installed, missing.candidate) == (
        ItemId("arch:missing"),
        None,
        None,
    )
    match cleared:
        case StarResultResponse(payload=payload):
            assert (payload.item_id, payload.mode) == (
                ItemId("arch:missing"),
                WatchMode.OFF,
            )
        case InventoryResponse() | ErrorResponse():
            raise AssertionError("expected a star-result response")
        case _:
            raise AssertionError("expected a star-result response")
    assert store.load_state().state.watches == ()


def test_set_star_rejects_identity_mode_and_future_state_without_overwrite(
    tmp_path: Path,
) -> None:
    # Given: a valid cached identity and then a future state-schema document.
    store = storage(tmp_path)
    write_inventory(store, ItemSource.ARCH, item("arch:demo", ItemSource.ARCH, "Demo"))
    unknown = error_code(star_cli(tmp_path, "arch:unknown", "temporary"))
    store.state_path.parent.mkdir(parents=True, exist_ok=True)
    future = b'{"schemaVersion":999,"watches":[]}'
    _ = store.state_path.write_bytes(future)

    # When: malformed and future-schema mutations execute through the subprocess.
    errors = (
        unknown,
        error_code(star_cli(tmp_path, "", "temporary")),
        error_code(star_cli(tmp_path, "arch:demo", "future")),
        error_code(star_cli(tmp_path, "arch:demo", "temporary")),
    )

    # Then: invalid input and unsupported state fail closed without overwrite.
    assert errors == (
        "STATE_UNAVAILABLE",
        "CLI_USAGE",
        "CLI_USAGE",
        "STATE_UNAVAILABLE",
    )
    assert store.state_path.read_bytes() == future


def test_two_concurrent_set_star_mutations_preserve_both_watches(
    tmp_path: Path,
) -> None:
    # Given: two distinct watchable cached identities.
    store = storage(tmp_path)
    write_inventory(
        store,
        ItemSource.ARCH,
        item("arch:first", ItemSource.ARCH, "first"),
        item("arch:second", ItemSource.ARCH, "second"),
    )

    # When: independent helpers request their first legal durable transition.
    first, second = concurrent_star(tmp_path, "arch:first", "arch:second")

    # Then: locking serializes both transitions with no lost durable watch.
    assert (first.returncode, second.returncode, first.stderr, second.stderr) == (
        0,
        0,
        "",
        "",
    )
    assert kind(response(first)) is ResponseKind.STAR_RESULT
    assert kind(response(second)) is ResponseKind.STAR_RESULT
    assert {watch.item_id for watch in store.load_state().state.watches} == {
        ItemId("arch:first"),
        ItemId("arch:second"),
    }
