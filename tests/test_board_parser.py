import json

from board_parser import parse_board_page


def test_parses_transfer_sale_to_market():
    items = [{
        "type": "transfer",
        "content": [{
            "player": 23572,
            "from": {"id": 12686032, "name": "Giotto di Bondone"},
            "amount": 378000,
        }],
        "date": 1788845299,
    }]

    result = parse_board_page(items)

    assert len(result["money_events"]) == 1
    event = result["money_events"][0]
    assert event["type"] == "transfer"
    assert event["user_id"] == 12686032
    assert event["counterparty_id"] is None
    assert event["player_id"] == 23572
    assert event["amount"] == 378000
    assert event["direction"] == "income"


def test_parses_direct_transfer_between_users():
    items = [{
        "type": "transfer",
        "content": [{
            "player": 27715,
            "from": {"id": 12684091, "name": "Real Papa sin Merva CF"},
            "to": {"id": 12683799, "name": "Cerveceria Gaira"},
            "amount": 200000,
        }],
        "date": 1788800000,
    }]

    result = parse_board_page(items)

    assert len(result["money_events"]) == 2
    income = next(e for e in result["money_events"] if e["direction"] == "income")
    expense = next(e for e in result["money_events"] if e["direction"] == "expense")
    assert income["user_id"] == 12684091
    assert income["counterparty_id"] == 12683799
    assert income["amount"] == 200000
    assert expense["user_id"] == 12683799
    assert expense["counterparty_id"] == 12684091
    assert expense["amount"] == 200000
    assert income["id"] != expense["id"]


def test_parses_market_purchase_with_multiple_items():
    items = [{
        "type": "market",
        "content": [
            {"player": 18128, "to": {"id": 12683799, "name": "A"}, "amount": 1960000},
            {"player": 26095, "to": {"id": 12686419, "name": "B"}, "amount": 2640000},
        ],
        "date": 1788843853,
    }]

    result = parse_board_page(items)

    assert len(result["money_events"]) == 2
    first = result["money_events"][0]
    assert first["type"] == "market"
    assert first["user_id"] == 12683799
    assert first["direction"] == "expense"
    assert first["amount"] == 1960000
    assert first["player_id"] == 18128
    assert result["money_events"][0]["id"] != result["money_events"][1]["id"]


def test_parses_round_finished_bonus_and_points():
    items = [{
        "type": "roundFinished",
        "content": {
            "round": {"id": 4902, "name": "Jornada 4"},
            "results": [
                {
                    "user": {"id": 12686032, "name": "Giotto di Bondone"},
                    "points": 76,
                    "bonus": 2325000,
                    "reason": {"bonusPoint": 875000, "bonusFixed": 500000},
                },
                {
                    "user": {"id": 12683880, "name": "Glotto di Bondone"},
                    "points": 54,
                    "bonus": 1655000,
                    "reason": {"bonusPoint": 1155000, "bonusFixed": 500000},
                },
            ],
        },
        "date": 1788700000,
    }]

    result = parse_board_page(items)

    assert result["rounds"] == [{"id": 4902, "name": "Jornada 4", "date": 1788700000}]
    assert len(result["round_points"]) == 2
    assert {"round_id": 4902, "user_id": 12686032, "points": 76} in result["round_points"]

    money = result["money_events"]
    assert len(money) == 2
    first = next(e for e in money if e["user_id"] == 12686032)
    assert first["amount"] == 2325000
    assert first["direction"] == "income"
    assert first["round_id"] == 4902
    assert json.loads(first["reason_json"]) == {"bonusPoint": 875000, "bonusFixed": 500000}


def test_ignores_unrelated_event_types():
    items = [{"type": "playerMovements", "content": [{"type": "join", "player": 1}], "date": 123}]

    result = parse_board_page(items)

    assert result == {"money_events": [], "round_points": [], "rounds": []}


def test_parse_board_page_handles_empty_list():
    assert parse_board_page([]) == {"money_events": [], "round_points": [], "rounds": []}
