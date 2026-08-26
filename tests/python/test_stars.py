from __future__ import annotations

import hashlib
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "helper"))

from opatchy_helper.models import (
    ItemId,
    ItemSource,
    NormalizedItem,
    NotificationStatus,
    Provenance,
    WatchMode,
)
from opatchy_helper.stars import (
    CachedInventory,
    CachedItem,
    FailedSourceScan,
    FreshSourceScan,
    InvalidSourceScan,
    StaleSourceScan,
    StarClick,
    WatchEvent,
    WatchTransitionError,
    apply_durable_event,
    cached_item,
    missing_permanent_item_ids,
    transition,
    watch_notification_reference,
)
from opatchy_helper.storage import Storage, SystemAtomicOperations
from opatchy_helper.storage_state import decode_state, encode_state
from opatchy_helper.storage_types import LedgerEntry, PersistentState, WatchRecord

NOW = datetime(2026, 8, 26, tzinfo=timezone.utc)


def item(
    item_id: str = "arch:demo",
    source: ItemSource = ItemSource.ARCH,
    installed: str | None = "1.0",
    candidate: str | None = "1.1",
    watchable: bool = True,
) -> CachedItem:
    return CachedItem(ItemId(item_id), source, installed, candidate, watchable)


def inventory(*items: CachedItem) -> CachedInventory:
    return CachedInventory(items)


def temporary(
    item_id: str = "arch:demo",
    installed: str = "1.0",
    candidate: str | None = None,
    armed: bool = False,
) -> WatchRecord:
    return WatchRecord(
        ItemId(item_id), WatchMode.TEMPORARY, installed, candidate, armed
    )


def test_off_click_creates_an_armed_temporary_watch_when_candidate_exists() -> None:
    # Given: a cached, watchable Arch item with installed and candidate evidence.
    inventory = CachedInventory(
        (
            CachedItem(
                ItemId("arch:demo"),
                ItemSource.ARCH,
                "installed-v1",
                "candidate-v2",
                True,
            ),
        )
    )

    # When: the item is starred from the off state.
    updated = transition(
        PersistentState.empty(), StarClick(ItemId("arch:demo"), inventory)
    )

    # Then: the temporary watch records the baseline and arms immediately.
    assert updated.watches[0].installed_fingerprint == "installed-v1"
    assert updated.watches[0].candidate_fingerprint == "candidate-v2"
    assert updated.watches[0].armed


@pytest.mark.parametrize(
    ("starting", "expected_mode"),
    (
        (PersistentState.empty(), WatchMode.TEMPORARY),
        (PersistentState((temporary(),), (), ()), WatchMode.PERMANENT),
        (
            PersistentState(
                (
                    WatchRecord(
                        ItemId("arch:demo"), WatchMode.PERMANENT, None, None, False
                    ),
                ),
                (),
                (),
            ),
            WatchMode.OFF,
        ),
    ),
)
def test_star_click_follows_three_state_cycle(
    starting: PersistentState, expected_mode: WatchMode
) -> None:
    updated = transition(starting, StarClick(ItemId("arch:demo"), inventory(item())))

    assert (
        updated.watches[0].mode if updated.watches else WatchMode.OFF
    ) is expected_mode


def test_off_click_without_candidate_preserves_baseline_and_stays_unarmed() -> None:
    updated = transition(
        PersistentState.empty(),
        StarClick(ItemId("arch:demo"), inventory(item(candidate=None))),
    )

    assert updated.watches == (temporary(),)


@pytest.mark.parametrize(
    "cached",
    (
        inventory(),
        inventory(item(watchable=False)),
        inventory(item(installed=None)),
    ),
)
def test_off_click_rejects_unknown_nonwatchable_or_baselineless_items_without_state_change(
    cached: CachedInventory,
) -> None:
    state = PersistentState.empty()

    with pytest.raises(WatchTransitionError):
        _ = transition(state, StarClick(ItemId("arch:demo"), cached))

    assert state == PersistentState.empty()


@pytest.mark.parametrize(
    "event",
    (
        StaleSourceScan(ItemSource.ARCH),
        FailedSourceScan(ItemSource.ARCH),
        InvalidSourceScan(ItemSource.ARCH),
        FreshSourceScan(ItemSource.AUR, inventory(item("aur:demo", ItemSource.AUR))),
    ),
)
def test_unusable_or_other_source_scan_preserves_temporary_state_exactly(
    event: WatchEvent,
) -> None:
    state = PersistentState((temporary(candidate="1.1", armed=True),), (), ())

    assert transition(state, event) == state


def test_fresh_first_candidate_arms_unarmed_temporary_without_clearing() -> None:
    state = PersistentState((temporary(),), (), ())

    updated = transition(
        state, FreshSourceScan(ItemSource.ARCH, inventory(item(candidate="2.0")))
    )

    assert updated.watches == (temporary(candidate="2.0", armed=True),)


@pytest.mark.parametrize(
    "candidate",
    (None, "2.0"),
)
def test_fresh_installed_change_clears_temporary_even_without_candidate(
    candidate: str | None,
) -> None:
    state = PersistentState((temporary(candidate="1.1", armed=True),), (), ())

    updated = transition(
        state,
        FreshSourceScan(
            ItemSource.ARCH, inventory(item(installed="1.1", candidate=candidate))
        ),
    )

    assert updated.watches == ()


def test_fresh_confirmed_removal_clears_temporary() -> None:
    state = PersistentState((temporary(candidate="1.1", armed=True),), (), ())

    assert (
        transition(
            state,
            FreshSourceScan(
                ItemSource.ARCH, inventory(), frozenset((ItemId("arch:demo"),))
            ),
        )
        == PersistentState.empty()
    )


@pytest.mark.parametrize(
    "watch",
    (temporary(), temporary(candidate="1.1", armed=True)),
)
def test_empty_fresh_updates_without_explicit_removal_preserve_temporary_watch(
    watch: WatchRecord,
) -> None:
    state = PersistentState((watch,), (), ())

    updated = transition(state, FreshSourceScan(ItemSource.ARCH, inventory()))

    assert updated == state


def test_source_scoped_removal_cannot_clear_same_label_item_from_another_source() -> (
    None
):
    arch_watch = temporary("arch:shared", candidate="1.1", armed=True)
    aur_watch = temporary("aur:shared", candidate="1.1", armed=True)
    state = PersistentState((arch_watch, aur_watch), (), ())

    ignored = transition(
        state,
        FreshSourceScan(
            ItemSource.ARCH, inventory(), frozenset((ItemId("aur:shared"),))
        ),
    )
    cleared = transition(
        state,
        FreshSourceScan(
            ItemSource.ARCH, inventory(), frozenset((ItemId("arch:shared"),))
        ),
    )

    assert ignored == state
    assert cleared.watches == (aur_watch,)


@pytest.mark.parametrize(
    "watch",
    (temporary(), temporary(candidate="1.1", armed=True)),
)
def test_candidate_withdrawal_with_unchanged_installation_preserves_temporary_state(
    watch: WatchRecord,
) -> None:
    state = PersistentState((watch,), (), ())

    updated = transition(
        state, FreshSourceScan(ItemSource.ARCH, inventory(item(candidate=None)))
    )

    assert updated == state


def test_permanent_normalizes_and_survives_every_scan_and_missing_view_exposes_only_id() -> (
    None
):
    state = transition(
        PersistentState((temporary(candidate="1.1", armed=True),), (), ()),
        StarClick(ItemId("arch:demo"), inventory()),
    )

    for event in (
        FreshSourceScan(ItemSource.ARCH, inventory()),
        StaleSourceScan(ItemSource.ARCH),
        FailedSourceScan(ItemSource.ARCH),
        InvalidSourceScan(ItemSource.ARCH),
    ):
        state = transition(state, event)

    assert state.watches == (
        WatchRecord(ItemId("arch:demo"), WatchMode.PERMANENT, None, None, False),
    )
    assert missing_permanent_item_ids(state, inventory()) == (ItemId("arch:demo"),)


def test_permanent_clear_removes_only_pending_attributed_notification_references() -> (
    None
):
    watched = WatchRecord(ItemId("arch:demo"), WatchMode.PERMANENT, None, None, False)
    matching = LedgerEntry(
        watch_notification_reference(ItemId("arch:demo"), "candidate-a"),
        NotificationStatus.PENDING,
        NOW,
    )
    historical = LedgerEntry(
        watch_notification_reference(ItemId("arch:demo"), "candidate-old"),
        NotificationStatus.DELIVERED,
        NOW,
    )
    other = LedgerEntry(
        watch_notification_reference(ItemId("aur:demo"), "candidate-a"),
        NotificationStatus.PENDING,
        NOW,
    )
    state = PersistentState((watched,), (matching, historical, other), ())

    updated = transition(state, StarClick(ItemId("arch:demo"), inventory()))

    assert updated.watches == ()
    assert updated.ledger == (historical, other)


def test_cached_adapter_fingerprint_is_deterministic_and_duplicate_labels_remain_distinct() -> (
    None
):
    arch = NormalizedItem(
        ItemId("arch:shared"),
        ItemSource.ARCH,
        "shared",
        "1.0",
        "1.1",
        WatchMode.OFF,
        True,
        Provenance.LIVE,
    )
    aur = NormalizedItem(
        ItemId("aur:shared"),
        ItemSource.AUR,
        "shared",
        "1.0",
        "1.1",
        WatchMode.OFF,
        True,
        Provenance.LIVE,
    )
    cached = inventory(cached_item(arch), cached_item(aur))

    state = transition(PersistentState.empty(), StarClick(arch.item_id, cached))
    state = transition(state, StarClick(aur.item_id, cached))

    assert tuple(watch.item_id for watch in state.watches) == (
        arch.item_id,
        aur.item_id,
    )
    assert (
        state.watches[0].installed_fingerprint != state.watches[1].installed_fingerprint
    )
    assert (
        state.watches[0].installed_fingerprint
        == hashlib.sha256(b"arch\x00arch:shared\x001.0").hexdigest()
    )


def test_cached_adapter_preserves_absent_native_evidence_without_fabricating_fingerprint() -> (
    None
):
    normalized = NormalizedItem(
        ItemId("mise:tool"),
        ItemSource.MISE,
        "tool",
        None,
        None,
        WatchMode.OFF,
        True,
        Provenance.LIVE,
    )

    assert cached_item(normalized).installed_fingerprint is None
    assert cached_item(normalized).candidate_fingerprint is None


def test_invalid_in_memory_off_record_fails_closed_for_click_and_fresh_scan() -> None:
    state = PersistentState(
        (WatchRecord(ItemId("arch:demo"), WatchMode.OFF, None, None, False),), (), ()
    )

    with pytest.raises(WatchTransitionError):
        _ = transition(state, StarClick(ItemId("arch:demo"), inventory(item())))
    with pytest.raises(WatchTransitionError):
        _ = transition(state, FreshSourceScan(ItemSource.ARCH, inventory(item())))


def test_unknown_in_memory_watch_mode_fails_closed_for_click_and_fresh_scan() -> None:
    watch = WatchRecord(ItemId("arch:demo"), WatchMode.OFF, None, None, False)
    object.__setattr__(watch, "mode", "future")
    state = PersistentState((watch,), (), ())

    with pytest.raises(WatchTransitionError):
        _ = transition(state, StarClick(ItemId("arch:demo"), inventory(item())))
    with pytest.raises(WatchTransitionError):
        _ = transition(state, FreshSourceScan(ItemSource.ARCH, inventory(item())))


def test_transition_error_keeps_its_typed_reason() -> None:
    with pytest.raises(WatchTransitionError) as raised:
        _ = transition(
            PersistentState.empty(), StarClick(ItemId("arch:demo"), inventory())
        )

    assert str(raised.value) == "item is not a cached watchable item"


@dataclass(frozen=True, slots=True)
class ExtendedWatchEvent:
    pass


def test_transition_rejects_a_future_event_discriminator() -> None:
    dynamic_transition: Callable[..., PersistentState] = transition

    with pytest.raises(AssertionError):
        _ = dynamic_transition(PersistentState.empty(), ExtendedWatchEvent())


def test_finite_transition_sequences_remain_valid_and_restart_safe() -> None:
    state = PersistentState.empty()
    events = (
        StarClick(ItemId("arch:demo"), inventory(item(candidate=None))),
        FreshSourceScan(ItemSource.ARCH, inventory(item(candidate="1.1"))),
        StaleSourceScan(ItemSource.ARCH),
        FreshSourceScan(ItemSource.ARCH, inventory(item(candidate=None))),
        StarClick(ItemId("arch:demo"), inventory()),
        FreshSourceScan(ItemSource.ARCH, inventory()),
        StarClick(ItemId("arch:demo"), inventory()),
    )

    for event in events:
        state = transition(state, event)
        state = decode_state(encode_state(state, NOW))

    assert state == PersistentState.empty()


def test_durable_wrapper_uses_storage_update_and_rejection_keeps_last_good_bytes(
    tmp_path: Path,
) -> None:
    store = Storage(
        tmp_path / "state.json",
        tmp_path / "cache",
        lambda: NOW,
        SystemAtomicOperations(),
    )
    store.save_state(PersistentState.empty())
    before = store.state_path.read_bytes()

    with pytest.raises(WatchTransitionError):
        _ = apply_durable_event(store, StarClick(ItemId("arch:unknown"), inventory()))

    assert store.state_path.read_bytes() == before
    updated = apply_durable_event(
        store, StarClick(ItemId("arch:demo"), inventory(item()))
    )
    assert updated.watches[0].item_id == ItemId("arch:demo")
