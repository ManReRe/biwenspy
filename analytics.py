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
