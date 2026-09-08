"""Derived views over stored money events: balances, points, curious facts."""
from collections import defaultdict

STARTING_BALANCE = 20_000_000


def compute_balance_timeline(money_events, starting_balance=STARTING_BALANCE):
    """Return {user_id: [(date, balance), ...]}, sorted by date, running totals."""
    by_user = defaultdict(list)
    for event in sorted(money_events, key=lambda e: e["date"]):
        by_user[event["user_id"]].append(event)

    timelines = {}
    for user_id, events in by_user.items():
        balance = starting_balance
        series = []
        for event in events:
            if event["direction"] == "income":
                balance += event["amount"]
            else:
                balance -= event["amount"]
            series.append((event["date"], balance))
        timelines[user_id] = series
    return timelines


def compute_current_balances(money_events, starting_balance=STARTING_BALANCE):
    """Return {user_id: balance} as of the latest known event per user."""
    timelines = compute_balance_timeline(money_events, starting_balance)
    return {user_id: series[-1][1] for user_id, series in timelines.items() if series}


def compute_points_timeline(round_points, rounds):
    """Return {user_id: [(round_date, cumulative_points), ...]} in round-date order."""
    round_dates = {r["id"]: r["date"] for r in rounds}
    by_user = defaultdict(list)
    for entry in round_points:
        date = round_dates.get(entry["round_id"])
        by_user[entry["user_id"]].append((date, entry["points"]))

    timelines = {}
    for user_id, entries in by_user.items():
        entries.sort(key=lambda e: (e[0] is None, e[0]))
        cumulative = 0
        series = []
        for date, points in entries:
            cumulative += points
            series.append((date, cumulative))
        timelines[user_id] = series
    return timelines


def _user_name(users_by_id, user_id):
    return users_by_id.get(user_id, {}).get("name", f"Usuario {user_id}")


def player_name(players, player_id):
    if player_id is None:
        return None
    return players.get(player_id, {}).get("name", f"Jugador {player_id}")


def compute_curious_facts(money_events, players, users):
    """Return a dict of notable facts derived from the money events."""
    users_by_id = {u["id"]: u for u in users}
    facts = {}

    sales = [e for e in money_events if e["type"] == "transfer" and e["direction"] == "income"]
    if sales:
        best_sale = max(sales, key=lambda e: e["amount"])
        facts["most_expensive_sale"] = {
            "user": _user_name(users_by_id, best_sale["user_id"]),
            "player": player_name(players, best_sale["player_id"]),
            "amount": best_sale["amount"],
            "date": best_sale["date"],
        }

    purchases = [e for e in money_events if e["type"] in ("market", "transfer") and e["direction"] == "expense"]
    if purchases:
        best_purchase = max(purchases, key=lambda e: e["amount"])
        facts["most_expensive_purchase"] = {
            "user": _user_name(users_by_id, best_purchase["user_id"]),
            "player": player_name(players, best_purchase["player_id"]),
            "amount": best_purchase["amount"],
            "date": best_purchase["date"],
        }

    bonuses = [e for e in money_events if e["type"] == "roundFinished"]
    if bonuses:
        best_bonus = max(bonuses, key=lambda e: e["amount"])
        facts["biggest_round_bonus"] = {
            "user": _user_name(users_by_id, best_bonus["user_id"]),
            "amount": best_bonus["amount"],
            "date": best_bonus["date"],
        }

    trade_counts = defaultdict(int)
    for event in money_events:
        if event["type"] in ("market", "transfer"):
            trade_counts[event["user_id"]] += 1
    if trade_counts:
        most_active_id = max(trade_counts, key=trade_counts.get)
        facts["most_active_trader"] = {
            "user": _user_name(users_by_id, most_active_id),
            "movements": trade_counts[most_active_id],
        }

    purchases_by_user_player = defaultdict(list)
    sales_by_user_player = defaultdict(list)
    for event in money_events:
        if event["player_id"] is None:
            continue
        key = (event["user_id"], event["player_id"])
        if event["direction"] == "expense" and event["type"] in ("market", "transfer"):
            purchases_by_user_player[key].append(event)
        elif event["direction"] == "income" and event["type"] == "transfer":
            sales_by_user_player[key].append(event)

    flips = []
    for key, buys in purchases_by_user_player.items():
        sells = sales_by_user_player.get(key, [])
        if not sells:
            continue
        buy = min(buys, key=lambda e: e["date"])
        later_sells = [s for s in sells if s["date"] > buy["date"]]
        if not later_sells:
            continue
        sell = max(later_sells, key=lambda e: e["date"])
        flips.append({
            "user_id": key[0],
            "player_id": key[1],
            "profit": sell["amount"] - buy["amount"],
            "buy_amount": buy["amount"],
            "sell_amount": sell["amount"],
        })
    if flips:
        best_flip = max(flips, key=lambda f: f["profit"])
        facts["best_flip"] = {
            "user": _user_name(users_by_id, best_flip["user_id"]),
            "player": player_name(players, best_flip["player_id"]),
            "profit": best_flip["profit"],
            "buy_amount": best_flip["buy_amount"],
            "sell_amount": best_flip["sell_amount"],
        }

    return facts


def compute_income_breakdown(money_events, users):
    """Return {user_id: {"points": int, "sales": int, "purchases": int}}."""
    breakdown = {u["id"]: {"points": 0, "sales": 0, "purchases": 0} for u in users}
    for event in money_events:
        entry = breakdown.setdefault(event["user_id"], {"points": 0, "sales": 0, "purchases": 0})
        if event["type"] == "roundFinished":
            entry["points"] += event["amount"]
        elif event["type"] == "transfer" and event["direction"] == "income":
            entry["sales"] += event["amount"]
        elif event["direction"] == "expense":
            entry["purchases"] += event["amount"]
    return breakdown


def compute_biggest_bonus_round(money_events, rounds):
    """Return the round with the highest total roundFinished payout, or None."""
    round_names = {r["id"]: r["name"] for r in rounds}
    totals = defaultdict(int)
    for event in money_events:
        if event["type"] == "roundFinished" and event["round_id"] is not None:
            totals[event["round_id"]] += event["amount"]
    if not totals:
        return None
    best_round_id = max(totals, key=totals.get)
    return {
        "round": round_names.get(best_round_id, f"Jornada {best_round_id}"),
        "total": totals[best_round_id],
    }
