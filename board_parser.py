"""Parse Biwenger league board (activity feed) items into structured records."""
import hashlib
import json


def _event_id(date, type_, index, direction, user_id):
    raw = f"{date}:{type_}:{index}:{direction}:{user_id}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def parse_board_page(items):
    """Parse a page of raw board items from GET /league/{id}/board.

    Returns {"money_events": [...], "round_points": [...], "rounds": [...]}.
    """
    money_events = []
    round_points = []
    rounds = []

    for item in items:
        item_type = item.get("type")
        date = item.get("date")

        if item_type == "roundFinished":
            content = item.get("content") or {}
            round_info = content.get("round") or {}
            round_id = round_info.get("id")
            if round_id is not None:
                rounds.append({
                    "id": round_id,
                    "name": round_info.get("name"),
                    "date": date,
                })
            for result in content.get("results", []):
                user = result.get("user") or {}
                user_id = user.get("id")
                if user_id is None:
                    continue
                round_points.append({
                    "round_id": round_id,
                    "user_id": user_id,
                    "points": result.get("points", 0),
                })
                money_events.append({
                    "id": _event_id(date, "roundFinished", round_id, "income", user_id),
                    "date": date,
                    "round_id": round_id,
                    "type": "roundFinished",
                    "user_id": user_id,
                    "counterparty_id": None,
                    "player_id": None,
                    "amount": result.get("bonus", 0),
                    "direction": "income",
                    "reason_json": json.dumps(result.get("reason", {})),
                })

        elif item_type == "transfer":
            for index, movement in enumerate(item.get("content") or []):
                from_user = movement.get("from") or {}
                to_user = movement.get("to")
                from_id = from_user.get("id")
                amount = movement.get("amount", 0)
                player_id = movement.get("player")
                if from_id is not None:
                    counterparty_id = to_user.get("id") if to_user else None
                    money_events.append({
                        "id": _event_id(date, "transfer", index, "income", from_id),
                        "date": date,
                        "round_id": None,
                        "type": "transfer",
                        "user_id": from_id,
                        "counterparty_id": counterparty_id,
                        "player_id": player_id,
                        "amount": amount,
                        "direction": "income",
                        "reason_json": None,
                    })
                if to_user is not None:
                    to_id = to_user.get("id")
                    money_events.append({
                        "id": _event_id(date, "transfer", index, "expense", to_id),
                        "date": date,
                        "round_id": None,
                        "type": "transfer",
                        "user_id": to_id,
                        "counterparty_id": from_id,
                        "player_id": player_id,
                        "amount": amount,
                        "direction": "expense",
                        "reason_json": None,
                    })

        elif item_type == "market":
            for index, movement in enumerate(item.get("content") or []):
                to_user = movement.get("to") or {}
                to_id = to_user.get("id")
                if to_id is None:
                    continue
                money_events.append({
                    "id": _event_id(date, "market", index, "expense", to_id),
                    "date": date,
                    "round_id": None,
                    "type": "market",
                    "user_id": to_id,
                    "counterparty_id": None,
                    "player_id": movement.get("player"),
                    "amount": movement.get("amount", 0),
                    "direction": "expense",
                    "reason_json": None,
                })

        # other types (playerMovements, text, adminText, roundStarted,
        # bettingPool, leagueSettings) carry no money information.

    return {"money_events": money_events, "round_points": round_points, "rounds": rounds}
