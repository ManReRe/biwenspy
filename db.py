"""SQLite storage layer for the Biwenger dashboard."""
import json
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

CREATE TABLE IF NOT EXISTS squads (
    user_id INTEGER,
    player_id INTEGER,
    price_paid INTEGER,
    acquired_date INTEGER,
    PRIMARY KEY (user_id, player_id)
);

CREATE TABLE IF NOT EXISTS player_form (
    player_id INTEGER PRIMARY KEY,
    points_json TEXT,
    status TEXT
);

CREATE TABLE IF NOT EXISTS team_fixtures (
    team_id INTEGER PRIMARY KEY,
    opponent TEXT,
    difficulty INTEGER,
    is_home INTEGER
);
"""


def init_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    for statement in (
        "ALTER TABLE players ADD COLUMN position INTEGER",
        "ALTER TABLE players ADD COLUMN team_id INTEGER",
        "ALTER TABLE players ADD COLUMN price INTEGER",
        "ALTER TABLE players ADD COLUMN season_points INTEGER",
        "ALTER TABLE player_form ADD COLUMN status_info TEXT",
    ):
        try:
            conn.execute(statement)
        except sqlite3.OperationalError:
            pass  # column already added by a previous run
    conn.commit()
    return conn


def upsert_user(conn, id, name, icon=None):
    conn.execute(
        "INSERT INTO users (id, name, icon) VALUES (?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET name = excluded.name, icon = excluded.icon",
        (id, name, icon),
    )
    conn.commit()


def upsert_player(conn, id, name, team=None, position=None, team_id=None):
    conn.execute(
        "INSERT INTO players (id, name, team, position, team_id) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET name = excluded.name, team = excluded.team, "
        "position = excluded.position, team_id = excluded.team_id",
        (id, name, team, position, team_id),
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
    return {
        row["id"]: {
            "name": row["name"], "team": row["team"],
            "position": row["position"], "team_id": row["team_id"],
            "price": row["price"], "season_points": row["season_points"],
        }
        for row in rows
    }


def upsert_player_market(conn, id, price, season_points):
    """Set a player's current market price and season point total, refreshed
    for the whole La Liga catalog on every sync (not just squad/event-
    referenced players) -- kept separate from upsert_player so a caller that
    doesn't have this data (e.g. the single-player fallback lookup for a
    player who has left La Liga) can't accidentally null it out."""
    conn.execute(
        "INSERT INTO players (id, price, season_points) VALUES (?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET price = excluded.price, "
        "season_points = excluded.season_points",
        (id, price, season_points),
    )
    conn.commit()


def get_known_player_ids(conn):
    rows = conn.execute("SELECT id FROM players").fetchall()
    return {row["id"] for row in rows}


def get_player_ids_missing_team_id(conn):
    rows = conn.execute("SELECT id FROM players WHERE team_id IS NULL").fetchall()
    return {row["id"] for row in rows}


def get_standings(conn):
    rows = conn.execute("SELECT * FROM standings ORDER BY position ASC").fetchall()
    return [dict(row) for row in rows]


def replace_squad(conn, user_id, entries):
    """Overwrite a manager's squad with the given current snapshot (not append-only:
    a sold/released player must disappear, unlike the historical money_events log)."""
    conn.execute("DELETE FROM squads WHERE user_id = ?", (user_id,))
    conn.executemany(
        "INSERT INTO squads (user_id, player_id, price_paid, acquired_date) VALUES (?, ?, ?, ?)",
        [(user_id, e["player_id"], e["price_paid"], e["acquired_date"]) for e in entries],
    )
    conn.commit()


def get_all_squads(conn):
    rows = conn.execute("SELECT * FROM squads").fetchall()
    return [dict(row) for row in rows]


def upsert_player_form(conn, player_id, points_json, status, status_info=None):
    conn.execute(
        "INSERT INTO player_form (player_id, points_json, status, status_info) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(player_id) DO UPDATE SET points_json = excluded.points_json, "
        "status = excluded.status, status_info = excluded.status_info",
        (player_id, points_json, status, status_info),
    )
    conn.commit()


def replace_team_fixtures(conn, fixtures):
    """Overwrite the next-round fixture table with a fresh snapshot: {team_id:
    {"opponent", "difficulty", "is_home"}}. Small (~20 rows) and entirely
    superseded each sync, so a full delete+insert is simplest."""
    conn.execute("DELETE FROM team_fixtures")
    conn.executemany(
        "INSERT INTO team_fixtures (team_id, opponent, difficulty, is_home) VALUES (?, ?, ?, ?)",
        [
            (team_id, info.get("opponent"), info.get("difficulty"), int(bool(info.get("is_home"))))
            for team_id, info in fixtures.items()
        ],
    )
    conn.commit()


def get_team_fixtures(conn):
    rows = conn.execute("SELECT * FROM team_fixtures").fetchall()
    return {
        row["team_id"]: {
            "opponent": row["opponent"], "difficulty": row["difficulty"],
            "is_home": bool(row["is_home"]),
        }
        for row in rows
    }


def get_player_form(conn):
    rows = conn.execute("SELECT * FROM player_form").fetchall()
    return {
        row["player_id"]: {
            "recent_points": json.loads(row["points_json"]) if row["points_json"] else [],
            "status": row["status"],
            "status_info": row["status_info"],
        }
        for row in rows
    }
