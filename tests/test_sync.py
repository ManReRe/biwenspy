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


def test_sync_board_stops_as_soon_as_a_known_item_is_seen_once_backfill_is_complete():
    conn = db.init_db(":memory:")
    full_page = [_market_item(date) for date in range(500)]
    # First run walks page 0 (full) then page 1 (short: 1 item < PAGE_SIZE), so it
    # genuinely reaches the end of history and marks the backfill complete -- this is
    # what a real, uninterrupted first sync does.
    sync.sync_board(FakeClient(pages=[full_page, [ROUND_FINISHED_ITEM]]), conn)
    assert db.get_sync_state(conn, "board_backfill_complete") == "true"

    client2 = FakeClient(pages=[full_page, [ROUND_FINISHED_ITEM]])
    sync.sync_board(client2, conn)

    # Fast path: backfill is already complete, so hitting the first (already-seen) item
    # on page 0 is proof there's nothing new below it -- safe to stop immediately.
    assert client2.calls == [0]
    assert len(db.get_all_money_events(conn)) == 501


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
    try:
        sync.sync_board(crashing_client, conn)
    except RuntimeError:
        pass

    # The interrupted run stored page 0's items but never reached a short/empty page,
    # so backfill must still be marked incomplete.
    assert db.get_sync_state(conn, "board_backfill_complete") is None
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


def test_sync_board_keeps_paging_through_pages_with_no_money_events():
    conn = db.init_db(":memory:")
    no_money_page = [{"type": "text", "content": "hola", "date": d} for d in range(500)]
    client = FakeClient(pages=[no_money_page, [_market_item(999)]])

    sync.sync_board(client, conn)

    assert client.calls == [0, 500]
    assert len(db.get_all_money_events(conn)) == 1


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
