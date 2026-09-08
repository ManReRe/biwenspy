# Biwenger Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Python tool that reconstructs each Biwenger league manager's money (starting
from 20,000,000 €), market movements, and points history from the league's activity feed, and
renders it as a self-contained HTML dashboard.

**Architecture:** A one-time Playwright login script captures a session token. A sync script calls
Biwenger's internal JSON API, incrementally stores the league's activity feed in SQLite. A pure
analytics module reconstructs balances/points/facts from the stored data. A dashboard script
renders everything to a static HTML file with Plotly charts.

**Tech Stack:** Python 3.9+, `requests` (HTTP), `playwright` (one-time login capture only),
`plotly` (charts), `pytest` (tests), `sqlite3` (stdlib, storage).

## Global Constraints

- Money amounts are always raw euros as integers (e.g. `378000` = 378.000 €), matching what the
  Biwenger API returns. No unit conversion anywhere in the codebase.
- Starting balance is a constant: `20_000_000` (defined once in `analytics.py` as
  `STARTING_BALANCE`).
- League id, user id, and token always come from `config.json` — never hardcoded in source files.
- `config.json` and `biwenger.db` are local secrets/data and must never be committed (enforced via
  `.gitignore`, created in Task 1).
- **Never add `Co-Authored-By: Claude` or any Claude/Anthropic attribution to commit messages** —
  this project's `CLAUDE.md` explicitly forbids it. Every commit step in this plan already omits
  it; do not add it back.
- All new Python modules live at the repo root (flat structure — this is a small single-purpose
  tool, not a package).

---

## Reference: confirmed Biwenger API shapes

These were captured live against the real league during design and are the ground truth for the
parsing code in this plan. Do not "improve" or guess at alternate shapes.

`GET /league/{id}/board?limit=500&offset=N` items (`content` shape per `type`):

```jsonc
// type: "transfer" — sale to market (only "from"), or direct trade between managers ("from" + "to")
{"type": "transfer", "date": 1788845299, "content": [
  {"player": 23572, "from": {"id": 12686032, "name": "..."}, "amount": 378000}
]}
{"type": "transfer", "date": 1788800000, "content": [
  {"player": 27715, "from": {"id": 12684091, "name": "..."}, "to": {"id": 12683799, "name": "..."}, "amount": 200000}
]}

// type: "market" — purchase from the market, paid by "to"
{"type": "market", "date": 1788843853, "content": [
  {"player": 18128, "to": {"id": 12683799, "name": "..."}, "amount": 1960000}
]}

// type: "roundFinished" — weekly points-based money
{"type": "roundFinished", "date": 1788700000, "content": {
  "round": {"id": 4902, "name": "Jornada 4"},
  "results": [
    {"user": {"id": 12686032, "name": "..."}, "points": 76, "bonus": 2325000,
     "reason": {"bonusPoint": 875000, "bonusFixed": 500000}}
  ]
}}
```

Other `type` values (`text`, `adminText`, `playerMovements`, `roundStarted`, `bettingPool`,
`leagueSettings`) carry no money information and must be ignored (not error out).

`GET /competitions/la-liga/data?lang=es&score=5` → `data.players` is a **dict keyed by string id**
(not a list), each value has `name` and `teamID` (an int, not a nested object). `data.teams` is a
**dict keyed by string id**, each value has `name`. Team names must be resolved by joining
`teamID` against `data.teams`.

---

### Task 1: Board parser — turn raw board items into money movements

**Files:**
- Create: `board_parser.py`
- Create: `requirements.txt`
- Create: `.gitignore`
- Test: `tests/test_board_parser.py`

**Interfaces:**
- Produces: `parse_board_page(items: list[dict]) -> dict` with keys `"money_events"`,
  `"round_points"`, `"rounds"` (each a `list[dict]`). Shape of a `money_events` entry:
  `{"id": str, "date": int, "round_id": int|None, "type": str, "user_id": int,
  "counterparty_id": int|None, "player_id": int|None, "amount": int,
  "direction": "income"|"expense", "reason_json": str|None}`. Shape of a `round_points` entry:
  `{"round_id": int, "user_id": int, "points": int}`. Shape of a `rounds` entry:
  `{"id": int, "name": str, "date": int}`.

- [ ] **Step 1: Create `requirements.txt`**

```
requests
playwright
plotly
pytest
```

- [ ] **Step 2: Create `.gitignore`**

```
config.json
biwenger.db
dashboard.html
__pycache__/
*.pyc
.venv/
venv/
```

- [ ] **Step 3: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: packages install without errors.

- [ ] **Step 4: Write the failing tests**

Create `tests/test_board_parser.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `pytest tests/test_board_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'board_parser'`

- [ ] **Step 6: Implement `board_parser.py`**

```python
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
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_board_parser.py -v`
Expected: PASS (7 tests)

- [ ] **Step 8: Commit**

```bash
git add board_parser.py tests/test_board_parser.py requirements.txt .gitignore
git commit -m "Add board parser for Biwenger activity feed events"
```

---

### Task 2: SQLite storage layer

**Files:**
- Create: `db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: nothing from other project modules (only stdlib `sqlite3`).
- Produces: `init_db(path) -> sqlite3.Connection`; `upsert_user(conn, id, name, icon=None)`;
  `upsert_player(conn, id, name, team=None)`; `upsert_round(conn, id, name, date)`;
  `insert_money_event(conn, event: dict) -> bool`; `insert_round_points(conn, round_id, user_id,
  points) -> bool`; `upsert_standing(conn, user_id, points, position)`;
  `has_board_item(conn, item_id: str) -> bool`; `mark_board_item_seen(conn, item_id: str)`;
  `get_sync_state(conn, key, default=None)`; `set_sync_state(conn, key, value)`;
  `get_all_money_events(conn) -> list[dict]`; `get_all_round_points(conn) -> list[dict]`;
  `get_all_rounds(conn) -> list[dict]`; `get_users(conn) -> list[dict]`;
  `get_players(conn) -> dict[int, dict]`; `get_known_player_ids(conn) -> set[int]`;
  `get_standings(conn) -> list[dict]`. `event` dicts passed to `insert_money_event` match the
  `money_events` shape produced by `board_parser.parse_board_page`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_db.py`:

```python
import db


def test_init_db_creates_tables():
    conn = db.init_db(":memory:")
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {
        "users", "players", "rounds", "money_events", "round_points",
        "standings", "sync_state", "board_items",
    } <= tables


def test_upsert_user_inserts_and_updates():
    conn = db.init_db(":memory:")
    db.upsert_user(conn, 1, "Alice", "icon.png")
    db.upsert_user(conn, 1, "Alice Updated", "icon2.png")
    assert db.get_users(conn) == [{"id": 1, "name": "Alice Updated", "icon": "icon2.png"}]


def test_insert_money_event_is_idempotent():
    conn = db.init_db(":memory:")
    event = {
        "id": "abc", "date": 1, "round_id": None, "type": "market",
        "user_id": 1, "counterparty_id": None, "player_id": 5,
        "amount": 1000, "direction": "expense", "reason_json": None,
    }
    assert db.insert_money_event(conn, event) is True
    assert db.insert_money_event(conn, event) is False
    assert len(db.get_all_money_events(conn)) == 1


def test_insert_round_points_is_idempotent():
    conn = db.init_db(":memory:")
    assert db.insert_round_points(conn, 1, 2, 50) is True
    assert db.insert_round_points(conn, 1, 2, 50) is False


def test_board_item_seen_tracking():
    conn = db.init_db(":memory:")
    assert db.has_board_item(conn, "x") is False
    db.mark_board_item_seen(conn, "x")
    assert db.has_board_item(conn, "x") is True


def test_sync_state_roundtrip():
    conn = db.init_db(":memory:")
    assert db.get_sync_state(conn, "missing") is None
    db.set_sync_state(conn, "last_offset", "500")
    assert db.get_sync_state(conn, "last_offset") == "500"
    db.set_sync_state(conn, "last_offset", "1000")
    assert db.get_sync_state(conn, "last_offset") == "1000"


def test_get_players_and_known_player_ids():
    conn = db.init_db(":memory:")
    db.upsert_player(conn, 10, "Jugador A", "Equipo X")
    assert db.get_players(conn) == {10: {"name": "Jugador A", "team": "Equipo X"}}
    assert db.get_known_player_ids(conn) == {10}


def test_upsert_standing_and_get_standings_ordered_by_position():
    conn = db.init_db(":memory:")
    db.upsert_standing(conn, 2, 40, 2)
    db.upsert_standing(conn, 1, 60, 1)
    assert db.get_standings(conn) == [
        {"user_id": 1, "points": 60, "position": 1},
        {"user_id": 2, "points": 40, "position": 2},
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 3: Implement `db.py`**

```python
"""SQLite storage layer for the Biwenger dashboard."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT,
    icon TEXT
);

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY,
    name TEXT,
    team TEXT
);

CREATE TABLE IF NOT EXISTS rounds (
    id INTEGER PRIMARY KEY,
    name TEXT,
    date INTEGER
);

CREATE TABLE IF NOT EXISTS money_events (
    id TEXT PRIMARY KEY,
    date INTEGER,
    round_id INTEGER,
    type TEXT,
    user_id INTEGER,
    counterparty_id INTEGER,
    player_id INTEGER,
    amount INTEGER,
    direction TEXT,
    reason_json TEXT
);

CREATE TABLE IF NOT EXISTS round_points (
    round_id INTEGER,
    user_id INTEGER,
    points INTEGER,
    PRIMARY KEY (round_id, user_id)
);

CREATE TABLE IF NOT EXISTS standings (
    user_id INTEGER PRIMARY KEY,
    points INTEGER,
    position INTEGER
);

CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS board_items (
    id TEXT PRIMARY KEY
);
"""


def init_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def upsert_user(conn, id, name, icon=None):
    conn.execute(
        "INSERT INTO users (id, name, icon) VALUES (?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET name = excluded.name, icon = excluded.icon",
        (id, name, icon),
    )
    conn.commit()


def upsert_player(conn, id, name, team=None):
    conn.execute(
        "INSERT INTO players (id, name, team) VALUES (?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET name = excluded.name, team = excluded.team",
        (id, name, team),
    )
    conn.commit()


def upsert_round(conn, id, name, date):
    conn.execute(
        "INSERT INTO rounds (id, name, date) VALUES (?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET name = excluded.name, date = excluded.date",
        (id, name, date),
    )
    conn.commit()


def insert_money_event(conn, event):
    cursor = conn.execute(
        "INSERT OR IGNORE INTO money_events "
        "(id, date, round_id, type, user_id, counterparty_id, player_id, amount, direction, reason_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            event["id"], event["date"], event["round_id"], event["type"],
            event["user_id"], event["counterparty_id"], event["player_id"],
            event["amount"], event["direction"], event["reason_json"],
        ),
    )
    conn.commit()
    return cursor.rowcount == 1


def insert_round_points(conn, round_id, user_id, points):
    cursor = conn.execute(
        "INSERT OR IGNORE INTO round_points (round_id, user_id, points) VALUES (?, ?, ?)",
        (round_id, user_id, points),
    )
    conn.commit()
    return cursor.rowcount == 1


def upsert_standing(conn, user_id, points, position):
    conn.execute(
        "INSERT INTO standings (user_id, points, position) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET points = excluded.points, position = excluded.position",
        (user_id, points, position),
    )
    conn.commit()


def has_board_item(conn, item_id):
    row = conn.execute("SELECT 1 FROM board_items WHERE id = ?", (item_id,)).fetchone()
    return row is not None


def mark_board_item_seen(conn, item_id):
    conn.execute("INSERT OR IGNORE INTO board_items (id) VALUES (?)", (item_id,))
    conn.commit()


def get_sync_state(conn, key, default=None):
    row = conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_sync_state(conn, key, value):
    conn.execute(
        "INSERT INTO sync_state (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def get_all_money_events(conn):
    rows = conn.execute("SELECT * FROM money_events ORDER BY date ASC").fetchall()
    return [dict(row) for row in rows]


def get_all_round_points(conn):
    rows = conn.execute("SELECT * FROM round_points").fetchall()
    return [dict(row) for row in rows]


def get_all_rounds(conn):
    rows = conn.execute("SELECT * FROM rounds ORDER BY date ASC").fetchall()
    return [dict(row) for row in rows]


def get_users(conn):
    rows = conn.execute("SELECT * FROM users").fetchall()
    return [dict(row) for row in rows]


def get_players(conn):
    rows = conn.execute("SELECT * FROM players").fetchall()
    return {row["id"]: {"name": row["name"], "team": row["team"]} for row in rows}


def get_known_player_ids(conn):
    rows = conn.execute("SELECT id FROM players").fetchall()
    return {row["id"] for row in rows}


def get_standings(conn):
    rows = conn.execute("SELECT * FROM standings ORDER BY position ASC").fetchall()
    return [dict(row) for row in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_db.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "Add SQLite storage layer"
```

---

### Task 3: Analytics — balance and points reconstruction

**Files:**
- Create: `analytics.py`
- Test: `tests/test_analytics.py` (this task writes the balance/points tests; Task 4 extends the
  same two files with curious-facts tests)

**Interfaces:**
- Consumes: `money_events` / `round_points` / `rounds` lists shaped exactly like
  `db.get_all_money_events`, `db.get_all_round_points`, `db.get_all_rounds` return.
- Produces: `STARTING_BALANCE = 20_000_000`; `compute_balance_timeline(money_events,
  starting_balance=STARTING_BALANCE) -> dict[int, list[tuple[int, int]]]`;
  `compute_current_balances(money_events, starting_balance=STARTING_BALANCE) -> dict[int, int]`;
  `compute_points_timeline(round_points, rounds) -> dict[int, list[tuple[int|None, int]]]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_analytics.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analytics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'analytics'`

- [ ] **Step 3: Implement `analytics.py` (balance and points parts)**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analytics.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add analytics.py tests/test_analytics.py
git commit -m "Add balance and points timeline reconstruction"
```

---

### Task 4: Analytics — curious facts

**Files:**
- Modify: `analytics.py`
- Modify: `tests/test_analytics.py`

**Interfaces:**
- Consumes: `money_events` (as above), `players: dict[int, dict]` shaped like
  `db.get_players()`, `users: list[dict]` shaped like `db.get_users()`.
- Produces: `compute_curious_facts(money_events, players, users) -> dict`. Possible keys (each
  present only if at least one relevant event exists):
  `"most_expensive_sale"`: `{"user": str, "player": str, "amount": int, "date": int}`;
  `"most_expensive_purchase"`: same shape; `"biggest_round_bonus"`: `{"user": str, "amount": int,
  "date": int}`; `"most_active_trader"`: `{"user": str, "movements": int}`; `"best_flip"`:
  `{"user": str, "player": str, "profit": int, "buy_amount": int, "sell_amount": int}`.
  Also produces: `compute_income_breakdown(money_events, users) -> dict[int, dict]` with
  `{"points": int, "sales": int, "purchases": int}` per user id (one entry per user in `users`,
  plus any extra user id only seen in `money_events`); `compute_biggest_bonus_round(money_events,
  rounds) -> dict|None` — `{"round": str, "total": int}` for the round with the highest total
  `roundFinished` money paid out across all managers, or `None` if there are no `roundFinished`
  events.

- [ ] **Step 1: Append the failing tests**

Append to `tests/test_analytics.py`:

```python
import json

from analytics import compute_biggest_bonus_round, compute_curious_facts, compute_income_breakdown


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analytics.py -v`
Expected: FAIL with `ImportError: cannot import name 'compute_curious_facts'`

- [ ] **Step 3: Append `compute_curious_facts` to `analytics.py`**

Append to `analytics.py`:

```python
def _user_name(users_by_id, user_id):
    return users_by_id.get(user_id, {}).get("name", f"Usuario {user_id}")


def _player_name(players, player_id):
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
            "player": _player_name(players, best_sale["player_id"]),
            "amount": best_sale["amount"],
            "date": best_sale["date"],
        }

    purchases = [e for e in money_events if e["type"] in ("market", "transfer") and e["direction"] == "expense"]
    if purchases:
        best_purchase = max(purchases, key=lambda e: e["amount"])
        facts["most_expensive_purchase"] = {
            "user": _user_name(users_by_id, best_purchase["user_id"]),
            "player": _player_name(players, best_purchase["player_id"]),
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
            "player": _player_name(players, best_flip["player_id"]),
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analytics.py -v`
Expected: PASS (16 tests)

- [ ] **Step 5: Commit**

```bash
git add analytics.py tests/test_analytics.py
git commit -m "Add curious facts to analytics"
```

---

### Task 5: Biwenger API client

**Files:**
- Create: `client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: `requests` (via injectable `session` object exposing `.get(url, headers=, params=,
  timeout=) -> Response` with `.status_code`, `.json()`, `.raise_for_status()`).
- Produces: `BiwengerAuthError(Exception)`; `BiwengerClient(token, league_id, user_id,
  base_url=BASE_URL, session=None)` with methods `get_league_users() -> list[dict]`,
  `get_standings() -> list[dict]`, `get_board_page(offset, limit=500) -> list[dict]`,
  `get_players() -> dict[int, dict]` (each value `{"name": str, "team": str|None}`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_client.py`:

```python
import pytest

from client import BiwengerAuthError, BiwengerClient


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.last_call = None

    def get(self, url, headers=None, params=None, timeout=None):
        self.last_call = {"url": url, "headers": headers, "params": params}
        return self.response


def _client(response):
    session = FakeSession(response)
    client = BiwengerClient("token123", 1967092, 12683880, session=session)
    return client, session


def test_sends_expected_headers():
    client, session = _client(FakeResponse(200, {"status": 200, "data": {"users": []}}))
    client.get_league_users()
    headers = session.last_call["headers"]
    assert headers["Authorization"] == "Bearer token123"
    assert headers["X-League"] == "1967092"
    assert headers["X-User"] == "12683880"


def test_get_league_users_returns_users_list():
    client, _ = _client(FakeResponse(200, {"status": 200, "data": {"users": [{"id": 1, "name": "Ana"}]}}))
    assert client.get_league_users() == [{"id": 1, "name": "Ana"}]


def test_get_standings_returns_standings_list():
    client, _ = _client(FakeResponse(200, {"status": 200, "data": {"standings": [{"id": 1, "points": 50}]}}))
    assert client.get_standings() == [{"id": 1, "points": 50}]


def test_get_board_page_returns_raw_items():
    client, session = _client(FakeResponse(200, {"status": 200, "data": [{"type": "market"}]}))
    result = client.get_board_page(offset=500, limit=500)
    assert result == [{"type": "market"}]
    assert session.last_call["params"] == {"offset": 500, "limit": 500}


def test_get_players_resolves_team_names_by_id():
    payload = {
        "status": 200,
        "data": {
            "players": {"10": {"id": 10, "name": "Jugador A", "teamID": 1}},
            "teams": {"1": {"id": 1, "name": "Equipo X"}},
        },
    }
    client, _ = _client(FakeResponse(200, payload))
    assert client.get_players() == {10: {"name": "Jugador A", "team": "Equipo X"}}


def test_raises_auth_error_on_401():
    client, _ = _client(FakeResponse(401, {"status": 401, "message": "Invalid user"}))
    with pytest.raises(BiwengerAuthError):
        client.get_league_users()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'client'`

- [ ] **Step 3: Implement `client.py`**

```python
"""Thin HTTP client for the internal Biwenger API."""
import requests

BASE_URL = "https://biwenger.as.com/api/v2"


class BiwengerAuthError(Exception):
    """Raised when the API rejects the stored token (HTTP 401)."""


class BiwengerClient:
    def __init__(self, token, league_id, user_id, base_url=BASE_URL, session=None):
        self.token = token
        self.league_id = league_id
        self.user_id = user_id
        self.base_url = base_url
        self.session = session or requests.Session()

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "X-League": str(self.league_id),
            "X-User": str(self.user_id),
            "X-Lang": "es",
            "X-Version": "665",
        }

    def _get(self, path, params=None):
        response = self.session.get(
            f"{self.base_url}{path}", headers=self._headers(), params=params, timeout=15
        )
        if response.status_code == 401:
            raise BiwengerAuthError(
                "Biwenger rechazo el token (401). Vuelve a ejecutar capture_token.py."
            )
        response.raise_for_status()
        return response.json()["data"]

    def get_league_users(self):
        return self._get(f"/league/{self.league_id}")["users"]

    def get_standings(self):
        return self._get(f"/league/{self.league_id}", params={"fields": "standings"})["standings"]

    def get_board_page(self, offset, limit=500):
        return self._get(f"/league/{self.league_id}/board", params={"offset": offset, "limit": limit})

    def get_players(self):
        data = self._get("/competitions/la-liga/data", params={"lang": "es", "score": "5"})
        teams = {int(team_id): info.get("name") for team_id, info in data.get("teams", {}).items()}
        players = {}
        for player_id, info in data.get("players", {}).items():
            players[int(player_id)] = {
                "name": info.get("name"),
                "team": teams.get(info.get("teamID")),
            }
        return players
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_client.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add client.py tests/test_client.py
git commit -m "Add Biwenger API client"
```

---

### Task 6: Sync orchestration

**Files:**
- Create: `sync.py`
- Test: `tests/test_sync.py`

**Interfaces:**
- Consumes: `board_parser.parse_board_page`; `db.{init_db, upsert_round, insert_money_event,
  insert_round_points, has_board_item, mark_board_item_seen, get_all_money_events,
  get_known_player_ids, upsert_player, upsert_user, upsert_standing}`; a client object exposing
  `get_board_page(offset, limit) -> list[dict]`, `get_players() -> dict`,
  `get_league_users() -> list[dict]`, `get_standings() -> list[dict]` (matches `BiwengerClient`).
- Produces: `sync_board(client, conn)`; `sync_players(client, conn)`; `load_config(path) -> dict`;
  `main()` (CLI entry point, reads `config.json`, writes `biwenger.db`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sync.py`:

```python
import db
import sync


class FakeClient:
    def __init__(self, pages):
        self._pages = pages
        self.calls = []

    def get_board_page(self, offset, limit=500):
        self.calls.append(offset)
        index = offset // limit
        return self._pages[index] if index < len(self._pages) else []


def _market_item(date, amount=500_000):
    return {
        "type": "market",
        "content": [{"player": 10, "to": {"id": 1, "name": "Ana"}, "amount": amount}],
        "date": date,
    }


ROUND_FINISHED_ITEM = {
    "type": "roundFinished",
    "content": {
        "round": {"id": 1, "name": "J1"},
        "results": [{"user": {"id": 1, "name": "Ana"}, "points": 50, "bonus": 1_000_000, "reason": {}}],
    },
    "date": 999,
}


def test_sync_board_stores_events_from_a_single_short_page():
    conn = db.init_db(":memory:")
    client = FakeClient(pages=[[ROUND_FINISHED_ITEM, _market_item(200)]])

    sync.sync_board(client, conn)

    assert len(db.get_all_money_events(conn)) == 2
    assert client.calls == [0]


def test_sync_board_pages_forward_while_pages_are_full():
    conn = db.init_db(":memory:")
    full_page = [_market_item(date) for date in range(500)]
    client = FakeClient(pages=[full_page, [ROUND_FINISHED_ITEM]])

    sync.sync_board(client, conn)

    assert client.calls == [0, 500]
    assert len(db.get_all_money_events(conn)) == 501


def test_sync_board_stops_as_soon_as_a_known_item_is_seen():
    conn = db.init_db(":memory:")
    full_page = [_market_item(date) for date in range(500)]
    sync.sync_board(FakeClient(pages=[full_page, [ROUND_FINISHED_ITEM]]), conn)

    client2 = FakeClient(pages=[full_page, [ROUND_FINISHED_ITEM]])
    sync.sync_board(client2, conn)

    assert client2.calls == [0]
    assert len(db.get_all_money_events(conn)) == 501


def test_sync_board_keeps_paging_through_pages_with_no_money_events():
    conn = db.init_db(":memory:")
    no_money_page = [{"type": "text", "content": "hola", "date": d} for d in range(500)]
    client = FakeClient(pages=[no_money_page, [_market_item(999)]])

    sync.sync_board(client, conn)

    assert client.calls == [0, 500]
    assert len(db.get_all_money_events(conn)) == 1


def test_sync_players_fetches_and_stores_only_referenced_players():
    conn = db.init_db(":memory:")
    db.insert_money_event(conn, {
        "id": "e1", "date": 1, "round_id": None, "type": "market", "user_id": 1,
        "counterparty_id": None, "player_id": 10, "amount": 100, "direction": "expense",
        "reason_json": None,
    })

    class PlayersClient:
        def get_players(self):
            return {
                10: {"name": "Jugador A", "team": "Equipo X"},
                11: {"name": "Jugador B", "team": "Equipo Y"},
            }

    sync.sync_players(PlayersClient(), conn)

    assert db.get_players(conn) == {10: {"name": "Jugador A", "team": "Equipo X"}}


def test_sync_players_skips_api_call_when_nothing_new():
    conn = db.init_db(":memory:")
    db.upsert_player(conn, 10, "Jugador A", "Equipo X")
    db.insert_money_event(conn, {
        "id": "e1", "date": 1, "round_id": None, "type": "market", "user_id": 1,
        "counterparty_id": None, "player_id": 10, "amount": 100, "direction": "expense",
        "reason_json": None,
    })

    class ExplodingClient:
        def get_players(self):
            raise AssertionError("should not be called")

    sync.sync_players(ExplodingClient(), conn)  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sync.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sync'`

- [ ] **Step 3: Implement `sync.py`**

```python
"""Fetch the Biwenger league board incrementally and store it in SQLite."""
import hashlib
import json
import sys

import board_parser
import db
from client import BiwengerAuthError, BiwengerClient

CONFIG_PATH = "config.json"
DB_PATH = "biwenger.db"
PAGE_SIZE = 500


def load_config(path=CONFIG_PATH):
    with open(path) as config_file:
        return json.load(config_file)


def _item_id(item):
    raw = json.dumps(
        {"date": item.get("date"), "type": item.get("type"), "content": item.get("content")},
        sort_keys=True,
        default=str,
    )
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def sync_board(client, conn):
    offset = 0
    while True:
        page = client.get_board_page(offset, limit=PAGE_SIZE)
        if not page:
            return

        for item in page:
            item_id = _item_id(item)
            if db.has_board_item(conn, item_id):
                return
            db.mark_board_item_seen(conn, item_id)

            parsed = board_parser.parse_board_page([item])
            for round_ in parsed["rounds"]:
                db.upsert_round(conn, round_["id"], round_["name"], round_["date"])
            for event in parsed["money_events"]:
                db.insert_money_event(conn, event)
            for entry in parsed["round_points"]:
                db.insert_round_points(conn, entry["round_id"], entry["user_id"], entry["points"])

        if len(page) < PAGE_SIZE:
            return
        offset += PAGE_SIZE


def sync_players(client, conn):
    events = db.get_all_money_events(conn)
    known_ids = db.get_known_player_ids(conn)
    needed_ids = {e["player_id"] for e in events if e["player_id"] is not None}
    missing_ids = needed_ids - known_ids
    if not missing_ids:
        return

    players = client.get_players()
    for player_id in missing_ids:
        info = players.get(player_id)
        if info:
            db.upsert_player(conn, player_id, info["name"], info["team"])


def main():
    config = load_config()
    client = BiwengerClient(config["token"], config["league_id"], config["user_id"])
    conn = db.init_db(DB_PATH)

    try:
        for user in client.get_league_users():
            db.upsert_user(conn, user["id"], user["name"], user.get("icon"))

        sync_board(client, conn)
        sync_players(client, conn)

        for standing in client.get_standings():
            db.upsert_standing(conn, standing["id"], standing["points"], standing["position"])
    except BiwengerAuthError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)

    print(f"Sincronizacion completa. {len(db.get_all_money_events(conn))} movimientos de dinero en {DB_PATH}.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sync.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add sync.py tests/test_sync.py
git commit -m "Add incremental sync orchestration"
```

---

### Task 7: Dashboard HTML generation

**Files:**
- Create: `dashboard.py`
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `db.{get_users, get_all_money_events, get_all_round_points, get_all_rounds,
  get_standings, get_players}`; `analytics.{compute_balance_timeline, compute_current_balances,
  compute_points_timeline, compute_curious_facts, compute_income_breakdown,
  compute_biggest_bonus_round}` (the last two from Task 4).
- Produces: `build_dashboard_html(conn) -> str`; `main()` (writes `dashboard.html`). The output
  includes: standings table, balance-over-time chart, points-over-time chart, curious facts (plus
  the biggest-bonus-round fact), a per-manager income/expense breakdown table, and a per-manager
  movements table (compra/venta, fecha, importe) — this last one covers the "movimientos desde el
  inicio de la liga" requirement from the design spec.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dashboard.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dashboard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dashboard'`

- [ ] **Step 3: Implement `dashboard.py`**

```python
"""Generate a self-contained HTML dashboard from biwenger.db."""
import html
from collections import defaultdict

import plotly.graph_objects as go
from plotly.offline import plot

import analytics
import db

DB_PATH = "biwenger.db"
OUTPUT_PATH = "dashboard.html"


def _balance_chart(balance_timelines, names):
    fig = go.Figure()
    for user_id, points in balance_timelines.items():
        if not points:
            continue
        fig.add_trace(go.Scatter(
            x=[p[0] for p in points], y=[p[1] for p in points],
            mode="lines+markers", name=names.get(user_id, str(user_id)),
        ))
    fig.update_layout(title="Dinero disponible por manager", xaxis_title="Fecha (epoch)", yaxis_title="EUR")
    return fig


def _points_chart(points_timelines, names):
    fig = go.Figure()
    for user_id, points in points_timelines.items():
        if not points:
            continue
        fig.add_trace(go.Scatter(
            x=[p[0] for p in points], y=[p[1] for p in points],
            mode="lines+markers", name=names.get(user_id, str(user_id)),
        ))
    fig.update_layout(title="Puntos acumulados por manager", xaxis_title="Fecha (epoch)", yaxis_title="Puntos")
    return fig


def _standings_table_html(standings, names, current_balances):
    rows = []
    for row in standings:
        name = html.escape(names.get(row["user_id"], str(row["user_id"])))
        # A manager with zero recorded money events hasn't traded yet, so their
        # balance is still the starting amount, not 0.
        balance = current_balances.get(row["user_id"], analytics.STARTING_BALANCE)
        rows.append(
            f"<tr><td>{row['position']}</td><td>{name}</td>"
            f"<td>{row['points']}</td><td>{balance:,.0f} EUR</td></tr>"
        )
    return (
        "<table><thead><tr><th>Pos.</th><th>Manager</th><th>Puntos</th>"
        "<th>Dinero</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _format_fact(key, fact):
    if key == "most_expensive_sale":
        return f"{fact['user']} vendio a {fact['player']} por {fact['amount']:,} EUR"
    if key == "most_expensive_purchase":
        return f"{fact['user']} compro a {fact['player']} por {fact['amount']:,} EUR"
    if key == "biggest_round_bonus":
        return f"{fact['user']} gano {fact['amount']:,} EUR en una sola jornada"
    if key == "most_active_trader":
        return f"{fact['user']} con {fact['movements']} movimientos de mercado"
    if key == "best_flip":
        return (
            f"{fact['user']} gano {fact['profit']:,} EUR comprando a {fact['player']} por "
            f"{fact['buy_amount']:,} EUR y vendiendolo por {fact['sell_amount']:,} EUR"
        )
    return str(fact)


def _facts_html(facts, biggest_bonus_round=None):
    labels = {
        "most_expensive_sale": "Venta mas cara",
        "most_expensive_purchase": "Compra mas cara",
        "biggest_round_bonus": "Mayor bonus semanal",
        "most_active_trader": "Manager mas activo en el mercado",
        "best_flip": "Mejor plusvalia",
    }
    items = [
        f"<li><strong>{html.escape(label)}:</strong> {html.escape(_format_fact(key, facts[key]))}</li>"
        for key, label in labels.items() if key in facts
    ]
    if biggest_bonus_round is not None:
        items.append(
            "<li><strong>Jornada con mas dinero repartido:</strong> "
            f"{html.escape(biggest_bonus_round['round'])} "
            f"({biggest_bonus_round['total']:,} EUR entre todos los managers)</li>"
        )
    return "<ul>" + "".join(items) + "</ul>" if items else "<p>Sin datos todavia.</p>"


def _breakdown_table_html(breakdown, names):
    rows = []
    for user_id, values in breakdown.items():
        rows.append(
            f"<tr><td>{html.escape(names.get(user_id, str(user_id)))}</td>"
            f"<td>{values['points']:,} EUR</td><td>{values['sales']:,} EUR</td>"
            f"<td>{values['purchases']:,} EUR</td></tr>"
        )
    return (
        "<table><thead><tr><th>Manager</th><th>Ingresos por puntos</th>"
        "<th>Ingresos por ventas</th><th>Gastos en fichajes</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _movement_description(event, names, players):
    player_name = players.get(event["player_id"], {}).get("name") if event["player_id"] else None
    counterparty = names.get(event["counterparty_id"]) if event["counterparty_id"] else None

    if event["type"] == "roundFinished":
        return "Bonus de jornada"
    if event["type"] == "market":
        return f"Compra de {player_name} al mercado"
    if event["type"] == "transfer" and event["direction"] == "income":
        return f"Venta de {player_name} a {counterparty}" if counterparty else f"Venta de {player_name} al mercado"
    if event["type"] == "transfer" and event["direction"] == "expense":
        return f"Compra de {player_name} a {counterparty}"
    return event["type"]


def _movements_table_html(events, names, players):
    by_user = defaultdict(list)
    for event in events:
        by_user[event["user_id"]].append(event)

    sections = []
    for user_id, user_events in by_user.items():
        rows = []
        for event in sorted(user_events, key=lambda e: e["date"], reverse=True):
            sign = "+" if event["direction"] == "income" else "-"
            description = html.escape(_movement_description(event, names, players))
            rows.append(
                f"<tr><td>{event['date']}</td><td>{description}</td>"
                f"<td>{sign}{event['amount']:,} EUR</td></tr>"
            )
        manager_name = html.escape(names.get(user_id, str(user_id)))
        sections.append(
            f"<details><summary>{manager_name} ({len(user_events)} movimientos)</summary>"
            "<table><thead><tr><th>Fecha</th><th>Movimiento</th><th>Importe</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></details>"
        )
    return "".join(sections) if sections else "<p>Sin movimientos todavia.</p>"


def build_dashboard_html(conn):
    users = db.get_users(conn)
    names = {u["id"]: u["name"] for u in users}
    events = db.get_all_money_events(conn)
    round_points = db.get_all_round_points(conn)
    rounds = db.get_all_rounds(conn)
    standings = db.get_standings(conn)
    players = db.get_players(conn)

    balance_timelines = analytics.compute_balance_timeline(events)
    current_balances = analytics.compute_current_balances(events)
    points_timelines = analytics.compute_points_timeline(round_points, rounds)
    facts = analytics.compute_curious_facts(events, players, users)
    breakdown = analytics.compute_income_breakdown(events, users)
    biggest_bonus_round = analytics.compute_biggest_bonus_round(events, rounds)

    balance_fig_html = plot(_balance_chart(balance_timelines, names), output_type="div", include_plotlyjs="cdn")
    points_fig_html = plot(_points_chart(points_timelines, names), output_type="div", include_plotlyjs=False)

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><title>Dashboard Biwenger</title></head>
<body>
<h1>Dashboard financiero de la liga</h1>
<h2>Clasificacion</h2>
{_standings_table_html(standings, names, current_balances)}
<h2>Evolucion del dinero</h2>
{balance_fig_html}
<h2>Evolucion de puntos</h2>
{points_fig_html}
<h2>Desglose de ingresos y gastos</h2>
{_breakdown_table_html(breakdown, names)}
<h2>Movimientos por manager</h2>
{_movements_table_html(events, names, players)}
<h2>Datos curiosos</h2>
{_facts_html(facts, biggest_bonus_round)}
</body>
</html>"""


def main():
    conn = db.init_db(DB_PATH)
    output = build_dashboard_html(conn)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as output_file:
        output_file.write(output)
    print(f"Dashboard generado en {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dashboard.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add dashboard.py tests/test_dashboard.py
git commit -m "Add HTML dashboard generation"
```

---

### Task 8: One-time login token capture

**Files:**
- Create: `capture_token.py`
- Create: `config.example.json`

**Interfaces:**
- Produces: `config.json` on disk with keys `token: str`, `league_id: int`, `user_id: int`,
  `league_name: str` — this is exactly what `sync.load_config()` (Task 6) reads.

This script drives a real interactive login (the user types their own credentials, or uses
Google/Facebook, in a real browser window) — it cannot be meaningfully unit-tested with mocks
without testing nothing of value. It is verified manually instead, against the real Biwenger
account.

- [ ] **Step 1: Install the Playwright browser**

Run: `playwright install chromium`
Expected: downloads and installs a Chromium build for Playwright.

- [ ] **Step 2: Create `config.example.json`**

```json
{
  "token": "PASTE_TOKEN_HERE",
  "league_id": 0,
  "user_id": 0,
  "league_name": "example"
}
```

- [ ] **Step 3: Implement `capture_token.py`**

```python
"""One-time interactive login to capture a Biwenger session token.

Opens a real Chrome window, waits for the user to log in manually, then reads
the session token and league/user ids from localStorage and writes config.json.
"""
import json
import time

from playwright.sync_api import sync_playwright

CONFIG_PATH = "config.json"
LOGIN_URL = "https://biwenger.as.com/"
POLL_SECONDS = 2
TIMEOUT_SECONDS = 300


def wait_for_login(page):
    waited = 0
    while waited < TIMEOUT_SECONDS:
        token = page.evaluate("localStorage.getItem('satellizer_token')")
        if token:
            return token
        time.sleep(POLL_SECONDS)
        waited += POLL_SECONDS
    raise TimeoutError("No se detecto login tras 5 minutos. Vuelve a ejecutar el script.")


def pick_league(leagues):
    if len(leagues) == 1:
        return leagues[0]
    print("Tienes varias ligas, elige una:")
    for index, league in enumerate(leagues):
        print(f"  [{index}] {league['name']} (id {league['id']})")
    choice = int(input("Numero de liga: "))
    return leagues[choice]


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(LOGIN_URL)
        print("Inicia sesion en la ventana de Chrome. Esperando...")
        token = wait_for_login(page)

        last_session = json.loads(page.evaluate("localStorage.getItem('lastSession')"))
        league = pick_league(last_session["leagues"])

        config = {
            "token": token,
            "league_id": league["id"],
            "user_id": league["user"]["id"],
            "league_name": league["name"],
        }
        with open(CONFIG_PATH, "w") as config_file:
            json.dump(config, config_file, indent=2)

        print(f"Listo. Guardado en {CONFIG_PATH} para la liga '{league['name']}'.")
        browser.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Manually verify**

Run: `python capture_token.py`

1. A Chrome window opens on the Biwenger homepage.
2. Log in with your real account in that window.
3. Within ~2-10 seconds the terminal should print `Listo. Guardado en config.json para la liga
   '<tu liga>'.` and the browser closes.
4. Open `config.json` and confirm it has non-empty `token`, `league_id`, `user_id`, `league_name`.

Expected: `config.json` exists with real values, no traceback in the terminal.

- [ ] **Step 5: Commit**

```bash
git add capture_token.py config.example.json
git commit -m "Add one-time login token capture script"
```

(`config.json` itself is never committed — it's covered by `.gitignore` from Task 1.)

---

### Task 9: Wiring, README, and end-to-end verification

**Files:**
- Create: `README.md`

**Interfaces:** none (documentation + manual verification only).

- [ ] **Step 1: Write `README.md`**

```markdown
# biwenspy

Dashboard financiero para tu liga de Biwenger: dinero disponible, movimientos de mercado y
puntos de cada manager a lo largo de la temporada, reconstruidos desde 20.000.000 EUR iniciales.

## Uso

1. Instala dependencias:
   ```
   pip install -r requirements.txt
   playwright install chromium
   ```
2. Captura tu sesion (una vez, o cuando el token caduque):
   ```
   python capture_token.py
   ```
3. Sincroniza los datos de la liga (repite cuando quieras datos frescos, es incremental):
   ```
   python sync.py
   ```
4. Genera el dashboard:
   ```
   python dashboard.py
   ```
5. Abre `dashboard.html` en el navegador.

## Tests

```
pytest
```
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`
Expected: PASS, all tests from Tasks 1-7 (49 tests) green.

- [ ] **Step 3: End-to-end run against the real league**

Run in order: `python capture_token.py` (log in when the window opens), then `python sync.py`,
then `python dashboard.py`.

Expected: `sync.py` prints a movement count around 537 or higher (the real league had 537
board events at design time — it only grows). `dashboard.html` is created.

- [ ] **Step 4: Manually cross-check the reconstructed balance**

Open `dashboard.html`, find the row for your own manager in the "Clasificacion" table, and
compare its "Dinero" value against the real balance Biwenger shows you in the app for the same
moment. They should match (the design-time control value was 38.470.000 EUR for user id
12683880 in league 1967092 — your current live value will differ since time has passed, but it
must match what Biwenger itself reports *now*, not that historical number).

Expected: the two values match exactly.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "Add README with usage instructions"
```
