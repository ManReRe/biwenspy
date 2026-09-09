"""Fetch the Biwenger league board incrementally and store it in SQLite."""
import hashlib
import json
import sys

import analytics
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
            # A manager can pin a post to the top of the board regardless of its real
            # date (Biwenger marks it "fixed": true) -- confirmed live. A fixed item is
            # NOT chronologically meaningful, so it must be excluded from both the
            # top-item marker and the stop check below; otherwise the walk would anchor
            # on that permanently-first, never-changing item and stop immediately on
            # every run, never seeing genuinely new items sitting right below it.
            if item.get("fixed"):
                db.mark_board_item_seen(conn, item_id)
                continue

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


def calibrate_starting_balance(client, conn, owner_user_id):
    """Back-solve the real season-starting balance from the account owner's
    real current balance, and store it for every manager's calculation.

    Biwenger's board has no event for a season-transition budget reset (a
    manager keeping part of a prior season's squad, say), so a hardcoded
    analytics.STARTING_BALANCE (20,000,000) can silently diverge from
    reality -- confirmed for this league: after an exhaustive search (every
    board event, over a dozen API endpoints, the app's own stats/value
    history views) turned up no missing transaction, the account owner's
    real balance still differs from the flat-20M reconstruction by a fixed
    amount. The API exposes that owner's real current balance even though
    the league hides every OTHER manager's (``client.get_own_balance``), so
    that one real number is used to back-solve what the season must have
    actually started with: real balance minus the net of every synced event
    for that owner. That corrected figure is then applied to EVERY manager,
    since a season-transition reset is a league-wide mechanic -- it is the
    best available approximation for the other managers, not a verified fact
    for them the way it is for the owner (see dashboard.py's disclosure).

    If the API can't report the owner's balance (e.g. they've left the
    league), sync_state is left untouched -- callers fall back to
    analytics.STARTING_BALANCE.
    """
    own_balance = client.get_own_balance()
    if own_balance is None:
        return

    events = db.get_all_money_events(conn)
    net_for_owner = analytics.compute_current_balances(events, starting_balance=0).get(owner_user_id, 0)
    starting_balance = own_balance - net_for_owner

    db.set_sync_state(conn, "owner_user_id", str(owner_user_id))
    db.set_sync_state(conn, "owner_real_balance", str(own_balance))
    db.set_sync_state(conn, "starting_balance", str(starting_balance))


def sync_players(client, conn):
    events = db.get_all_money_events(conn)
    known_ids = db.get_known_player_ids(conn)
    needed_ids = {e["player_id"] for e in events if e["player_id"] is not None}
    missing_ids = needed_ids - known_ids

    # A known player can be missing team_id from before the crest feature existed,
    # or because they weren't on anyone's squad yet when their identity was first
    # resolved. Retry those against the bulk catalog too so a movement involving a
    # player nobody currently owns still gets its team crest -- not just the ones
    # sync_squads_and_form happens to touch because they're on a squad right now.
    team_id_backfill_ids = db.get_player_ids_missing_team_id(conn) - missing_ids

    if not missing_ids and not team_id_backfill_ids:
        return

    players = client.get_players()
    still_missing = []
    for player_id in missing_ids:
        info = players.get(player_id)
        if info:
            db.upsert_player(
                conn, player_id, info["name"],
                team=info.get("team"), position=info.get("position"), team_id=info.get("team_id"),
            )
        else:
            still_missing.append(player_id)

    # A player who has since left La Liga drops out of the bulk catalog above (it
    # only lists currently active players), so fall back to looking them up one by
    # one -- otherwise they'd be stuck forever as the placeholder "Jugador <id>" in
    # movement descriptions, since sync_players only retries ids still missing from
    # the players table on each run and this bulk endpoint would never resolve them.
    for player_id in still_missing:
        info = client.get_player(player_id)
        if info:
            db.upsert_player(
                conn, player_id, info["name"],
                team=info.get("team"), position=info.get("position"), team_id=info.get("team_id"),
            )

    for player_id in team_id_backfill_ids:
        info = players.get(player_id)
        # Not in the bulk catalog at all means they're genuinely off any current La
        # Liga roster (not a transient gap) -- team_id stays None, correctly.
        if info and info.get("team_id"):
            db.upsert_player(
                conn, player_id, info["name"],
                team=info.get("team"), position=info.get("position"), team_id=info["team_id"],
            )


def sync_squads_and_form(client, conn, users):
    """Snapshot every manager's current squad, plus the identity/price/form of
    EVERY player in the current La Liga catalog (not just owned ones) and the
    next round's per-team fixture difficulty.

    Unlike sync_players (which only backfills players referenced by a money
    event), a player kept since before the tracked history has no purchase
    event at all -- this is the only place their name/team/position gets
    stored, since it reads the live squad directly instead of the board log.
    Syncing the whole catalog (not just owned_ids) is what makes a market-wide
    points-per-euro ranking possible -- a manager's best transfer target is
    rarely someone already on a squad in this league.
    """
    catalog = client.get_players()

    for user in users:
        squad = client.get_manager_squad(user["id"])
        db.replace_squad(conn, user["id"], squad)

    for player_id, info in catalog.items():
        db.upsert_player(
            conn, player_id, info["name"],
            team=info.get("team"), position=info.get("position"), team_id=info.get("team_id"),
        )
        db.upsert_player_market(conn, player_id, info.get("price"), info.get("season_points"))
        db.upsert_player_form(
            conn, player_id, json.dumps(info["recent_points"]), info["status"], info.get("status_info"),
        )

    db.replace_team_fixtures(conn, client.get_next_round_fixtures())


def main():
    config = load_config()
    client = BiwengerClient(config["token"], config["league_id"], config["user_id"])
    conn = db.init_db(DB_PATH)

    try:
        users = client.get_league_users()
        for user in users:
            db.upsert_user(conn, user["id"], user["name"], user.get("icon"))

        sync_board(client, conn)
        sync_players(client, conn)
        sync_squads_and_form(client, conn, users)
        calibrate_starting_balance(client, conn, config["user_id"])

        for standing in client.get_standings():
            db.upsert_standing(conn, standing["id"], standing["points"], standing["position"])
    except BiwengerAuthError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)

    print(f"Sync complete. {len(db.get_all_money_events(conn))} money movements in {DB_PATH}.")


if __name__ == "__main__":
    main()
