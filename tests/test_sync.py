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


def test_sync_board_stops_as_soon_as_a_known_item_is_seen():
    conn = db.init_db(":memory:")
    full_page = [_market_item(date) for date in range(500)]
    sync.sync_board(FakeClient(pages=[full_page, [ROUND_FINISHED_ITEM]]), conn)

    client2 = FakeClient(pages=[full_page, [ROUND_FINISHED_ITEM]])
    sync.sync_board(client2, conn)

    assert client2.calls == [0]
    assert len(db.get_all_money_events(conn)) == 501


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
