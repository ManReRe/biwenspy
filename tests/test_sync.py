import pytest

import db
import sync


class FakeClient:
    def __init__(self, pages):
        self._pages = pages
        self.calls = []

    def get_board_page(self, offset, limit=500):
        self.calls.append(offset)
        index = offset // limit
        return self._pages[index] if index < len(self._pages) else []


def _market_item(date, amount=500_000):
    return {
        "type": "market",
        "content": [{"player": 10, "to": {"id": 1, "name": "Ana"}, "amount": amount}],
        "date": date,
    }


ROUND_FINISHED_ITEM = {
    "type": "roundFinished",
    "content": {
        "round": {"id": 1, "name": "J1"},
        "results": [{"user": {"id": 1, "name": "Ana"}, "points": 50, "bonus": 1_000_000, "reason": {}}],
    },
    "date": 999,
}


def test_sync_board_stores_events_from_a_single_short_page():
    conn = db.init_db(":memory:")
    client = FakeClient(pages=[[ROUND_FINISHED_ITEM, _market_item(200)]])

    sync.sync_board(client, conn)

    assert len(db.get_all_money_events(conn)) == 2
    assert client.calls == [0]


def test_sync_board_pages_forward_while_pages_are_full():
    conn = db.init_db(":memory:")
    full_page = [_market_item(date) for date in range(500)]
    client = FakeClient(pages=[full_page, [ROUND_FINISHED_ITEM]])

    sync.sync_board(client, conn)

    assert client.calls == [0, 500]
    assert len(db.get_all_money_events(conn)) == 501


def test_sync_board_stops_as_soon_as_the_previous_top_item_marker_is_seen_again():
    conn = db.init_db(":memory:")
    full_page = [_market_item(date) for date in range(500)]
    # First run walks page 0 (full) then page 1 (short: 1 item < PAGE_SIZE), so it
    # genuinely reaches the end of history, marks the backfill complete, and records
    # the newest item's id as the top-item marker -- this is what a real, uninterrupted
    # first sync does.
    sync.sync_board(FakeClient(pages=[full_page, [ROUND_FINISHED_ITEM]]), conn)
    assert db.get_sync_state(conn, "board_backfill_complete") == "true"
    top_marker = db.get_sync_state(conn, "board_top_item_id")
    assert top_marker is not None

    client2 = FakeClient(pages=[full_page, [ROUND_FINISHED_ITEM]])
    sync.sync_board(client2, conn)

    # Fast path: backfill is already complete, so hitting the previous run's top-item
    # marker again on the very first item of page 0 is proof there's nothing new below
    # it -- safe to stop immediately. The marker itself doesn't change since nothing new
    # was found on top of it.
    assert client2.calls == [0]
    assert len(db.get_all_money_events(conn)) == 501
    assert db.get_sync_state(conn, "board_top_item_id") == top_marker


def test_sync_board_recovers_never_synced_history_after_an_interrupted_first_run():
    """Reproduces the bug: an interrupted first run (crash mid-walk, before reaching a
    short/empty page) must NOT permanently strand older, never-fetched pages. A second
    run must keep paging past any already-seen items until it reaches the true end of
    history, even though new activity has appeared on top in the meantime.
    """
    conn = db.init_db(":memory:")
    first_page = [_market_item(date) for date in range(500)]

    class CrashingClient:
        """Simulates a process killed/crashed right after fetching the second page."""

        def __init__(self):
            self.calls = []

        def get_board_page(self, offset, limit=500):
            self.calls.append(offset)
            if offset == 0:
                return first_page
            raise RuntimeError("simulated crash / network error")

    crashing_client = CrashingClient()
    with pytest.raises(RuntimeError):
        sync.sync_board(crashing_client, conn)

    # The interrupted run stored page 0's items but never reached a short/empty page,
    # so backfill must still be marked incomplete, and the top-item marker must not
    # have been written (the walk never completed).
    assert db.get_sync_state(conn, "board_backfill_complete") is None
    assert db.get_sync_state(conn, "board_top_item_id") is None
    assert len(db.get_all_money_events(conn)) == 500

    # Second run: new activity pushed old page-0 item 0 down to still be present on the
    # (new) page 0, alongside new content; page 1 (offset 500) holds history that was
    # never fetched by the interrupted first run.
    page0_run2 = [first_page[0]] + [_market_item(date) for date in range(10_000, 10_499)]
    historical_item = _market_item(20_000)
    client2 = FakeClient(pages=[page0_run2, [historical_item]])

    sync.sync_board(client2, conn)

    # The old bug: stopping forever after the first known item on page 0 would mean
    # offset 500 is never requested. Assert it IS requested and the historical item
    # from it IS stored -- proving the gap is recovered.
    assert client2.calls == [0, 500]
    assert db.get_sync_state(conn, "board_backfill_complete") == "true"
    all_events = db.get_all_money_events(conn)
    assert len(all_events) == 500 + 499 + 1
    assert any(event["date"] == 20_000 for event in all_events)
    assert db.get_sync_state(conn, "board_top_item_id") == sync._item_id(page0_run2[0])


def test_sync_board_recovers_never_synced_history_after_an_interrupted_steady_state_run():
    """Reproduces the reviewer's follow-up scenario: the FIRST backfill completes
    cleanly (board_backfill_complete == "true", a top-item marker is recorded), but a
    LATER steady-state run crashes partway through -- after storing a full page of
    brand-new items, but before fetching the next page (which also holds new,
    never-before-seen items). The old "stop on any already-seen item" design would
    have let a subsequent run stop at the very first item of that first page (now
    already seen from the crashed run) and never reach the second page again, silently
    losing it forever. The marker-based design must instead notice that the crashed
    run never advanced the marker, and keep walking on the next attempt until the
    marker (or a short page) is reached, recovering the lost page.
    """
    conn = db.init_db(":memory:")

    # Run 1: a full, uninterrupted first backfill. Page 0 is full (500 items), page 1
    # is short (50 items) -- the true end of history.
    backfill_page0 = [_market_item(date) for date in range(500)]
    backfill_page1 = [_market_item(date) for date in range(500, 550)]
    sync.sync_board(FakeClient(pages=[backfill_page0, backfill_page1]), conn)

    assert db.get_sync_state(conn, "board_backfill_complete") == "true"
    marker_after_run1 = db.get_sync_state(conn, "board_top_item_id")
    assert marker_after_run1 == sync._item_id(backfill_page0[0])

    # Run 2: steady state. A burst of activity means there's more than one page of
    # brand-new items since run 1: page 0 (offset 0) is a full page of new items D1-500
    # that stores cleanly, but the fetch of page 1 (offset 500, which would also hold
    # new, never-before-seen items D501-550) crashes.
    run2_page0 = [_market_item(date) for date in range(100_000, 100_500)]
    run2_page1 = [_market_item(date) for date in range(100_500, 100_550)]

    class CrashesOnSecondPageClient:
        def __init__(self):
            self.calls = []

        def get_board_page(self, offset, limit=500):
            self.calls.append(offset)
            if offset == 0:
                return run2_page0
            raise RuntimeError("simulated crash / network error")

    crashing_client = CrashesOnSecondPageClient()
    with pytest.raises(RuntimeError):
        sync.sync_board(crashing_client, conn)

    # Page 0's 500 new items were stored (idempotent inserts make this safe), but since
    # the run never completed, the top-item marker must be UNCHANGED from run 1 --
    # this is exactly what lets the next run know it must keep walking.
    assert crashing_client.calls == [0, 500]
    assert db.get_sync_state(conn, "board_backfill_complete") == "true"
    assert db.get_sync_state(conn, "board_top_item_id") == marker_after_run1
    events_after_run2 = db.get_all_money_events(conn)
    assert len(events_after_run2) == 550 + 500  # run 1's 550 + run 2's page-0 500
    # Page 1's items (run2_page1, dates 100_500-100_549) never got fetched, so none of
    # them can be stored yet.
    assert not any(100_500 <= e["date"] < 100_550 for e in events_after_run2)

    # Run 3: same page 0 and now a succeeding page 1, matching what run 2 was fetching
    # when it crashed. Since the marker still points at run 1's top item (not anything
    # from run 2's page 0), run 3 must walk past all of page 0 (idempotently
    # re-storing it) and reach page 1, recovering the items that run 2's crash lost.
    client3 = FakeClient(pages=[run2_page0, run2_page1])
    sync.sync_board(client3, conn)

    assert client3.calls == [0, 500]
    all_events = db.get_all_money_events(conn)
    assert len(all_events) == 550 + 500 + 50  # run 1's 550 + run 2's 500 + recovered 50
    assert any(100_500 <= e["date"] < 100_550 for e in all_events)
    assert db.get_sync_state(conn, "board_top_item_id") == sync._item_id(run2_page0[0])


def test_sync_board_writes_this_runs_own_top_item_as_the_new_marker_on_fast_path_stop():
    """The fast-path stop (hitting the previous marker mid-page during a steady-state
    run) must record THIS run's own newest item as the new ``board_top_item_id`` --
    not leave the old marker in place and not record the item where it stopped. No
    existing test exercises this specific write in a way that would fail if it were
    dropped or written with the wrong value (e.g. the old marker, or the stopping
    item's id).
    """
    conn = db.init_db(":memory:")

    # Run 1: a full, uninterrupted backfill across exactly 550 items (a full page 0 of
    # 500 plus a short page 1 of 50), so it fully backfills and reaches a short final
    # page -- same pattern as the interrupted-steady-state test above.
    backfill_page0 = [_market_item(date) for date in range(500)]  # dates 0-499
    backfill_page1 = [_market_item(date) for date in range(500, 550)]  # dates 500-549
    sync.sync_board(FakeClient(pages=[backfill_page0, backfill_page1]), conn)

    assert db.get_sync_state(conn, "board_backfill_complete") == "true"
    old_marker = db.get_sync_state(conn, "board_top_item_id")
    assert old_marker == sync._item_id(backfill_page0[0])
    events_before = len(db.get_all_money_events(conn))
    assert events_before == 550

    # Run 2: a NEW client whose board is 700 fresh items pushed on top of the original
    # 550. The item that was previously the top (backfill_page0[0], now the recorded
    # marker) sits at absolute position 700 -- NOT a page boundary -- landing at index
    # 200 of the second page fetched at offset 500.
    new_items = [_market_item(date) for date in range(200_000, 200_700)]  # 700 fresh items
    page0_run2 = new_items[0:500]
    page1_run2 = new_items[500:700] + [backfill_page0[0]]  # marker at index 200
    client2 = FakeClient(pages=[page0_run2, page1_run2])

    sync.sync_board(client2, conn)

    # Fast path stops mid-page-two, at the marker, without ever requesting offset 1000.
    assert client2.calls == [0, 500]

    # Exactly the 700 fresh items were added as new money events -- the marker item
    # itself, encountered mid-page, is not reprocessed.
    events_after = len(db.get_all_money_events(conn))
    assert events_after - events_before == 700

    # The new marker must be THIS run's own top item (the first of the 700 pushed on
    # top), not the old marker and not the item where the walk stopped.
    assert db.get_sync_state(conn, "board_top_item_id") == sync._item_id(new_items[0])
    assert db.get_sync_state(conn, "board_top_item_id") != old_marker


def test_sync_board_keeps_paging_through_pages_with_no_money_events():
    conn = db.init_db(":memory:")
    no_money_page = [{"type": "text", "content": "hola", "date": d} for d in range(500)]
    client = FakeClient(pages=[no_money_page, [_market_item(999)]])

    sync.sync_board(client, conn)

    assert client.calls == [0, 500]
    assert len(db.get_all_money_events(conn)) == 1


def test_record_real_balance_check_stores_owner_and_their_real_balance():
    # This is a comparison data point only -- it must never be used to adjust
    # any computed balance (the reconstruction always stays a plain
    # analytics.STARTING_BALANCE plus synced events, uniformly for everyone).
    conn = db.init_db(":memory:")

    class BalanceClient:
        def get_own_balance(self):
            return 38_470

    sync.record_real_balance_check(BalanceClient(), conn, owner_user_id=1)

    assert db.get_sync_state(conn, "owner_user_id") == "1"
    assert db.get_sync_state(conn, "owner_real_balance") == "38470"


def test_record_real_balance_check_leaves_state_untouched_when_balance_unavailable():
    conn = db.init_db(":memory:")

    class NoBalanceClient:
        def get_own_balance(self):
            return None

    sync.record_real_balance_check(NoBalanceClient(), conn, owner_user_id=1)

    assert db.get_sync_state(conn, "owner_user_id") is None
    assert db.get_sync_state(conn, "owner_real_balance") is None


def test_sync_players_fetches_and_stores_only_referenced_players():
    conn = db.init_db(":memory:")
    db.insert_money_event(conn, {
        "id": "e1", "date": 1, "round_id": None, "type": "market", "user_id": 1,
        "counterparty_id": None, "player_id": 10, "amount": 100, "direction": "expense",
        "reason_json": None,
    })

    class PlayersClient:
        def get_players(self):
            return {
                10: {"name": "Jugador A", "team": "Equipo X"},
                11: {"name": "Jugador B", "team": "Equipo Y"},
            }

    sync.sync_players(PlayersClient(), conn)

    assert db.get_players(conn) == {10: {"name": "Jugador A", "team": "Equipo X"}}


def test_sync_players_skips_api_call_when_nothing_new():
    conn = db.init_db(":memory:")
    db.upsert_player(conn, 10, "Jugador A", "Equipo X")
    db.insert_money_event(conn, {
        "id": "e1", "date": 1, "round_id": None, "type": "market", "user_id": 1,
        "counterparty_id": None, "player_id": 10, "amount": 100, "direction": "expense",
        "reason_json": None,
    })

    class ExplodingClient:
        def get_players(self):
            raise AssertionError("should not be called")

    sync.sync_players(ExplodingClient(), conn)  # must not raise


def test_main_exits_cleanly_on_auth_error(tmp_path, monkeypatch):
    # Isolate from the real filesystem: replace load_config entirely (rather than
    # patching sync.CONFIG_PATH, which wouldn't work anyway -- it's captured as
    # load_config's default parameter value at def time, not re-read per call) and
    # point DB_PATH at a throwaway file under tmp_path so nothing touches the project's
    # real config.json/biwenger.db.
    monkeypatch.setattr(sync, "load_config", lambda: {"token": "t", "league_id": 1, "user_id": 2})
    monkeypatch.setattr(sync, "DB_PATH", str(tmp_path / "biwenger.db"))

    class ExplodingAuthClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_league_users(self):
            raise sync.BiwengerAuthError("Biwenger rechazo el token (401).")

    monkeypatch.setattr(sync, "BiwengerClient", ExplodingAuthClient)

    with pytest.raises(SystemExit) as exc_info:
        sync.main()

    assert exc_info.value.code == 1
