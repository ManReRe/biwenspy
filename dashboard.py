"""Generate a self-contained HTML dashboard from biwenger.db."""
import html
from collections import defaultdict
from datetime import datetime

import plotly.graph_objects as go
from plotly.offline import plot

import analytics
import db

DB_PATH = "biwenger.db"
OUTPUT_PATH = "dashboard.html"

STYLE = """
:root {
  --bg: #f4f5f8;
  --card-bg: #ffffff;
  --text: #1a1a2e;
  --text-muted: #6b7280;
  --primary: #4f46e5;
  --primary-light: #eef2ff;
  --income: #16a34a;
  --expense: #dc2626;
  --border: #e5e7eb;
}
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: var(--bg); color: var(--text); margin: 0; padding: 24px 16px;
}
.container { max-width: 1080px; margin: 0 auto; }
h1 { font-size: 1.6rem; margin: 0 0 2px; }
.subtitle { color: var(--text-muted); margin: 0 0 20px; font-size: 0.95rem; }
.card { background: var(--card-bg); border-radius: 14px; padding: 20px 24px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.07); }
.card h2 { font-size: 1.1rem; margin: 0 0 14px; }
.tabs { display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 2px solid var(--border); flex-wrap: wrap; }
.tab-btn {
  background: none; border: none; padding: 10px 18px; font-size: 0.95rem; font-weight: 600;
  color: var(--text-muted); cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -2px;
}
.tab-btn.active { color: var(--primary); border-bottom-color: var(--primary); }
.tab-panel { display: none; }
.tab-panel.active { display: block; }
table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
th { text-align: left; padding: 10px 12px; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--border); white-space: nowrap; }
td { padding: 10px 12px; border-bottom: 1px solid var(--border); }
tr:last-child td { border-bottom: none; }
.table-wrap { overflow-x: auto; }
.amount-income { color: var(--income); font-weight: 600; }
.amount-expense { color: var(--expense); font-weight: 600; }
.amount-balance { color: var(--text-muted); font-weight: 600; }
select {
  padding: 9px 14px; border-radius: 8px; border: 1px solid var(--border); font-size: 0.95rem;
  margin-bottom: 16px; background: var(--card-bg); color: var(--text);
}
.fact-list { list-style: none; padding: 0; margin: 0; }
.fact-list li { padding: 10px 0; border-bottom: 1px solid var(--border); font-size: 0.92rem; }
.fact-list li:last-child { border-bottom: none; }
.disclosure {
  background: #fffbeb; border: 1px solid #fde68a; border-radius: 10px; padding: 14px 16px;
  font-size: 0.85rem; color: #78350f; margin-top: 14px;
}
.manager-panel { display: none; }
.manager-panel.active { display: block; }
.badge { display: inline-block; background: var(--primary-light); color: var(--primary); border-radius: 999px; padding: 2px 10px; font-size: 0.78rem; font-weight: 600; }
"""

SCRIPT = """
function showTab(id) {
  document.querySelectorAll('.tab-panel').forEach(function(p) { p.classList.remove('active'); });
  document.querySelectorAll('.tab-btn').forEach(function(b) { b.classList.remove('active'); });
  document.getElementById('tab-' + id).classList.add('active');
  document.getElementById('btn-' + id).classList.add('active');
}
function showManager(userId) {
  document.querySelectorAll('.manager-panel').forEach(function(p) { p.classList.remove('active'); });
  var panel = document.getElementById('manager-' + userId);
  if (panel) { panel.classList.add('active'); }
}
"""


def _format_date(date_int):
    """Render a Biwenger epoch-seconds timestamp as a human-readable date."""
    if date_int is None:
        return ""
    return datetime.fromtimestamp(date_int).strftime("%Y-%m-%d")


def _balance_chart(balance_timelines, names):
    fig = go.Figure()
    for user_id, points in balance_timelines.items():
        if not points:
            continue
        fig.add_trace(go.Scatter(
            x=[_format_date(p[0]) for p in points], y=[p[1] for p in points],
            mode="lines+markers", name=names.get(user_id, str(user_id)),
        ))
    fig.update_layout(title="Dinero disponible por manager", xaxis_title="Fecha", yaxis_title="EUR")
    return fig


def _points_chart(points_timelines, names):
    fig = go.Figure()
    for user_id, points in points_timelines.items():
        if not points:
            continue
        fig.add_trace(go.Scatter(
            x=[_format_date(p[0]) for p in points], y=[p[1] for p in points],
            mode="lines+markers", name=names.get(user_id, str(user_id)),
        ))
    fig.update_layout(title="Puntos acumulados por manager", xaxis_title="Fecha", yaxis_title="Puntos")
    return fig


def _standings_table_html(standings, names, current_balances, starting_balance):
    rows = []
    for row in standings:
        name = html.escape(names.get(row["user_id"], str(row["user_id"])))
        # A manager with zero recorded money events hasn't traded yet, so their
        # balance is still the starting amount, not 0.
        balance = current_balances.get(row["user_id"], starting_balance)
        rows.append(
            f"<tr><td>{row['position']}</td><td>{name}</td>"
            f"<td>{row['points']}</td><td>{balance:,.0f} EUR</td></tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr><th>Pos.</th><th>Manager</th><th>Puntos</th>'
        "<th>Dinero</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def _real_balance_check_html(names, owner_user_id, owner_real_balance, owner_computed_balance, starting_balance):
    if owner_user_id is None or owner_real_balance is None:
        return ""
    owner_name = html.escape(names.get(owner_user_id, str(owner_user_id)))
    diff = owner_computed_balance - owner_real_balance

    if diff == 0:
        return (
            '<div class="disclosure">Comprobacion: el dinero de partida '
            f"({starting_balance:,} EUR) esta calibrado contra el saldo real de {owner_name} en "
            f"Biwenger -- su saldo reconstruido coincide exacto: {owner_computed_balance:,} EUR. "
            "Para el resto de managers esa misma cifra de partida es la mejor aproximacion "
            "disponible, no un dato verificado: Biwenger no deja consultar el saldo de nadie mas "
            "que la cuenta autenticada, ni registra ningun evento para el reparto de presupuesto "
            "en el cambio de temporada."
            "</div>"
        )

    return (
        '<div class="disclosure">Comprobacion (no usada para ajustar ningun calculo): el saldo real de '
        f"{owner_name} en Biwenger es {owner_real_balance:,} EUR; el saldo reconstruido "
        f"({starting_balance:,} EUR de partida + movimientos del muro) da {owner_computed_balance:,} EUR "
        f"-- una diferencia de {diff:,} EUR. Biwenger no registra ningun evento para el reparto "
        "de presupuesto en el cambio de temporada, asi que una plantilla heredada de la "
        "temporada anterior puede explicar esta diferencia sin que sea un fallo de calculo."
        "</div>"
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
    return f'<ul class="fact-list">{"".join(items)}</ul>' if items else "<p>Sin datos todavia.</p>"


def _breakdown_table_html(breakdown, names):
    rows = []
    for user_id, values in breakdown.items():
        rows.append(
            f"<tr><td>{html.escape(names.get(user_id, str(user_id)))}</td>"
            f"<td>{values['points']:,} EUR</td><td>{values['sales']:,} EUR</td>"
            f"<td>{values['purchases']:,} EUR</td></tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr><th>Manager</th><th>Ingresos por puntos</th>'
        "<th>Ingresos por ventas</th><th>Gastos en fichajes</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def _movement_description(event, names, players, rounds_by_id):
    # player_id is genuinely None (not merely unresolvable) for roundFinished events,
    # and in principle for a market/transfer movement missing its "player" field. In
    # either case analytics.player_name(players, None) returns None -- guard every
    # branch that mentions a player so that value never gets interpolated into the
    # description (which would otherwise render the literal text "None").
    player = analytics.player_name(players, event["player_id"])
    counterparty = names.get(event["counterparty_id"]) if event["counterparty_id"] else None

    if event["type"] == "roundFinished":
        round_name = rounds_by_id.get(event["round_id"])
        return f"Bonus de {round_name}" if round_name else "Bonus de jornada"
    if event["type"] == "market":
        return f"Compra de {player} al mercado" if player else "Compra al mercado"
    if event["type"] == "transfer" and event["direction"] == "income":
        if not player:
            return f"Venta a {counterparty}" if counterparty else "Venta al mercado"
        return f"Venta de {player} a {counterparty}" if counterparty else f"Venta de {player} al mercado"
    if event["type"] == "transfer" and event["direction"] == "expense":
        if not player:
            return f"Compra a {counterparty}" if counterparty else "Compra a un manager desconocido"
        return f"Compra de {player} a {counterparty}" if counterparty else f"Compra de {player} a un manager desconocido"
    return event["type"]


def _movements_tab_html(events, names, players, users, rounds_by_id, running_balances):
    by_user = defaultdict(list)
    for event in events:
        by_user[event["user_id"]].append(event)

    # Every manager gets an <option>, even one with zero movements, so the
    # selector always lists the full roster.
    user_ids_in_order = [u["id"] for u in users]
    for user_id in by_user:
        if user_id not in user_ids_in_order:
            user_ids_in_order.append(user_id)

    if not user_ids_in_order:
        return "<p>Sin managers todavia.</p>"

    options = []
    panels = []
    for index, user_id in enumerate(user_ids_in_order):
        user_events = by_user.get(user_id, [])
        manager_name = html.escape(names.get(user_id, str(user_id)))
        options.append(
            f'<option value="{user_id}">{manager_name} ({len(user_events)} movimientos)</option>'
        )

        total_income = sum(e["amount"] for e in user_events if e["direction"] == "income")
        total_expense = sum(e["amount"] for e in user_events if e["direction"] == "expense")
        net = total_income - total_expense
        net_class = "amount-income" if net >= 0 else "amount-expense"
        net_sign = "+" if net >= 0 else ""
        summary = (
            '<p class="movements-summary">'
            f"Ingresos totales: {total_income:,} EUR &nbsp;&middot;&nbsp; "
            f"Gastos totales: {total_expense:,} EUR &nbsp;&middot;&nbsp; "
            f'Neto por transacciones: <span class="{net_class}">{net_sign}{net:,} EUR</span>'
            "</p>"
        )

        rows = []
        # Sort ascending then reverse the whole list (rather than sorted(..., reverse=True))
        # so that events sharing the exact same timestamp -- e.g. several simultaneous
        # market purchases in one settlement -- come out in TRUE reverse-chronological
        # order. sorted(reverse=True) is stable but keeps tied elements in their original
        # ascending order, which would misalign the newest-first display against
        # running_balances (computed by replaying events in ascending order), making the
        # balance look inverted for any two operations that landed in the same instant.
        for event in reversed(sorted(user_events, key=lambda e: e["date"])):
            is_income = event["direction"] == "income"
            sign = "+" if is_income else "-"
            css_class = "amount-income" if is_income else "amount-expense"
            description = html.escape(_movement_description(event, names, players, rounds_by_id))
            balance_after = running_balances.get(event["id"])
            balance_cell = f"{balance_after:,} EUR" if balance_after is not None else "-"
            rows.append(
                f"<tr><td>{_format_date(event['date'])}</td><td>{description}</td>"
                f'<td class="{css_class}">{sign}{event["amount"]:,} EUR</td>'
                f'<td class="amount-balance">{balance_cell}</td></tr>'
            )
        empty_row = '<tr><td colspan="4">Sin movimientos todavia.</td></tr>'
        rows_html = "".join(rows) if rows else empty_row
        table = (
            '<div class="table-wrap"><table><thead><tr><th>Fecha</th><th>Movimiento</th>'
            "<th>Importe</th><th>Saldo</th></tr></thead>"
            f"<tbody>{rows_html}</tbody></table></div>"
        )
        active_class = " active" if index == 0 else ""
        panels.append(f'<div class="manager-panel{active_class}" id="manager-{user_id}">{summary}{table}</div>')

    select_html = (
        f'<select id="managerSelect" onchange="showManager(this.value)">{"".join(options)}</select>'
    )
    return select_html + "".join(panels)


def _jornadas_tab_html(round_bonus_rows, standings, names):
    if not round_bonus_rows:
        return "<p>Sin jornadas todavia.</p>"

    # Manager columns in league-standings order; defensively append anyone who
    # somehow has a bonus but no standings row.
    user_ids = [s["user_id"] for s in sorted(standings, key=lambda r: r["position"])]
    for row in round_bonus_rows:
        for user_id in row["amounts"]:
            if user_id not in user_ids:
                user_ids.append(user_id)

    header_cells = "".join(f"<th>{html.escape(names.get(uid, str(uid)))}</th>" for uid in user_ids)

    totals = defaultdict(int)
    body_rows = []
    for row in round_bonus_rows:
        cells = []
        for user_id in user_ids:
            amount = row["amounts"].get(user_id)
            if amount is None:
                cells.append("<td>-</td>")
            else:
                totals[user_id] += amount
                cells.append(f"<td>{amount:,} EUR</td>")
        body_rows.append(f"<tr><td>{html.escape(row['name'])}</td>{''.join(cells)}</tr>")

    total_cells = "".join(f"<td><strong>{totals.get(uid, 0):,} EUR</strong></td>" for uid in user_ids)
    total_row = f"<tr><td><strong>Total</strong></td>{total_cells}</tr>"

    return (
        '<div class="table-wrap"><table><thead><tr><th>Jornada</th>' + header_cells + "</tr></thead>"
        f"<tbody>{''.join(body_rows)}{total_row}</tbody></table></div>"
    )


def build_dashboard_html(conn):
    users = db.get_users(conn)
    names = {u["id"]: u["name"] for u in users}
    events = db.get_all_money_events(conn)
    round_points = db.get_all_round_points(conn)
    rounds = db.get_all_rounds(conn)
    rounds_by_id = {r["id"]: r["name"] for r in rounds}
    standings = db.get_standings(conn)
    players = db.get_players(conn)

    # sync.py's calibrate_starting_balance back-solves the real season-starting
    # balance from the account owner's real current balance (Biwenger's board
    # has no event for the season-transition budget reset, so a hardcoded
    # 20,000,000 can silently diverge from reality -- confirmed for this
    # league). That calibrated figure is applied uniformly to every manager;
    # fall back to the plain 20,000,000 default if calibration hasn't run yet
    # (e.g. dashboard.py before any sync). See _real_balance_check_html for
    # the disclosure of what's verified (the owner) vs. approximated (everyone
    # else).
    starting_balance_raw = db.get_sync_state(conn, "starting_balance")
    starting_balance = int(starting_balance_raw) if starting_balance_raw is not None else analytics.STARTING_BALANCE
    owner_user_id_raw = db.get_sync_state(conn, "owner_user_id")
    owner_user_id = int(owner_user_id_raw) if owner_user_id_raw is not None else None
    owner_real_balance_raw = db.get_sync_state(conn, "owner_real_balance")
    owner_real_balance = int(owner_real_balance_raw) if owner_real_balance_raw is not None else None

    balance_timelines = analytics.compute_balance_timeline(events, starting_balance=starting_balance)
    running_balances = analytics.compute_running_balances(events, starting_balance=starting_balance)
    current_balances = analytics.compute_current_balances(events, starting_balance=starting_balance)
    points_timelines = analytics.compute_points_timeline(round_points, rounds)
    facts = analytics.compute_curious_facts(events, players, users)
    breakdown = analytics.compute_income_breakdown(events, users)
    biggest_bonus_round = analytics.compute_biggest_bonus_round(events, rounds)
    round_bonus_rows = analytics.compute_round_bonus_table(events, rounds)

    balance_fig_html = plot(_balance_chart(balance_timelines, names), output_type="div", include_plotlyjs=True)
    points_fig_html = plot(_points_chart(points_timelines, names), output_type="div", include_plotlyjs=False)

    owner_computed_balance = current_balances.get(owner_user_id, starting_balance)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard Biwenger</title>
<style>{STYLE}</style>
</head>
<body>
<div class="container">
<h1>LA SECTA -- Dashboard financiero</h1>
<p class="subtitle">Dinero de partida por manager esta temporada: {starting_balance:,} EUR</p>

<div class="tabs">
<button class="tab-btn active" id="btn-resumen" onclick="showTab('resumen')">Resumen</button>
<button class="tab-btn" id="btn-desglose" onclick="showTab('desglose')">Desglose</button>
<button class="tab-btn" id="btn-jornadas" onclick="showTab('jornadas')">Jornadas</button>
<button class="tab-btn" id="btn-movimientos" onclick="showTab('movimientos')">Movimientos</button>
<button class="tab-btn" id="btn-curiosidades" onclick="showTab('curiosidades')">Curiosidades</button>
</div>

<div class="tab-panel active" id="tab-resumen">
<div class="card">
<h2>Clasificacion</h2>
{_standings_table_html(standings, names, current_balances, starting_balance)}
{_real_balance_check_html(names, owner_user_id, owner_real_balance, owner_computed_balance, starting_balance)}
</div>
<div class="card">
<h2>Evolucion del dinero</h2>
{balance_fig_html}
</div>
<div class="card">
<h2>Evolucion de puntos</h2>
{points_fig_html}
</div>
</div>

<div class="tab-panel" id="tab-desglose">
<div class="card">
<h2>Desglose de ingresos y gastos</h2>
{_breakdown_table_html(breakdown, names)}
</div>
</div>

<div class="tab-panel" id="tab-jornadas">
<div class="card">
<h2>Dinero ganado por jornada</h2>
{_jornadas_tab_html(round_bonus_rows, standings, names)}
</div>
</div>

<div class="tab-panel" id="tab-movimientos">
<div class="card">
<h2>Movimientos por manager</h2>
{_movements_tab_html(events, names, players, users, rounds_by_id, running_balances)}
</div>
</div>

<div class="tab-panel" id="tab-curiosidades">
<div class="card">
<h2>Datos curiosos</h2>
{_facts_html(facts, biggest_bonus_round)}
</div>
</div>

</div>
<script>{SCRIPT}</script>
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
