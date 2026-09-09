import db


def test_init_db_creates_tables():
    conn = db.init_db(":memory:")
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {
        "users", "players", "rounds", "money_events", "round_points",
        "standings", "sync_state", "board_items",
    } <= tables


def test_upsert_user_inserts_and_updates():
    conn = db.init_db(":memory:")
    db.upsert_user(conn, 1, "Alice", "icon.png")
    db.upsert_user(conn, 1, "Alice Updated", "icon2.png")
    assert db.get_users(conn) == [{"id": 1, "name": "Alice Updated", "icon": "icon2.png"}]


def test_insert_money_event_is_idempotent():
    conn = db.init_db(":memory:")
    event = {
        "id": "abc", "date": 1, "round_id": None, "type": "market",
        "user_id": 1, "counterparty_id": None, "player_id": 5,
        "amount": 1000, "direction": "expense", "reason_json": None,
    }
    assert db.insert_money_event(conn, event) is True
    assert db.insert_money_event(conn, event) is False
    assert len(db.get_all_money_events(conn)) == 1


def test_insert_round_points_is_idempotent():
    conn = db.init_db(":memory:")
    assert db.insert_round_points(conn, 1, 2, 50) is True
    assert db.insert_round_points(conn, 1, 2, 50) is False


def test_board_item_seen_tracking():
    conn = db.init_db(":memory:")
    assert db.has_board_item(conn, "x") is False
    db.mark_board_item_seen(conn, "x")
    assert db.has_board_item(conn, "x") is True


def test_sync_state_roundtrip():
    conn = db.init_db(":memory:")
    assert db.get_sync_state(conn, "missing") is None
    db.set_sync_state(conn, "last_offset", "500")
    assert db.get_sync_state(conn, "last_offset") == "500"
    db.set_sync_state(conn, "last_offset", "1000")
    assert db.get_sync_state(conn, "last_offset") == "1000"


def test_get_players_and_known_player_ids():
    conn = db.init_db(":memory:")
    db.upsert_player(conn, 10, "Jugador A", "Equipo X", position=3)
    assert db.get_players(conn) == {10: {"name": "Jugador A", "team": "Equipo X", "position": 3}}
    assert db.get_known_player_ids(conn) == {10}


def test_upsert_standing_and_get_standings_ordered_by_position():
    conn = db.init_db(":memory:")
    db.upsert_standing(conn, 2, 40, 2)
    db.upsert_standing(conn, 1, 60, 1)
    assert db.get_standings(conn) == [
        {"user_id": 1, "points": 60, "position": 1},
        {"user_id": 2, "points": 40, "position": 2},
    ]


def test_replace_squad_overwrites_previous_snapshot():
    conn = db.init_db(":memory:")
    db.replace_squad(conn, 1, [{"player_id": 10, "price_paid": 100, "acquired_date": 5}])
    db.replace_squad(conn, 1, [{"player_id": 20, "price_paid": None, "acquired_date": 9}])
    assert db.get_all_squads(conn) == [
        {"user_id": 1, "player_id": 20, "price_paid": None, "acquired_date": 9},
    ]


def test_player_form_roundtrip():
    conn = db.init_db(":memory:")
    db.upsert_player_form(conn, 10, "[2, 5, 3]", "ok")
    db.upsert_player_form(conn, 10, "[5, 3]", "injured")
    assert db.get_player_form(conn) == {10: {"recent_points": [5, 3], "status": "injured"}}
