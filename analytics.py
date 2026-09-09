"""Derived views over stored money events: balances, points, curious facts."""
import time
from collections import defaultdict

STARTING_BALANCE = 20_000_000

# Biwenger position codes, confirmed live against the real API.
POSITION_GK, POSITION_DF, POSITION_MF, POSITION_FW = 1, 2, 3, 4
POSITION_ORDER = {POSITION_GK: 0, POSITION_DF: 1, POSITION_MF: 2, POSITION_FW: 3}

# Formation -> required count per outfield line; goalkeeper is always exactly 1.
FORMATIONS = {
    "4-4-2": {POSITION_DF: 4, POSITION_MF: 4, POSITION_FW: 2},
    "4-3-3": {POSITION_DF: 4, POSITION_MF: 3, POSITION_FW: 3},
    "3-5-2": {POSITION_DF: 3, POSITION_MF: 5, POSITION_FW: 2},
    "3-4-3": {POSITION_DF: 3, POSITION_MF: 4, POSITION_FW: 3},
    "5-3-2": {POSITION_DF: 5, POSITION_MF: 3, POSITION_FW: 2},
    "5-4-1": {POSITION_DF: 5, POSITION_MF: 4, POSITION_FW: 1},
}

RECENT_ACTIVITY_WINDOW_SECONDS = 14 * 24 * 3600


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


def compute_running_balances(money_events, starting_balance=STARTING_BALANCE):
    """Return {event_id: balance_after}, replaying each user's events in date order."""
    by_user = defaultdict(list)
    for event in sorted(money_events, key=lambda e: e["date"]):
        by_user[event["user_id"]].append(event)

    balances = {}
    for events in by_user.values():
        balance = starting_balance
        for event in events:
            if event["direction"] == "income":
                balance += event["amount"]
            else:
                balance -= event["amount"]
            balances[event["id"]] = balance
    return balances


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


def compute_round_bonus_table(money_events, rounds):
    """Return a list of rounds (sorted by date) with each manager's jornada
    bonus for that round: [{"round_id", "name", "date", "amounts": {user_id: amount}}].

    Only roundFinished events contribute; a round with no known metadata (not
    in `rounds`) still gets a row, with a placeholder name.
    """
    round_info = {r["id"]: r for r in rounds}
    amounts_by_round = defaultdict(dict)
    for event in money_events:
        if event["type"] == "roundFinished" and event["round_id"] is not None:
            amounts_by_round[event["round_id"]][event["user_id"]] = event["amount"]

    rows = []
    for round_id, amounts in amounts_by_round.items():
        info = round_info.get(round_id, {})
        rows.append({
            "round_id": round_id,
            "name": info.get("name") or f"Jornada {round_id}",
            "date": info.get("date"),
            "amounts": amounts,
        })
    rows.sort(key=lambda r: (r["date"] is None, r["date"]))
    return rows


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


def compute_squad_table(squads, players):
    """Return {user_id: [{"player_id","name","team","position","price_paid",
    "acquired_date"}, ...]}, one list per manager, sorted GK -> DF -> MF -> FW
    then by name."""
    by_user = defaultdict(list)
    for entry in squads:
        info = players.get(entry["player_id"], {})
        by_user[entry["user_id"]].append({
            "player_id": entry["player_id"],
            "name": info.get("name") or f"Jugador {entry['player_id']}",
            "team": info.get("team"),
            "position": info.get("position"),
            "price_paid": entry["price_paid"],
            "acquired_date": entry["acquired_date"],
        })
    for rows in by_user.values():
        rows.sort(key=lambda r: (POSITION_ORDER.get(r["position"], 99), r["name"]))
    return dict(by_user)


def _average_recent_points(recent_points):
    # Biwenger's per-round "fitness" entries can be None (round not played) or a
    # status string like "doubt"/"injured" instead of a score -- confirmed live.
    numeric = [p for p in recent_points if isinstance(p, (int, float)) and not isinstance(p, bool)]
    return sum(numeric) / len(numeric) if numeric else 0.0


def recommend_lineup(squad_player_ids, players, player_form):
    """Suggest the strongest starting XI for one manager's squad ahead of the
    next round, using each eligible player's average recent score as signal.

    This is a data-driven SUGGESTION of the statistically strongest lineup
    given the real squad -- not a claim about what the manager will actually
    set (Biwenger only exposes a manager's real lineup once the round has
    already started, never before).

    Returns {"formation", "starters", "captain", "total_points"}, or None if
    the squad doesn't have enough eligible players (status == "ok") for ANY
    supported formation (e.g. no fit goalkeeper, or too few defenders).
    """
    by_position = defaultdict(list)
    for player_id in squad_player_ids:
        form = player_form.get(player_id, {})
        if form.get("status", "ok") != "ok":
            continue
        info = players.get(player_id, {})
        by_position[info.get("position")].append({
            "player_id": player_id,
            "name": info.get("name") or f"Jugador {player_id}",
            "position": info.get("position"),
            "avg_points": _average_recent_points(form.get("recent_points", [])),
        })
    for group in by_position.values():
        group.sort(key=lambda p: p["avg_points"], reverse=True)

    goalkeepers = by_position.get(POSITION_GK, [])
    if not goalkeepers:
        return None

    best = None
    for formation, quotas in FORMATIONS.items():
        starters = [goalkeepers[0]]
        feasible = True
        for position, count in quotas.items():
            candidates = by_position.get(position, [])
            if len(candidates) < count:
                feasible = False
                break
            starters.extend(candidates[:count])
        if not feasible:
            continue

        total_points = round(sum(p["avg_points"] for p in starters), 2)
        if best is None or total_points > best["total_points"]:
            captain = max(starters, key=lambda p: p["avg_points"])
            best = {
                "formation": formation,
                "starters": starters,
                "captain": captain,
                "total_points": total_points,
            }
    return best


def compute_market_profile(money_events, users, current_balances, now=None):
    """Return {user_id: {"cash", "total_trades", "avg_purchase", "avg_sale",
    "recent_trades"}}, one entry per manager, describing their REAL past
    market behaviour.

    This describes what already happened -- it is NOT a prediction of which
    player a manager will buy next or how much they'll bid, since Biwenger
    exposes no signal at all for another manager's buying intent.
    """
    if now is None:
        now = time.time()
    cutoff = now - RECENT_ACTIVITY_WINDOW_SECONDS

    purchases = defaultdict(list)
    sales = defaultdict(list)
    recent_trades = defaultdict(int)
    for event in money_events:
        if event["type"] not in ("market", "transfer"):
            continue
        if event["direction"] == "expense":
            purchases[event["user_id"]].append(event["amount"])
        elif event["type"] == "transfer":
            sales[event["user_id"]].append(event["amount"])
        if event["date"] >= cutoff:
            recent_trades[event["user_id"]] += 1

    profile = {}
    for user in users:
        user_id = user["id"]
        user_purchases = purchases.get(user_id, [])
        user_sales = sales.get(user_id, [])
        profile[user_id] = {
            "cash": current_balances.get(user_id, 0),
            "total_trades": len(user_purchases) + len(user_sales),
            "avg_purchase": round(sum(user_purchases) / len(user_purchases)) if user_purchases else 0,
            "avg_sale": round(sum(user_sales) / len(user_sales)) if user_sales else 0,
            "recent_trades": recent_trades.get(user_id, 0),
        }
    return profile
