import json

from analytics import (
    compute_balance_timeline,
    compute_biggest_bonus_round,
    compute_curious_facts,
    compute_current_balances,
    compute_income_breakdown,
    compute_points_timeline,
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
