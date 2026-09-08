import re

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


def test_build_dashboard_html_does_not_load_plotly_from_a_cdn():
    conn = db.init_db(":memory:")
    _populate(conn)

    output = dashboard.build_dashboard_html(conn)

    # The chart must be self-contained: no src="..." pointing at an external CDN
    # (previously plot() was called with include_plotlyjs="cdn", which produced
    # exactly such an attribute and made the dashboard depend on internet access to
    # render). Note: we deliberately don't match "<script src=" here -- Plotly's real
    # CDN output places other attributes (e.g. charset) before src= in the <script>
    # tag, so that substring never appears verbatim even in the broken version, which
    # would make this assertion pass regardless of whether the bug is present.
    assert 'src="https://cdn.plot.ly' not in output


def test_build_dashboard_html_renders_dates_as_human_readable_not_raw_epoch():
    conn = db.init_db(":memory:")
    _populate(conn)
    distinctive_epoch = 1_700_000_000  # 2023-11-14, chosen so it can't collide with
    # any EUR amount (which are always comma-grouped) elsewhere in the output.
    db.insert_money_event(conn, {
        "id": "e3", "date": distinctive_epoch, "round_id": None, "type": "market",
        "user_id": 1, "counterparty_id": None, "player_id": 10, "amount": 100,
        "direction": "expense", "reason_json": None,
    })

    output = dashboard.build_dashboard_html(conn)

    assert str(distinctive_epoch) not in output
    assert dashboard._format_date(distinctive_epoch) in output
    assert re.search(r"\d{4}-\d{2}-\d{2}", output)


def test_build_dashboard_html_falls_back_to_jugador_placeholder_for_unknown_player():
    conn = db.init_db(":memory:")
    _populate(conn)
    # player_id 999 is never registered via db.upsert_player, so it's unresolvable.
    db.insert_money_event(conn, {
        "id": "e3", "date": 300, "round_id": None, "type": "market", "user_id": 1,
        "counterparty_id": None, "player_id": 999, "amount": 100, "direction": "expense",
        "reason_json": None,
    })

    output = dashboard.build_dashboard_html(conn)

    assert "Jugador 999" in output


def test_movement_description_never_renders_the_literal_none_for_a_playerless_event():
    # A market movement with no "player" field at all (player_id is genuinely None,
    # not merely unresolvable) must not render the Python value None into the text.
    event = {
        "type": "market", "direction": "expense", "player_id": None,
        "counterparty_id": None,
    }
    description = dashboard._movement_description(event, names={}, players={})
    assert "None" not in description
    assert description == "Compra al mercado"


def test_movement_description_never_renders_the_literal_none_for_an_unresolvable_transfer_expense():
    # A transfer/expense movement (a purchase from another manager) with no player and
    # an unresolvable counterparty must not render the Python value None into the text
    # (previously this rendered the literal string "Compra a None").
    event = {
        "type": "transfer", "direction": "expense", "player_id": None,
        "counterparty_id": None,
    }
    description = dashboard._movement_description(event, names={}, players={})
    assert "None" not in description
    assert description == "Compra a un manager desconocido"


def test_build_dashboard_html_always_uses_the_plain_20m_starting_balance():
    # The reconstruction is always a plain, uniform calculation for every
    # manager -- analytics.STARTING_BALANCE plus the net of their synced money
    # events, with no hidden per-manager adjustment or calibration, even if a
    # sync_state key from an older run happens to be present.
    conn = db.init_db(":memory:")
    _populate(conn)
    db.set_sync_state(conn, "owner_user_id", "1")
    db.set_sync_state(conn, "owner_real_balance", "999")  # must NOT shift the calc

    output = dashboard.build_dashboard_html(conn)

    # Ana: 20,000,000 + 1,000,000 (points) - 2,000,000 (purchase) = 19,000,000
    assert "19,000,000" in output
    # Beto has no money events at all: falls back to the plain 20,000,000
    # starting balance.
    assert "20,000,000 EUR" in output


def test_build_dashboard_html_shows_the_real_balance_check_without_adjusting_the_calc():
    # sync.py's record_real_balance_check stores the account owner's real
    # current balance purely for a visible comparison -- the dashboard must
    # disclose the gap against the plain reconstruction, not silently correct
    # for it.
    conn = db.init_db(":memory:")
    _populate(conn)
    db.set_sync_state(conn, "owner_user_id", "1")  # Ana is the account owner
    db.set_sync_state(conn, "owner_real_balance", "18700000")

    output = dashboard.build_dashboard_html(conn)

    # Ana's plain reconstructed balance (19,000,000) still appears unchanged...
    assert "19,000,000" in output
    # ...alongside her real balance and the gap between them, disclosed.
    assert "18,700,000" in output
    assert "300,000" in output  # 19,000,000 - 18,700,000


def test_build_dashboard_html_omits_the_real_balance_check_when_unavailable():
    conn = db.init_db(":memory:")
    _populate(conn)
    # No sync_state["owner_real_balance"] set -- e.g. dashboard.py run before
    # any sync, or the API couldn't report it.

    output = dashboard.build_dashboard_html(conn)

    assert "Comprobacion" not in output


def test_build_dashboard_html_has_a_tab_for_each_section():
    conn = db.init_db(":memory:")
    _populate(conn)

    output = dashboard.build_dashboard_html(conn)

    for tab_id in ("resumen", "desglose", "movimientos", "curiosidades"):
        assert f'id="btn-{tab_id}"' in output
        assert f'id="tab-{tab_id}"' in output


def test_build_dashboard_html_movements_selector_lists_every_manager():
    # Beto has zero money events in this fixture -- he must still get a
    # selector option and an (empty) panel, not be silently omitted.
    conn = db.init_db(":memory:")
    _populate(conn)

    output = dashboard.build_dashboard_html(conn)

    assert '<option value="1">Ana (2 movimientos)</option>' in output
    assert '<option value="2">Beto (0 movimientos)</option>' in output
    assert 'id="manager-2"' in output
    assert "Sin movimientos todavia." in output


def test_build_dashboard_html_only_the_first_manager_panel_starts_active():
    conn = db.init_db(":memory:")
    _populate(conn)

    output = dashboard.build_dashboard_html(conn)

    assert 'class="manager-panel active" id="manager-1"' in output
    assert 'class="manager-panel" id="manager-2"' in output
