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
