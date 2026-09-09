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
    _attr, description = dashboard._movement_description_html(event, names={}, players={}, rounds_by_id={})
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
    _attr, description = dashboard._movement_description_html(event, names={}, players={}, rounds_by_id={})
    assert "None" not in description
    assert description == "Compra a un manager desconocido"


def test_build_dashboard_html_uses_the_calibrated_starting_balance_when_set():
    # sync.py's calibrate_starting_balance back-solves the real starting
    # balance for the current season and stores it in sync_state. The
    # dashboard must use that figure -- not the plain 20,000,000 default --
    # for both the reconstructed balance and the zero-movements fallback.
    conn = db.init_db(":memory:")
    _populate(conn)
    db.set_sync_state(conn, "starting_balance", "18420000")

    output = dashboard.build_dashboard_html(conn)

    # Ana: 18,420,000 + 1,000,000 (points) - 2,000,000 (purchase) = 17,420,000
    assert "17,420,000" in output
    # Beto has no money events at all: falls back to the calibrated starting
    # balance, not the hardcoded 20,000,000 default.
    assert "18,420,000 EUR" in output
    assert "20,000,000" not in output


def test_build_dashboard_html_falls_back_to_the_default_starting_balance_when_uncalibrated():
    conn = db.init_db(":memory:")
    _populate(conn)
    # No sync_state["starting_balance"] set -- e.g. dashboard.py run before
    # the first sync.py completed a calibration.

    output = dashboard.build_dashboard_html(conn)

    assert "19,000,000" in output  # Ana's balance off the 20,000,000 default


def test_build_dashboard_html_confirms_an_exact_match_when_calibrated_for_the_owner():
    # When starting_balance was calibrated FROM this owner's real balance,
    # their reconstructed figure matches exactly (diff == 0) -- the
    # disclosure must say so, not describe a gap that no longer exists.
    conn = db.init_db(":memory:")
    _populate(conn)
    db.set_sync_state(conn, "starting_balance", "18420000")
    db.set_sync_state(conn, "owner_user_id", "1")  # Ana is the account owner
    db.set_sync_state(conn, "owner_real_balance", "17420000")  # matches her computed balance

    output = dashboard.build_dashboard_html(conn)

    assert "coincide exacto" in output
    assert "17,420,000 EUR" in output


def test_build_dashboard_html_shows_the_real_balance_check_without_adjusting_the_calc():
    # When owner_real_balance is recorded but starting_balance was NOT
    # calibrated (e.g. an older sync, or calibration not yet applied), the
    # dashboard must disclose the resulting gap against the plain
    # reconstruction, not silently correct for it.
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

    # The translation dictionary embedded for the language switcher always carries
    # both disclosure templates, so check for the actual rendered element (its
    # data-i18n attribute) rather than the translated text, which is always present
    # somewhere in the page regardless of whether this disclosure is shown.
    assert 'data-i18n="disclosure_calibrated"' not in output
    assert 'data-i18n="disclosure_diff"' not in output


def test_build_dashboard_html_has_a_tab_for_each_section():
    conn = db.init_db(":memory:")
    _populate(conn)

    output = dashboard.build_dashboard_html(conn)

    for tab_id in ("resumen", "desglose", "movimientos", "plantillas", "jornada", "curiosidades"):
        assert f'id="btn-{tab_id}"' in output
        assert f'id="tab-{tab_id}"' in output


def test_build_dashboard_html_movements_selector_lists_every_manager():
    # Beto has zero money events in this fixture -- he must still get a
    # selector option and an (empty) panel, not be silently omitted.
    conn = db.init_db(":memory:")
    _populate(conn)

    output = dashboard.build_dashboard_html(conn)

    assert '<option value="1"' in output and "Ana (2 movimientos)" in output
    assert '<option value="2"' in output and "Beto (0 movimientos)" in output
    assert 'id="manager-movimientos-2"' in output
    assert "Sin movimientos todavia." in output


def test_build_dashboard_html_movements_tab_shows_the_net_total_per_manager():
    # Ana: +1,000,000 (roundFinished income) - 2,000,000 (market expense) = -1,000,000 net.
    conn = db.init_db(":memory:")
    _populate(conn)

    output = dashboard.build_dashboard_html(conn)

    assert "-1,000,000 EUR" in output  # net (a loss) -- only this summary line formats it with a bare minus


def test_build_dashboard_html_movements_tab_shows_positive_net_with_a_plus_sign():
    conn = db.init_db(":memory:")
    db.upsert_user(conn, 1, "Ana", "")
    db.insert_money_event(conn, {
        "id": "e1", "date": 100, "round_id": None, "type": "transfer", "user_id": 1,
        "counterparty_id": None, "player_id": 10, "amount": 5_000_000, "direction": "income",
        "reason_json": None,
    })
    db.insert_money_event(conn, {
        "id": "e2", "date": 200, "round_id": None, "type": "market", "user_id": 1,
        "counterparty_id": None, "player_id": 11, "amount": 1_000_000, "direction": "expense",
        "reason_json": None,
    })

    output = dashboard.build_dashboard_html(conn)

    assert "+4,000,000 EUR" in output  # net gain, 5,000,000 - 1,000,000


def test_build_dashboard_html_only_the_first_manager_panel_starts_active():
    conn = db.init_db(":memory:")
    _populate(conn)

    output = dashboard.build_dashboard_html(conn)

    assert 'class="manager-panel active" data-prefix="movimientos" id="manager-movimientos-1"' in output
    assert 'class="manager-panel" data-prefix="movimientos" id="manager-movimientos-2"' in output


def test_squads_tab_lists_players_with_position_team_and_price():
    conn = db.init_db(":memory:")
    _populate(conn)
    db.upsert_player(conn, 10, "Jugador A", "Equipo X", position=2)
    db.replace_squad(conn, 1, [{"player_id": 10, "price_paid": 3_500_000, "acquired_date": 100}])

    output = dashboard.build_dashboard_html(conn)

    assert "Defensa" in output
    assert "Jugador A" in output
    assert "3,500,000 EUR" in output
    assert 'id="manager-plantillas-1"' in output


def test_next_round_tab_falls_back_when_squad_has_no_eligible_players():
    conn = db.init_db(":memory:")
    _populate(conn)  # neither manager has any squad/player_form data

    output = dashboard.build_dashboard_html(conn)

    assert "No hay suficientes jugadores disponibles" in output


def test_next_round_tab_shows_market_profile_from_real_history():
    conn = db.init_db(":memory:")
    _populate(conn)  # Ana has one 2,000,000 EUR market purchase (e2)

    output = dashboard.build_dashboard_html(conn)

    assert "Gasto medio por fichaje" in output
    assert "2,000,000 EUR" in output


def test_jornadas_tab_highlights_each_managers_own_best_jornada():
    conn = db.init_db(":memory:")
    db.upsert_user(conn, 1, "Ana", "")
    db.upsert_standing(conn, 1, 60, 1)
    db.upsert_round(conn, 1, "Jornada 1", 100)
    db.upsert_round(conn, 2, "Jornada 2", 200)
    db.insert_money_event(conn, {
        "id": "e1", "date": 100, "round_id": 1, "type": "roundFinished", "user_id": 1,
        "counterparty_id": None, "player_id": None, "amount": 2_000_000, "direction": "income",
        "reason_json": "{}",
    })
    db.insert_money_event(conn, {
        "id": "e2", "date": 200, "round_id": 2, "type": "roundFinished", "user_id": 1,
        "counterparty_id": None, "player_id": None, "amount": 500_000, "direction": "income",
        "reason_json": "{}",
    })

    output = dashboard.build_dashboard_html(conn)

    # Ana's own best jornada (2,000,000) is highlighted; her worse one (500,000) isn't.
    assert '<td class="num cell-best">2,000,000 EUR</td>' in output
    assert '<td class="num">500,000 EUR</td>' in output
    assert 'id="manager-jornadas-1"' in output
    assert "Total ganado por puntos" in output
    assert "<strong>2,500,000 EUR</strong>" in output


def test_jornadas_tab_season_summary_ranks_managers_and_badges_the_leader():
    conn = db.init_db(":memory:")
    db.upsert_user(conn, 1, "Ana", "")
    db.upsert_user(conn, 2, "Beto", "")
    db.upsert_standing(conn, 1, 60, 1)
    db.upsert_standing(conn, 2, 40, 2)
    db.upsert_round(conn, 1, "Jornada 1", 100)
    db.insert_money_event(conn, {
        "id": "e1", "date": 100, "round_id": 1, "type": "roundFinished", "user_id": 1,
        "counterparty_id": None, "player_id": None, "amount": 2_000_000, "direction": "income",
        "reason_json": "{}",
    })
    db.insert_money_event(conn, {
        "id": "e2", "date": 100, "round_id": 1, "type": "roundFinished", "user_id": 2,
        "counterparty_id": None, "player_id": None, "amount": 500_000, "direction": "income",
        "reason_json": "{}",
    })

    output = dashboard.build_dashboard_html(conn)

    assert "Resumen de la temporada" in output
    assert "<strong>2,000,000 EUR</strong>" in output
    assert 'class="badge"' in output and ">Lider</span>" in output


def test_standings_and_jornadas_show_the_manager_avatar_when_icon_is_known():
    conn = db.init_db(":memory:")
    db.upsert_user(conn, 1, "Ana", "i/u/1.png?v=1")
    db.upsert_user(conn, 2, "Beto", "")  # no icon -- must degrade gracefully, not crash
    db.upsert_standing(conn, 1, 60, 1)
    db.upsert_standing(conn, 2, 40, 2)
    db.upsert_round(conn, 1, "Jornada 1", 100)
    db.insert_money_event(conn, {
        "id": "e1", "date": 100, "round_id": 1, "type": "roundFinished", "user_id": 1,
        "counterparty_id": None, "player_id": None, "amount": 1_000_000, "direction": "income",
        "reason_json": "{}",
    })

    output = dashboard.build_dashboard_html(conn)

    avatar_img = '<img class="avatar" src="https://cdn.biwenger.com/i/u/1.png?v=1"'
    assert output.count(avatar_img) >= 2  # at least standings + the Jornadas panel header


def test_movements_and_squads_show_player_photo_and_team_crest():
    conn = db.init_db(":memory:")
    db.upsert_user(conn, 1, "Ana", "")
    db.upsert_player(conn, 10, "Jugador A", "Equipo X", position=2, team_id=7)
    db.replace_squad(conn, 1, [{"player_id": 10, "price_paid": 100, "acquired_date": 5}])
    db.insert_money_event(conn, {
        "id": "e1", "date": 100, "round_id": None, "type": "market", "user_id": 1,
        "counterparty_id": None, "player_id": 10, "amount": 2_000_000, "direction": "expense",
        "reason_json": None,
    })

    output = dashboard.build_dashboard_html(conn)

    assert '<img class="player-photo" src="https://cdn.biwenger.com/i/p/10.png"' in output
    assert '<img class="crest" src="https://cdn.biwenger.com/i/t/7.png"' in output


def test_movement_without_a_player_shows_no_player_icons():
    conn = db.init_db(":memory:")
    db.upsert_user(conn, 1, "Ana", "")
    db.upsert_round(conn, 1, "Jornada 1", 100)
    db.insert_money_event(conn, {
        "id": "e1", "date": 100, "round_id": 1, "type": "roundFinished", "user_id": 1,
        "counterparty_id": None, "player_id": None, "amount": 1_000_000, "direction": "income",
        "reason_json": "{}",
    })

    output = dashboard.build_dashboard_html(conn)

    assert '<span class="player-icons">' not in output


def test_login_gate_hides_the_dashboard_behind_a_password_form():
    conn = db.init_db(":memory:")
    _populate(conn)

    output = dashboard.build_dashboard_html(conn)

    assert 'id="loginGate"' in output
    # The real content starts hidden -- unlocking it is a client-side JS toggle,
    # not a server-side check, so it's a casual-visitor deterrent only. The data
    # itself is still present in this same HTML regardless (see main.py comment).
    assert 'id="mainContainer" style="display:none"' in output
    assert 'id="loginUser"' in output and 'id="loginPass"' in output
