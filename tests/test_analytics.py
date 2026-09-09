import json

from analytics import (
    compute_balance_timeline,
    compute_biggest_bonus_round,
    compute_curious_facts,
    compute_current_balances,
    compute_income_breakdown,
    compute_market_profile,
    compute_points_timeline,
    compute_round_bonus_table,
    compute_squad_table,
    recommend_lineup,
)


def _event(user_id, amount, direction, date, type="market", counterparty_id=None, player_id=None):
    return {
        "id": f"{user_id}-{date}-{direction}-{type}", "date": date, "round_id": None,
        "type": type, "user_id": user_id, "counterparty_id": counterparty_id,
        "player_id": player_id, "amount": amount, "direction": direction,
        "reason_json": None,
    }


def test_balance_timeline_starts_at_20m_and_accumulates():
    events = [
        _event(1, 1_000_000, "expense", 100, type="market"),
        _event(1, 2_000_000, "income", 200, type="transfer"),
    ]
    timeline = compute_balance_timeline(events)
    assert timeline[1] == [(100, 19_000_000), (200, 21_000_000)]


def test_balance_timeline_sorts_by_date_regardless_of_input_order():
    events = [
        _event(1, 500_000, "income", 300, type="transfer"),
        _event(1, 1_000_000, "expense", 100, type="market"),
    ]
    timeline = compute_balance_timeline(events)
    assert timeline[1] == [(100, 19_000_000), (300, 19_500_000)]


def test_balance_timeline_tracks_multiple_users_independently():
    events = [
        _event(1, 1_000_000, "expense", 100, type="market"),
        _event(2, 500_000, "income", 100, type="transfer"),
    ]
    timeline = compute_balance_timeline(events)
    assert timeline[1] == [(100, 19_000_000)]
    assert timeline[2] == [(100, 20_500_000)]


def test_compute_current_balances_returns_latest_value():
    events = [
        _event(1, 1_000_000, "expense", 100, type="market"),
        _event(1, 2_000_000, "income", 200, type="transfer"),
    ]
    assert compute_current_balances(events) == {1: 21_000_000}


def test_compute_current_balances_returns_empty_for_no_events():
    assert compute_current_balances([]) == {}


def test_points_timeline_accumulates_across_rounds_in_date_order():
    rounds = [{"id": 1, "name": "J1", "date": 100}, {"id": 2, "name": "J2", "date": 200}]
    round_points = [
        {"round_id": 2, "user_id": 1, "points": 30},
        {"round_id": 1, "user_id": 1, "points": 50},
    ]
    timeline = compute_points_timeline(round_points, rounds)
    assert timeline[1] == [(100, 50), (200, 80)]


def test_points_timeline_tracks_multiple_users_independently():
    rounds = [{"id": 1, "name": "J1", "date": 100}]
    round_points = [
        {"round_id": 1, "user_id": 1, "points": 50},
        {"round_id": 1, "user_id": 2, "points": 30},
    ]
    timeline = compute_points_timeline(round_points, rounds)
    assert timeline[1] == [(100, 50)]
    assert timeline[2] == [(100, 30)]


def test_curious_facts_most_expensive_sale_and_purchase():
    events = [
        _event(1, 500_000, "income", 100, type="transfer", player_id=10),
        _event(2, 2_000_000, "expense", 100, type="market", player_id=11),
    ]
    players = {10: {"name": "Jugador A", "team": "X"}, 11: {"name": "Jugador B", "team": "Y"}}
    users = [{"id": 1, "name": "Ana", "icon": ""}, {"id": 2, "name": "Beto", "icon": ""}]

    facts = compute_curious_facts(events, players, users)

    assert facts["most_expensive_sale"]["user"] == "Ana"
    assert facts["most_expensive_sale"]["player"] == "Jugador A"
    assert facts["most_expensive_sale"]["amount"] == 500_000
    assert facts["most_expensive_purchase"]["user"] == "Beto"
    assert facts["most_expensive_purchase"]["amount"] == 2_000_000


def test_curious_facts_biggest_round_bonus():
    events = [{
        "id": "a", "date": 100, "round_id": 1, "type": "roundFinished",
        "user_id": 1, "counterparty_id": None, "player_id": None,
        "amount": 2_000_000, "direction": "income",
        "reason_json": json.dumps({"bonusPoint": 2_000_000}),
    }]
    users = [{"id": 1, "name": "Ana", "icon": ""}]

    facts = compute_curious_facts(events, {}, users)

    assert facts["biggest_round_bonus"] == {"user": "Ana", "amount": 2_000_000, "date": 100}


def test_curious_facts_most_active_trader():
    events = [
        _event(1, 100, "expense", 10, type="market"),
        _event(1, 100, "expense", 20, type="market"),
        _event(2, 100, "expense", 30, type="market"),
    ]
    users = [{"id": 1, "name": "Ana", "icon": ""}, {"id": 2, "name": "Beto", "icon": ""}]

    facts = compute_curious_facts(events, {}, users)

    assert facts["most_active_trader"] == {"user": "Ana", "movements": 2}


def test_curious_facts_best_flip_matches_buy_then_later_sell_of_same_player():
    events = [
        _event(1, 1_000_000, "expense", 100, type="market", player_id=10),
        _event(1, 3_000_000, "income", 200, type="transfer", player_id=10),
    ]
    users = [{"id": 1, "name": "Ana", "icon": ""}]
    players = {10: {"name": "Jugador A", "team": "X"}}

    facts = compute_curious_facts(events, players, users)

    assert facts["best_flip"] == {
        "user": "Ana", "player": "Jugador A", "profit": 2_000_000,
        "buy_amount": 1_000_000, "sell_amount": 3_000_000,
    }


def test_curious_facts_best_flip_ignores_sale_dated_before_purchase():
    events = [
        _event(1, 3_000_000, "income", 100, type="transfer", player_id=10),
        _event(1, 1_000_000, "expense", 200, type="market", player_id=10),
    ]
    users = [{"id": 1, "name": "Ana", "icon": ""}]
    players = {10: {"name": "Jugador A", "team": "X"}}

    facts = compute_curious_facts(events, players, users)

    assert "best_flip" not in facts


def test_curious_facts_returns_empty_dict_for_no_events():
    assert compute_curious_facts([], {}, []) == {}


def test_income_breakdown_separates_points_sales_and_purchases():
    users = [{"id": 1, "name": "Ana", "icon": ""}]
    events = [
        {
            "id": "a", "date": 100, "round_id": 1, "type": "roundFinished", "user_id": 1,
            "counterparty_id": None, "player_id": None, "amount": 1_000_000,
            "direction": "income", "reason_json": "{}",
        },
        _event(1, 500_000, "income", 200, type="transfer", player_id=10),
        _event(1, 300_000, "expense", 300, type="market", player_id=11),
    ]

    breakdown = compute_income_breakdown(events, users)

    assert breakdown[1] == {"points": 1_000_000, "sales": 500_000, "purchases": 300_000}


def test_income_breakdown_includes_users_with_no_events():
    users = [{"id": 1, "name": "Ana", "icon": ""}, {"id": 2, "name": "Beto", "icon": ""}]
    breakdown = compute_income_breakdown([], users)
    assert breakdown == {
        1: {"points": 0, "sales": 0, "purchases": 0},
        2: {"points": 0, "sales": 0, "purchases": 0},
    }


def test_biggest_bonus_round_sums_all_managers_per_round():
    rounds = [{"id": 1, "name": "Jornada 1", "date": 100}, {"id": 2, "name": "Jornada 2", "date": 200}]
    events = [
        {"id": "a", "date": 100, "round_id": 1, "type": "roundFinished", "user_id": 1,
         "counterparty_id": None, "player_id": None, "amount": 1_000_000, "direction": "income", "reason_json": "{}"},
        {"id": "b", "date": 100, "round_id": 1, "type": "roundFinished", "user_id": 2,
         "counterparty_id": None, "player_id": None, "amount": 1_200_000, "direction": "income", "reason_json": "{}"},
        {"id": "c", "date": 200, "round_id": 2, "type": "roundFinished", "user_id": 1,
         "counterparty_id": None, "player_id": None, "amount": 900_000, "direction": "income", "reason_json": "{}"},
    ]

    result = compute_biggest_bonus_round(events, rounds)

    assert result == {"round": "Jornada 1", "total": 2_200_000}


def test_biggest_bonus_round_returns_none_when_no_round_finished_events():
    assert compute_biggest_bonus_round([], []) is None


def test_round_bonus_table_returns_one_row_per_round_sorted_by_date():
    rounds = [
        {"id": 2, "name": "Jornada 2", "date": 200},
        {"id": 1, "name": "Jornada 1", "date": 100},
    ]
    events = [
        {"id": "a", "date": 100, "round_id": 1, "type": "roundFinished", "user_id": 1,
         "counterparty_id": None, "player_id": None, "amount": 1_000_000, "direction": "income", "reason_json": "{}"},
        {"id": "b", "date": 100, "round_id": 1, "type": "roundFinished", "user_id": 2,
         "counterparty_id": None, "player_id": None, "amount": 1_200_000, "direction": "income", "reason_json": "{}"},
        {"id": "c", "date": 200, "round_id": 2, "type": "roundFinished", "user_id": 1,
         "counterparty_id": None, "player_id": None, "amount": 900_000, "direction": "income", "reason_json": "{}"},
    ]

    result = compute_round_bonus_table(events, rounds)

    assert [r["round_id"] for r in result] == [1, 2]
    assert result[0]["name"] == "Jornada 1"
    assert result[0]["amounts"] == {1: 1_000_000, 2: 1_200_000}
    assert result[1]["name"] == "Jornada 2"
    assert result[1]["amounts"] == {1: 900_000}


def test_round_bonus_table_ignores_non_round_finished_events():
    rounds = [{"id": 1, "name": "Jornada 1", "date": 100}]
    events = [
        {"id": "a", "date": 100, "round_id": 1, "type": "roundFinished", "user_id": 1,
         "counterparty_id": None, "player_id": None, "amount": 1_000_000, "direction": "income", "reason_json": "{}"},
        {"id": "b", "date": 100, "round_id": None, "type": "market", "user_id": 1,
         "counterparty_id": None, "player_id": 5, "amount": 500_000, "direction": "expense", "reason_json": None},
    ]

    result = compute_round_bonus_table(events, rounds)

    assert len(result) == 1
    assert result[0]["amounts"] == {1: 1_000_000}


def test_round_bonus_table_falls_back_to_a_placeholder_name_for_an_unknown_round():
    events = [
        {"id": "a", "date": 100, "round_id": 99, "type": "roundFinished", "user_id": 1,
         "counterparty_id": None, "player_id": None, "amount": 500_000, "direction": "income", "reason_json": "{}"},
    ]

    result = compute_round_bonus_table(events, rounds=[])

    assert result == [{"round_id": 99, "name": "Jornada 99", "date": None, "amounts": {1: 500_000}}]


def test_round_bonus_table_returns_empty_list_for_no_events():
    assert compute_round_bonus_table([], []) == []


def test_squad_table_groups_by_manager_and_sorts_gk_before_outfielders():
    squads = [
        {"user_id": 1, "player_id": 10, "price_paid": 100, "acquired_date": 5},
        {"user_id": 1, "player_id": 20, "price_paid": None, "acquired_date": 1},
    ]
    players = {
        10: {"name": "Zeta", "team": "X", "position": 3},
        20: {"name": "Alfa", "team": "Y", "position": 1},
    }

    result = compute_squad_table(squads, players)

    assert [row["name"] for row in result[1]] == ["Alfa", "Zeta"]
    assert result[1][0]["price_paid"] is None


def test_squad_table_falls_back_to_a_placeholder_name_for_an_unknown_player():
    squads = [{"user_id": 1, "player_id": 10, "price_paid": 100, "acquired_date": 5}]

    result = compute_squad_table(squads, players={})

    assert result[1][0]["name"] == "Jugador 10"


def _form(recent_points, status="ok"):
    return {"recent_points": recent_points, "status": status}


def test_recommend_lineup_picks_the_only_feasible_formation():
    # Exactly enough for 4-4-2 (1 GK + 4 DF + 4 MF + 2 FW = 11) and short on
    # defenders/forwards for every other supported formation.
    players = {1: {"name": "GK1", "position": 1}}
    player_form = {1: _form([5])}
    for i in range(2, 6):
        players[i] = {"name": f"DF{i}", "position": 2}
        player_form[i] = _form([3])
    for i in range(6, 10):
        players[i] = {"name": f"MF{i}", "position": 3}
        player_form[i] = _form([4])
    players[10] = {"name": "FW10", "position": 4}
    player_form[10] = _form([10])
    players[11] = {"name": "FW11", "position": 4}
    player_form[11] = _form([2])

    result = recommend_lineup(squad_player_ids=list(players), players=players, player_form=player_form)

    assert result["formation"] == "4-4-2"
    assert len(result["starters"]) == 11
    assert result["captain"]["player_id"] == 10  # FW10, highest avg (10.0)
    assert result["total_points"] == 5 + 3 * 4 + 4 * 4 + 10 + 2


def test_recommend_lineup_excludes_players_not_marked_ok():
    players = {1: {"name": "GK1", "position": 1}, 2: {"name": "GK2", "position": 1}}
    player_form = {1: _form([1], status="injured"), 2: _form([9], status="ok")}

    result = recommend_lineup(squad_player_ids=[1, 2], players=players, player_form=player_form)

    assert result is None  # only one eligible GK and no outfielders at all


def test_recommend_lineup_ignores_non_numeric_fitness_entries():
    # Biwenger's per-round "fitness" can hold None or a status string like "doubt"
    # instead of a score for a round the player didn't play -- confirmed live.
    players = {1: {"name": "GK1", "position": 1}}
    player_form = {1: _form([5, None, "doubt", "injured"])}
    for i in range(2, 6):
        players[i] = {"name": f"DF{i}", "position": 2}
        player_form[i] = _form([3])
    for i in range(6, 10):
        players[i] = {"name": f"MF{i}", "position": 3}
        player_form[i] = _form([4])
    for i in (10, 11):
        players[i] = {"name": f"FW{i}", "position": 4}
        player_form[i] = _form([2])

    result = recommend_lineup(squad_player_ids=list(players), players=players, player_form=player_form)

    gk_avg = next(p["avg_points"] for p in result["starters"] if p["player_id"] == 1)
    assert gk_avg == 5.0  # None/"doubt"/"injured" excluded, only the real 5 counts


def test_recommend_lineup_returns_none_without_a_fit_goalkeeper():
    players = {1: {"name": "GK1", "position": 1}}
    player_form = {1: _form([5], status="injured")}

    assert recommend_lineup(squad_player_ids=[1], players=players, player_form=player_form) is None


def test_market_profile_computes_averages_cash_and_recent_activity():
    day = 86400
    events = [
        _event(1, 1_000, "expense", date=0, type="market"),
        _event(1, 3_000, "expense", date=1, type="market"),
        _event(1, 2_000, "income", date=2, type="transfer"),
        _event(1, 500, "income", date=20 * day, type="roundFinished"),  # not a trade
        _event(1, 900, "expense", date=20 * day, type="market"),  # inside the 14-day window
    ]
    users = [{"id": 1}]
    current_balances = {1: 12_345}

    profile = compute_market_profile(events, users, current_balances, now=20 * day)

    assert profile[1]["cash"] == 12_345
    assert profile[1]["total_trades"] == 4  # 3 purchases + 1 sale, excludes the roundFinished
    assert profile[1]["avg_purchase"] == round((1_000 + 3_000 + 900) / 3)
    assert profile[1]["avg_sale"] == 2_000
    assert profile[1]["recent_trades"] == 1  # only the date==20*day market expense


def test_market_profile_includes_users_with_no_trades():
    profile = compute_market_profile([], users=[{"id": 1}], current_balances={})

    assert profile == {1: {"cash": 0, "total_trades": 0, "avg_purchase": 0, "avg_sale": 0, "recent_trades": 0}}
