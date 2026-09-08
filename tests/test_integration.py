"""End-to-end test: real raw board items flowing through the full chain
board_parser -> db -> sync -> analytics -> dashboard, instead of hand-shaped fixture
dicts mimicking each module's neighbor's output.
"""
import dashboard
import db
import sync


class FakeClient:
    """Same fake-paging client used in tests/test_sync.py."""

    def __init__(self, pages):
        self._pages = pages
        self.calls = []

    def get_board_page(self, offset, limit=500):
        self.calls.append(offset)
        index = offset // limit
        return self._pages[index] if index < len(self._pages) else []


# Raw items mirroring the confirmed live shapes documented in the implementation plan's
# "Reference: confirmed Biwenger API shapes" section (and tests/test_board_parser.py).

# Sale to the market (only "from"): Giotto sells a player and receives 378,000 EUR.
TRANSFER_SALE_TO_MARKET = {
    "type": "transfer",
    "content": [{
        "player": 23572,
        "from": {"id": 12686032, "name": "Giotto di Bondone"},
        "amount": 378000,
    }],
    "date": 1788845299,
}

# Purchase from the market, paid by "to": Cerveceria Gaira spends 1,960,000 EUR.
MARKET_PURCHASE = {
    "type": "market",
    "content": [{
        "player": 18128,
        "to": {"id": 12683799, "name": "Cerveceria Gaira"},
        "amount": 1960000,
    }],
    "date": 1788843853,
}

# Weekly points-based money: Giotto earns a 2,325,000 EUR round bonus.
ROUND_FINISHED = {
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
        ],
    },
    "date": 1788700000,
}


def test_full_pipeline_from_raw_board_items_to_dashboard_html():
    conn = db.init_db(":memory:")
    client = FakeClient(pages=[[TRANSFER_SALE_TO_MARKET, MARKET_PURCHASE, ROUND_FINISHED]])

    # board_parser -> db, driven by the real sync_board (not hand-inserted rows).
    sync.sync_board(client, conn)

    db.upsert_user(conn, 12686032, "Giotto di Bondone", None)
    db.upsert_user(conn, 12683799, "Cerveceria Gaira", None)
    db.upsert_standing(conn, 12686032, 76, 1)
    db.upsert_standing(conn, 12683799, 0, 2)

    # db -> analytics -> dashboard, driven by the real build_dashboard_html.
    output = dashboard.build_dashboard_html(conn)

    assert "<html" in output
    assert "Giotto di Bondone" in output
    assert "Cerveceria Gaira" in output

    # Giotto: 20,000,000 starting balance + 378,000 (sale to market) +
    # 2,325,000 (round bonus) = 22,703,000 EUR. This value only comes out right if
    # board_parser correctly attributed both events to user 12686032 as income, db
    # stored and returned them, analytics.compute_current_balances summed them onto
    # the starting balance, and dashboard rendered the result.
    assert "22,703,000" in output
