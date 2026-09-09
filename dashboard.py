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
  --bg: #0b0e14;
  --card-bg: #151922;
  --text: #e8eaed;
  --text-muted: #8b93a3;
  --primary: #6d7bff;
  --primary-light: rgba(109, 123, 255, 0.16);
  --income: #34d399;
  --expense: #f87171;
  --border: #262b36;
}
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: var(--bg); color: var(--text); margin: 0; padding: 24px 16px;
}
.container { max-width: 1080px; margin: 0 auto; }
h1 { font-size: 1.6rem; margin: 0 0 2px; }
.subtitle { color: var(--text-muted); margin: 0 0 20px; font-size: 0.95rem; }
.card {
  background: var(--card-bg); border-radius: 14px; padding: 20px 24px; margin-bottom: 20px;
  border: 1px solid var(--border); box-shadow: 0 1px 2px rgba(0, 0, 0, 0.4);
}
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
.table-wrap {
  overflow-x: auto;
  /* "Scroll shadow" trick: two solid gradients matching the card background scroll
     WITH the content and mask the shadow near an edge once there's nothing left to
     scroll past it; two shadow gradients stay fixed (background-attachment: scroll)
     so they only show while there's still content off-screen in that direction.
     Without this, a table wider than its card just gets cut off with no visual hint
     that there's more to see -- it looks broken rather than scrollable. */
  background:
    linear-gradient(to right, var(--card-bg) 30%, rgba(0, 0, 0, 0)) 0 0,
    linear-gradient(to left, var(--card-bg) 30%, rgba(0, 0, 0, 0)) 100% 0,
    linear-gradient(to right, rgba(255, 255, 255, 0.14), rgba(255, 255, 255, 0)) 0 0,
    linear-gradient(to left, rgba(255, 255, 255, 0.14), rgba(255, 255, 255, 0)) 100% 0;
  background-repeat: no-repeat;
  background-color: var(--card-bg);
  background-size: 32px 100%, 32px 100%, 12px 100%, 12px 100%;
  background-attachment: local, local, scroll, scroll;
}
.table-wrap::-webkit-scrollbar { height: 8px; }
.table-wrap::-webkit-scrollbar-track { background: transparent; }
.table-wrap::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
.table-wrap { scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
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
  background: rgba(217, 119, 6, 0.12); border: 1px solid rgba(217, 119, 6, 0.35);
  border-radius: 10px; padding: 14px 16px; font-size: 0.85rem; color: #fbbf24; margin-top: 14px;
}
.manager-panel { display: none; }
.manager-panel.active { display: block; }
.badge { display: inline-block; background: var(--primary-light); color: var(--primary); border-radius: 999px; padding: 2px 10px; font-size: 0.78rem; font-weight: 600; }
.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.jornadas-table th { white-space: normal; max-width: 96px; }
.jornadas-table .jornada-name {
  position: sticky; left: 0; background: var(--card-bg); z-index: 1; white-space: nowrap;
  box-shadow: 1px 0 0 var(--border);
}
.cell-best { background: var(--primary-light); border-radius: 6px; font-weight: 700; }
.totals-row td { border-top: 2px solid var(--border); }
.scroll-hint { color: var(--primary); font-size: 0.82rem; font-weight: 600; margin: 0 0 8px; }
.avatar {
  width: 28px; height: 28px; border-radius: 50%; object-fit: cover; vertical-align: middle;
  margin-right: 8px; background: var(--border);
}
.avatar-sm { width: 22px; height: 22px; margin-right: 6px; }
.panel-header {
  display: flex; align-items: center; gap: 10px; margin-bottom: 14px; font-size: 1.05rem;
  font-weight: 700;
}
.panel-header .avatar { width: 32px; height: 32px; margin-right: 0; }
.player-icons { display: inline-flex; align-items: center; margin-right: 8px; vertical-align: middle; }
.player-icons .crest { width: 16px; height: 16px; margin-right: 4px; }
.player-icons .player-photo {
  width: 26px; height: 26px; border-radius: 50%; object-fit: cover; background: var(--border);
}
"""

SCRIPT = """
function showTab(id) {
  document.querySelectorAll('.tab-panel').forEach(function(p) { p.classList.remove('active'); });
  document.querySelectorAll('.tab-btn').forEach(function(b) { b.classList.remove('active'); });
  document.getElementById('tab-' + id).classList.add('active');
  document.getElementById('btn-' + id).classList.add('active');
}
function showManager(prefix, userId) {
  document.querySelectorAll('.manager-panel[data-prefix="' + prefix + '"]').forEach(function(p) {
    p.classList.remove('active');
  });
  var panel = document.getElementById('manager-' + prefix + '-' + userId);
  if (panel) { panel.classList.add('active'); }
}
"""


def _format_date(date_int):
    """Render a Biwenger epoch-seconds timestamp as a human-readable date."""
    if date_int is None:
        return ""
    return datetime.fromtimestamp(date_int).strftime("%Y-%m-%d")


# Base for Biwenger's public image CDN. Confirmed live: it serves user avatars,
# player photos and team crests without authentication, as long as the request
# carries browser-like Origin/Referer headers (which only matters for the API
# client, not for an <img> tag loaded by a real browser viewing dashboard.html).
_CDN_BASE = "https://cdn.biwenger.com/"


def _user_avatar_url(icon):
    return f"{_CDN_BASE}{icon}" if icon else None


def _player_photo_url(player_id):
    return f"{_CDN_BASE}i/p/{player_id}.png" if player_id else None


def _team_crest_url(team_id):
    return f"{_CDN_BASE}i/t/{team_id}.png" if team_id else None


def _avatar_img_html(icon, css_class="avatar"):
    """<img> for a manager's avatar, or "" if there's no icon on file.

    Carries onerror to silently hide itself on a broken/missing image rather
    than showing the browser's broken-image icon.
    """
    url = _user_avatar_url(icon)
    if not url:
        return ""
    return f'<img class="{css_class}" src="{html.escape(url)}" alt="" onerror="this.style.display=\'none\'">'


def _player_icons_html(player_id, team_id):
    """<span> with the team crest (if known) and the player's photo, or "" for
    a playerless event (e.g. a roundFinished bonus). Same onerror fallback as
    _avatar_img_html -- with 500+ players it's not worth checking in advance
    which ones actually have a photo on the CDN."""
    if player_id is None:
        return ""
    crest = ""
    if team_id:
        crest_url = html.escape(_team_crest_url(team_id))
        crest = f'<img class="crest" src="{crest_url}" alt="" onerror="this.style.display=\'none\'">'
    photo_url = html.escape(_player_photo_url(player_id))
    photo = f'<img class="player-photo" src="{photo_url}" alt="" onerror="this.style.display=\'none\'">'
    return f'<span class="player-icons">{crest}{photo}</span>'


def _balance_chart(balance_timelines, names):
    fig = go.Figure()
    for user_id, points in balance_timelines.items():
        if not points:
            continue
        fig.add_trace(go.Scatter(
            x=[_format_date(p[0]) for p in points], y=[p[1] for p in points],
            mode="lines+markers", name=names.get(user_id, str(user_id)),
        ))
    fig.update_layout(
        title="Dinero disponible por manager", xaxis_title="Fecha", yaxis_title="EUR",
        template="plotly_dark", paper_bgcolor="#151922", plot_bgcolor="#151922",
        font_color="#e8eaed",
    )
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
    fig.update_layout(
        title="Puntos acumulados por manager", xaxis_title="Fecha", yaxis_title="Puntos",
        template="plotly_dark", paper_bgcolor="#151922", plot_bgcolor="#151922",
        font_color="#e8eaed",
    )
    return fig


def _standings_table_html(standings, names, icons, current_balances, starting_balance):
    rows = []
    for row in standings:
        avatar = _avatar_img_html(icons.get(row["user_id"]))
        name = html.escape(names.get(row["user_id"], str(row["user_id"])))
        # A manager with zero recorded money events hasn't traded yet, so their
        # balance is still the starting amount, not 0.
        balance = current_balances.get(row["user_id"], starting_balance)
        rows.append(
            f"<tr><td>{row['position']}</td><td>{avatar}{name}</td>"
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


def _movements_tab_html(events, names, icons, players, users, rounds_by_id, running_balances):
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
        panel_header = (
            f'<div class="panel-header">{_avatar_img_html(icons.get(user_id))}{manager_name}</div>'
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
            player_info = players.get(event["player_id"], {})
            icons_html = _player_icons_html(event["player_id"], player_info.get("team_id"))
            description = html.escape(_movement_description(event, names, players, rounds_by_id))
            balance_after = running_balances.get(event["id"])
            balance_cell = f"{balance_after:,} EUR" if balance_after is not None else "-"
            rows.append(
                f"<tr><td>{_format_date(event['date'])}</td><td>{icons_html}{description}</td>"
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
        panels.append(
            f'<div class="manager-panel{active_class}" data-prefix="movimientos" '
            f'id="manager-movimientos-{user_id}">{panel_header}{summary}{table}</div>'
        )

    select_html = (
        '<select id="managerSelect-movimientos" onchange="showManager(\'movimientos\', this.value)">'
        f'{"".join(options)}</select>'
    )
    return select_html + "".join(panels)


POSITION_LABELS = {1: "Portero", 2: "Defensa", 3: "Centrocampista", 4: "Delantero"}


def _position_label(position):
    return POSITION_LABELS.get(position, "?")


def _squads_tab_html(squad_table, names, icons, users):
    user_ids_in_order = [u["id"] for u in users]
    for user_id in squad_table:
        if user_id not in user_ids_in_order:
            user_ids_in_order.append(user_id)

    if not user_ids_in_order:
        return "<p>Sin managers todavia.</p>"

    options = []
    panels = []
    for index, user_id in enumerate(user_ids_in_order):
        rows = squad_table.get(user_id, [])
        manager_name = html.escape(names.get(user_id, str(user_id)))
        options.append(f'<option value="{user_id}">{manager_name} ({len(rows)} jugadores)</option>')
        panel_header = (
            f'<div class="panel-header">{_avatar_img_html(icons.get(user_id))}{manager_name}</div>'
        )

        row_html = []
        for player in rows:
            price = f"{player['price_paid']:,} EUR" if player["price_paid"] is not None else "-"
            acquired = _format_date(player["acquired_date"]) if player["acquired_date"] else "-"
            icons_html = _player_icons_html(player["player_id"], player.get("team_id"))
            row_html.append(
                f"<tr><td>{_position_label(player['position'])}</td>"
                f"<td>{icons_html}{html.escape(player['name'])}</td>"
                f"<td>{html.escape(player['team'] or '-')}</td>"
                f"<td>{price}</td><td>{acquired}</td></tr>"
            )
        empty_row = '<tr><td colspan="5">Sin jugadores todavia.</td></tr>'
        rows_html = "".join(row_html) if row_html else empty_row
        table = (
            '<div class="table-wrap"><table><thead><tr><th>Posicion</th><th>Jugador</th>'
            "<th>Equipo</th><th>Precio pagado</th><th>Fichado</th></tr></thead>"
            f"<tbody>{rows_html}</tbody></table></div>"
        )
        active_class = " active" if index == 0 else ""
        panels.append(
            f'<div class="manager-panel{active_class}" data-prefix="plantillas" '
            f'id="manager-plantillas-{user_id}">{panel_header}{table}</div>'
        )

    select_html = (
        '<select id="managerSelect-plantillas" onchange="showManager(\'plantillas\', this.value)">'
        f'{"".join(options)}</select>'
    )
    return select_html + "".join(panels)


def _lineup_rows_html(lineup):
    captain_id = lineup["captain"]["player_id"]
    rows = []
    for player in lineup["starters"]:
        captain_badge = ' <span class="badge">C</span>' if player["player_id"] == captain_id else ""
        name_cell = html.escape(player["name"]) + captain_badge
        rows.append(
            f"<tr><td>{_position_label(player['position'])}</td><td>{name_cell}</td>"
            f"<td>{player['avg_points']:.1f}</td></tr>"
        )
    return "".join(rows)


def _lineup_html(lineup):
    if lineup is None:
        return "<p>No hay suficientes jugadores disponibles en la plantilla para sugerir una alineacion.</p>"
    rows_html = _lineup_rows_html(lineup)
    return (
        f'<p><strong>Formacion sugerida:</strong> {lineup["formation"]} '
        f'&nbsp;&middot;&nbsp; Puntos esperados (suma de medias recientes): {lineup["total_points"]:.1f}</p>'
        '<div class="table-wrap"><table><thead><tr><th>Posicion</th><th>Jugador</th>'
        "<th>Media puntos recientes</th></tr></thead>"
        f"<tbody>{rows_html}</tbody></table></div>"
    )


def _market_profile_html(profile):
    return (
        '<div class="table-wrap"><table><tbody>'
        f"<tr><td>Caja actual</td><td>{profile['cash']:,} EUR</td></tr>"
        f"<tr><td>Operaciones totales</td><td>{profile['total_trades']}</td></tr>"
        f"<tr><td>Gasto medio por fichaje</td><td>{profile['avg_purchase']:,} EUR</td></tr>"
        f"<tr><td>Ingreso medio por venta</td><td>{profile['avg_sale']:,} EUR</td></tr>"
        f"<tr><td>Operaciones en los ultimos 14 dias</td><td>{profile['recent_trades']}</td></tr>"
        "</tbody></table></div>"
    )


_EMPTY_MARKET_PROFILE = {"cash": 0, "total_trades": 0, "avg_purchase": 0, "avg_sale": 0, "recent_trades": 0}


def _next_round_tab_html(users, names, icons, squad_table, players, player_form, market_profile):
    user_ids_in_order = [u["id"] for u in users]
    for user_id in squad_table:
        if user_id not in user_ids_in_order:
            user_ids_in_order.append(user_id)

    if not user_ids_in_order:
        return "<p>Sin managers todavia.</p>"

    lineup_disclosure = (
        '<div class="disclosure">Esto es una sugerencia calculada a partir de la plantilla real '
        "y la media de puntos de las ultimas jornadas jugadas -- Biwenger no publica la "
        "alineacion real de otro manager hasta que la jornada ya ha empezado, asi que esto NO "
        "es necesariamente lo que ese manager vaya a poner.</div>"
    )
    profile_disclosure = (
        '<div class="disclosure">Este perfil describe el comportamiento pasado real del manager '
        "(gasto, frecuencia, caja disponible) -- no predice que jugador va a fichar ni cuanto va "
        "a pujar, porque Biwenger no expone ninguna senal sobre la intencion de otro manager."
        "</div>"
    )

    options = []
    panels = []
    for index, user_id in enumerate(user_ids_in_order):
        manager_name = html.escape(names.get(user_id, str(user_id)))
        options.append(f'<option value="{user_id}">{manager_name}</option>')

        squad_player_ids = [row["player_id"] for row in squad_table.get(user_id, [])]
        lineup = analytics.recommend_lineup(squad_player_ids, players, player_form)
        profile = market_profile.get(user_id, _EMPTY_MARKET_PROFILE)

        panel_header = (
            f'<div class="panel-header">{_avatar_img_html(icons.get(user_id))}{manager_name}</div>'
        )
        panel_html = (
            f"{panel_header}"
            "<h3>Alineacion recomendada para la proxima jornada</h3>"
            f"{_lineup_html(lineup)}"
            f"{lineup_disclosure}"
            "<h3>Perfil de mercado</h3>"
            f"{_market_profile_html(profile)}"
            f"{profile_disclosure}"
        )
        active_class = " active" if index == 0 else ""
        panels.append(
            f'<div class="manager-panel{active_class}" data-prefix="jornada" '
            f'id="manager-jornada-{user_id}">{panel_html}</div>'
        )

    select_html = (
        '<select id="managerSelect-jornada" onchange="showManager(\'jornada\', this.value)">'
        f'{"".join(options)}</select>'
    )
    return select_html + "".join(panels)


def _jornadas_tab_html(round_bonus_rows, standings, names, icons):
    if not round_bonus_rows:
        return "<p>Sin jornadas todavia.</p>"

    # Manager columns in league-standings order; defensively append anyone who
    # somehow has a bonus but no standings row.
    user_ids = [s["user_id"] for s in sorted(standings, key=lambda r: r["position"])]
    for row in round_bonus_rows:
        for user_id in row["amounts"]:
            if user_id not in user_ids:
                user_ids.append(user_id)

    header_cells = "".join(
        f'<th class="num">{_avatar_img_html(icons.get(uid), "avatar avatar-sm")}'
        f'{html.escape(names.get(uid, str(uid)))}</th>'
        for uid in user_ids
    )

    totals = defaultdict(int)
    body_rows = []
    for row in round_bonus_rows:
        # Highlight whoever scored the biggest bonus that jornada, so a wide
        # multi-manager table can be scanned at a glance instead of read cell by cell.
        best_amount = max(row["amounts"].values(), default=None)
        cells = []
        for user_id in user_ids:
            amount = row["amounts"].get(user_id)
            if amount is None:
                cells.append('<td class="num">-</td>')
                continue
            totals[user_id] += amount
            is_best = amount > 0 and amount == best_amount
            cell_class = "num cell-best" if is_best else "num"
            cells.append(f'<td class="{cell_class}">{amount:,} EUR</td>')
        body_rows.append(
            f'<tr><td class="jornada-name">{html.escape(row["name"])}</td>{"".join(cells)}</tr>'
        )

    best_total = max(totals.values(), default=0)
    total_cells = []
    for user_id in user_ids:
        total = totals.get(user_id, 0)
        leader_badge = ' <span class="badge">Lider</span>' if total > 0 and total == best_total else ""
        total_cells.append(f'<td class="num"><strong>{total:,} EUR</strong>{leader_badge}</td>')
    total_row = (
        '<tr class="totals-row"><td class="jornada-name"><strong>Total</strong></td>'
        f'{"".join(total_cells)}</tr>'
    )

    # With enough managers the table is wider than the card and needs horizontal
    # scrolling; the scroll-shadow CSS hint alone is too subtle to notice at a
    # glance, so spell it out -- otherwise a table cut off mid-column just looks
    # broken instead of "scroll for more".
    scroll_hint = (
        '<p class="scroll-hint">Desliza la tabla hacia la derecha para ver a todos los managers &rarr;</p>'
        if len(user_ids) > 5 else ""
    )

    return (
        f"{scroll_hint}"
        '<div class="table-wrap"><table class="jornadas-table"><thead><tr>'
        '<th class="jornada-name">Jornada</th>' + header_cells + "</tr></thead>"
        f"<tbody>{''.join(body_rows)}{total_row}</tbody></table></div>"
    )


def build_dashboard_html(conn):
    users = db.get_users(conn)
    names = {u["id"]: u["name"] for u in users}
    icons = {u["id"]: u.get("icon") for u in users}
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

    squads = db.get_all_squads(conn)
    player_form = db.get_player_form(conn)
    squad_table = analytics.compute_squad_table(squads, players)
    market_profile = analytics.compute_market_profile(events, users, current_balances)

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
<button class="tab-btn" id="btn-plantillas" onclick="showTab('plantillas')">Plantillas</button>
<button class="tab-btn" id="btn-jornada" onclick="showTab('jornada')">Proxima jornada</button>
<button class="tab-btn" id="btn-curiosidades" onclick="showTab('curiosidades')">Curiosidades</button>
</div>

<div class="tab-panel active" id="tab-resumen">
<div class="card">
<h2>Clasificacion</h2>
{_standings_table_html(standings, names, icons, current_balances, starting_balance)}
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
{_jornadas_tab_html(round_bonus_rows, standings, names, icons)}
</div>
</div>

<div class="tab-panel" id="tab-movimientos">
<div class="card">
<h2>Movimientos por manager</h2>
{_movements_tab_html(events, names, icons, players, users, rounds_by_id, running_balances)}
</div>
</div>

<div class="tab-panel" id="tab-plantillas">
<div class="card">
<h2>Plantilla por manager</h2>
{_squads_tab_html(squad_table, names, icons, users)}
</div>
</div>

<div class="tab-panel" id="tab-jornada">
<div class="card">
<h2>Recomendaciones para la proxima jornada</h2>
{_next_round_tab_html(users, names, icons, squad_table, players, player_form, market_profile)}
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
