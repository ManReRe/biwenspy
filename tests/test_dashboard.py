import dashboard
import db


def _populate(conn):
    db.upsert_user(conn, 1, "Ana", "")
    db.upsert_user(conn, 2, "Beto", "")
    db.upsert_player(conn, 10, "Jugador A", "Equipo X")
    db.upsert_round(conn, 1, "Jornada 1", 100)
    db.insert_round_points(conn, 1, 1, 60)
    db.insert_round_points(conn, 1, 2, 40)
    db.upsert_standing(conn, 1, 60, 1)
    db.upsert_standing(conn, 2, 40, 2)
    db.insert_money_event(conn, {
        "id": "e1", "date": 100, "round_id": 1, "type": "roundFinished", "user_id": 1,
        "counterparty_id": None, "player_id": None, "amount": 1_000_000, "direction": "income",
        "reason_json": "{}",
    })
    db.insert_money_event(conn, {
        "id": "e2", "date": 200, "round_id": None, "type": "market", "user_id": 1,
        "counterparty_id": None, "player_id": 10, "amount": 2_000_000, "direction": "expense",
        "reason_json": None,
    })


def test_build_dashboard_html_includes_user_names_and_reconstructed_balance():
    conn = db.init_db(":memory:")
    _populate(conn)

    output = dashboard.build_dashboard_html(conn)

    assert "<html" in output
    assert "Ana" in output
    assert "Beto" in output
    # 20,000,000 + 1,000,000 - 2,000,000 = 19,000,000
    assert "19,000,000" in output


def test_build_dashboard_html_includes_curious_facts():
    conn = db.init_db(":memory:")
    _populate(conn)

    output = dashboard.build_dashboard_html(conn)

    assert "Jugador A" in output
    assert "Compra" in output


def test_build_dashboard_html_includes_income_breakdown_and_movements():
    conn = db.init_db(":memory:")
    _populate(conn)

    output = dashboard.build_dashboard_html(conn)

    # Ana: 1,000,000 EUR from points, 0 from sales, 2,000,000 EUR spent on purchases.
    assert "1,000,000 EUR" in output
    assert "2,000,000 EUR" in output
    # Per-manager movements section lists how many movements Ana has.
    assert "2 movimientos" in output


def test_build_dashboard_html_includes_biggest_bonus_round():
    conn = db.init_db(":memory:")
    _populate(conn)

    output = dashboard.build_dashboard_html(conn)

    assert "Jornada con mas dinero repartido" in output
    assert "Jornada 1" in output


def test_build_dashboard_html_handles_empty_database():
    conn = db.init_db(":memory:")
    output = dashboard.build_dashboard_html(conn)
    assert "<html" in output


def test_build_dashboard_html_shows_starting_balance_for_manager_with_no_movements():
    conn = db.init_db(":memory:")
    _populate(conn)  # Beto (user 2) is in standings but has no money_events at all.

    output = dashboard.build_dashboard_html(conn)

    # Beto hasn't traded yet, so his balance must still show the 20,000,000 EUR start,
    # not 0.
    assert "20,000,000 EUR" in output
