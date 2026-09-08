from analytics import (
    compute_balance_timeline,
    compute_current_balances,
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
