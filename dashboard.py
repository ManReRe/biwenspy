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
