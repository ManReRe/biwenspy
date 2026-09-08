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
    """Page through the league board and store money events.

    Stopping early is NOT based on whether an individual item has been seen before
    (``board_items`` can contain items from a run that crashed partway through and
    therefore never proved there's no gap below them). Instead it's based on a single
    marker, ``sync_state["board_top_item_id"]``: the id of the newest item as of the
    last time this function *fully completed* a walk (whether that walk was the
    original backfill reaching a short/empty page, or a later steady-state run that
    walked all the way back down to that same marker).

    Two modes, tracked via ``sync_state["board_backfill_complete"]``:

    - Backfill not yet complete (never reached the true end of history, e.g. an earlier
      run crashed mid-walk): walk the ENTIRE board regardless of whether individual items
      are already known. Stopping early here would silently and permanently abandon ever
      fetching older, never-synced pages below that point. Re-processing already-known
      items is safe: inserts are idempotent.
    - Backfill already complete: steady-state fast path, safe to stop as soon as the
      previous run's top-item marker is encountered again, since a full walk down to
      that exact item has already proven there's no gap below it.

    Crucially, the marker is only written AFTER a walk fully completes (either by
    reaching the previous marker, or by reaching a short/empty page). If this function
    is interrupted by an exception at any point, the marker is left untouched, so the
    next run's "previous marker" is still the one from the last genuinely complete run
    -- it will keep walking past anything the interrupted run touched (seen or not)
    until it either reaches that old marker or the true start of history, recovering
    whatever gap the interrupted run left behind.
    """
    backfill_complete = db.get_sync_state(conn, "board_backfill_complete") == "true"
    previous_top_item_id = db.get_sync_state(conn, "board_top_item_id")
    current_top_item_id = None
    offset = 0
    while True:
        page = client.get_board_page(offset, limit=PAGE_SIZE)

        for item in page:
            item_id = _item_id(item)
            if current_top_item_id is None:
                current_top_item_id = item_id

            if backfill_complete and previous_top_item_id is not None and item_id == previous_top_item_id:
                db.set_sync_state(conn, "board_top_item_id", current_top_item_id)
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
            db.set_sync_state(conn, "board_backfill_complete", "true")
            db.set_sync_state(conn, "board_top_item_id", current_top_item_id)
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
