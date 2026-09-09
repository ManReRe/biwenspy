"""Generate a self-contained HTML dashboard from biwenger.db."""
import html
import json
from collections import defaultdict
from datetime import datetime

import plotly.graph_objects as go
import plotly.io as pio

import analytics
import db

DB_PATH = "biwenger.db"
OUTPUT_PATH = "dashboard.html"

# All user-facing strings, keyed the same in both languages so the client-side
# switcher (see SCRIPT) can look either one up by key. Spanish is the default:
# every _xxx_html() function below renders its literal HTML in Spanish (reading
# straight from TRANSLATIONS["es"]) and tags each translatable node with
# data-i18n (see _i18n_attr) so the switcher can swap it to English in place --
# there's no server/build step to regenerate the page per language.
TRANSLATIONS = {
    "es": {
        "doc_title": "Dashboard Biwenger",
        "h1": "LA SECTA -- Dashboard financiero",
        "subtitle": "Dinero de partida por manager esta temporada: {amount} EUR",
        "tab_resumen": "Resumen",
        "tab_desglose": "Desglose",
        "tab_jornadas": "Jornadas",
        "tab_movimientos": "Movimientos",
        "tab_plantillas": "Plantillas",
        "tab_jornada": "Proxima jornada",
        "tab_curiosidades": "Curiosidades",
        "h_standings": "Clasificacion",
        "h_money_evolution": "Evolucion del dinero",
        "h_points_evolution": "Evolucion de puntos",
        "h_breakdown": "Desglose de ingresos y gastos",
        "h_matchday_money": "Dinero ganado por jornada",
        "h_movements": "Movimientos por manager",
        "h_squads": "Plantilla por manager",
        "h_next_matchday": "Recomendaciones para la proxima jornada",
        "h_facts": "Datos curiosos",
        "th_pos": "Pos.",
        "th_manager": "Manager",
        "th_points": "Puntos",
        "th_money": "Dinero",
        "th_income_points": "Ingresos por puntos",
        "th_income_sales": "Ingresos por ventas",
        "th_expense_signings": "Gastos en fichajes",
        "th_matchday": "Jornada",
        "th_amount": "Importe",
        "th_date": "Fecha",
        "th_movement": "Movimiento",
        "th_balance": "Saldo",
        "th_position": "Posicion",
        "th_player": "Jugador",
        "th_team": "Equipo",
        "th_price_paid": "Precio pagado",
        "th_signed": "Fichado",
        "th_recent_avg": "Media puntos recientes",
        "th_total_earned": "Total ganado por puntos",
        "pos_1": "Portero",
        "pos_2": "Defensa",
        "pos_3": "Centrocampista",
        "pos_4": "Delantero",
        "pos_unknown": "?",
        "empty_managers": "Sin managers todavia.",
        "empty_movements": "Sin movimientos todavia.",
        "empty_players": "Sin jugadores todavia.",
        "empty_matchdays": "Sin jornadas todavia.",
        "empty_data": "Sin datos todavia.",
        "empty_lineup": "No hay suficientes jugadores disponibles en la plantilla para sugerir una alineacion.",
        "badge_leader": "Lider",
        "option_movements_count": "{name} ({n} movimientos)",
        "option_players_count": "{name} ({n} jugadores)",
        "movements_summary": (
            "Ingresos totales: {income} EUR &nbsp;&middot;&nbsp; Gastos totales: {expense} EUR "
            '&nbsp;&middot;&nbsp; Neto por transacciones: <span class="{net_class}">{net}</span>'
        ),
        "disclosure_calibrated": (
            "Comprobacion: el dinero de partida ({amount} EUR) esta calibrado contra el saldo real "
            "de {owner} en Biwenger -- su saldo reconstruido coincide exacto: {balance} EUR. Para el "
            "resto de managers esa misma cifra de partida es la mejor aproximacion disponible, no un "
            "dato verificado: Biwenger no deja consultar el saldo de nadie mas que la cuenta "
            "autenticada, ni registra ningun evento para el reparto de presupuesto en el cambio de "
            "temporada."
        ),
        "disclosure_diff": (
            "Comprobacion (no usada para ajustar ningun calculo): el saldo real de {owner} en "
            "Biwenger es {real} EUR; el saldo reconstruido ({amount} EUR de partida + movimientos "
            "del muro) da {computed} EUR -- una diferencia de {diff} EUR. Biwenger no registra ningun "
            "evento para el reparto de presupuesto en el cambio de temporada, asi que una plantilla "
            "heredada de la temporada anterior puede explicar esta diferencia sin que sea un fallo de "
            "calculo."
        ),
        "lineup_disclosure": (
            "Esto es una sugerencia calculada a partir de la plantilla real y la media de puntos de "
            "las ultimas jornadas jugadas -- Biwenger no publica la alineacion real de otro manager "
            "hasta que la jornada ya ha empezado, asi que esto NO es necesariamente lo que ese "
            "manager vaya a poner."
        ),
        "profile_disclosure": (
            "Este perfil describe el comportamiento pasado real del manager (gasto, frecuencia, caja "
            "disponible) -- no predice que jugador va a fichar ni cuanto va a pujar, porque Biwenger "
            "no expone ninguna senal sobre la intencion de otro manager."
        ),
        "h3_recommended_lineup": "Alineacion recomendada para la proxima jornada",
        "h3_market_profile": "Perfil de mercado",
        "suggested_formation": "<strong>Formacion sugerida:</strong> {formation}",
        "expected_points": "Puntos esperados (suma de medias recientes): {points}",
        "mp_cash": "Caja actual",
        "mp_total_trades": "Operaciones totales",
        "mp_avg_purchase": "Gasto medio por fichaje",
        "mp_avg_sale": "Ingreso medio por venta",
        "mp_recent_trades": "Operaciones en los ultimos 14 dias",
        "h3_season_summary": "Resumen de la temporada",
        "jornadas_total_earned": "Total ganado por puntos: <strong>{amount} EUR</strong>",
        "mv_bonus_named": "Bonus de {round}",
        "mv_bonus_generic": "Bonus de jornada",
        "mv_bought_market_named": "Compra de {player} al mercado",
        "mv_bought_market_generic": "Compra al mercado",
        "mv_sold_to": "Venta a {counterparty}",
        "mv_sold_market": "Venta al mercado",
        "mv_sold_player_to": "Venta de {player} a {counterparty}",
        "mv_sold_player_market": "Venta de {player} al mercado",
        "mv_bought_from": "Compra a {counterparty}",
        "mv_bought_unknown": "Compra a un manager desconocido",
        "mv_bought_player_from": "Compra de {player} a {counterparty}",
        "mv_bought_player_unknown": "Compra de {player} a un manager desconocido",
        "fact_most_expensive_sale": "Venta mas cara",
        "fact_most_expensive_purchase": "Compra mas cara",
        "fact_biggest_round_bonus": "Mayor bonus semanal",
        "fact_most_active_trader": "Manager mas activo en el mercado",
        "fact_best_flip": "Mejor plusvalia",
        "fact_matchday_payout_label": "Jornada con mas dinero repartido:",
        "fact_matchday_payout_value": "{round} ({total} EUR entre todos los managers)",
        "fact_sale_sentence": "{user} vendio a {player} por {amount} EUR",
        "fact_purchase_sentence": "{user} compro a {player} por {amount} EUR",
        "fact_bonus_sentence": "{user} gano {amount} EUR en una sola jornada",
        "fact_active_sentence": "{user} con {n} movimientos de mercado",
        "fact_flip_sentence": (
            "{user} gano {profit} EUR comprando a {player} por {buy} EUR y vendiendolo por {sell} EUR"
        ),
        "chart_balance_title": "Dinero disponible por manager",
        "chart_date_axis": "Fecha",
        "chart_eur_axis": "EUR",
        "chart_points_title": "Puntos acumulados por manager",
        "chart_points_axis": "Puntos",
    },
    "en": {
        "doc_title": "Biwenger Dashboard",
        "h1": "LA SECTA -- Financial Dashboard",
        "subtitle": "Starting money per manager this season: {amount} EUR",
        "tab_resumen": "Summary",
        "tab_desglose": "Breakdown",
        "tab_jornadas": "Matchdays",
        "tab_movimientos": "Movements",
        "tab_plantillas": "Squads",
        "tab_jornada": "Next matchday",
        "tab_curiosidades": "Fun facts",
        "h_standings": "Standings",
        "h_money_evolution": "Money over time",
        "h_points_evolution": "Points over time",
        "h_breakdown": "Income and expenses breakdown",
        "h_matchday_money": "Money earned per matchday",
        "h_movements": "Movements by manager",
        "h_squads": "Squad by manager",
        "h_next_matchday": "Recommendations for the next matchday",
        "h_facts": "Fun facts",
        "th_pos": "Pos.",
        "th_manager": "Manager",
        "th_points": "Points",
        "th_money": "Money",
        "th_income_points": "Income from points",
        "th_income_sales": "Income from sales",
        "th_expense_signings": "Spent on signings",
        "th_matchday": "Matchday",
        "th_amount": "Amount",
        "th_date": "Date",
        "th_movement": "Movement",
        "th_balance": "Balance",
        "th_position": "Position",
        "th_player": "Player",
        "th_team": "Team",
        "th_price_paid": "Price paid",
        "th_signed": "Signed",
        "th_recent_avg": "Recent points average",
        "th_total_earned": "Total earned from points",
        "pos_1": "Goalkeeper",
        "pos_2": "Defender",
        "pos_3": "Midfielder",
        "pos_4": "Forward",
        "pos_unknown": "?",
        "empty_managers": "No managers yet.",
        "empty_movements": "No movements yet.",
        "empty_players": "No players yet.",
        "empty_matchdays": "No matchdays yet.",
        "empty_data": "No data yet.",
        "empty_lineup": "There aren't enough eligible players in the squad to suggest a lineup.",
        "badge_leader": "Leader",
        "option_movements_count": "{name} ({n} movements)",
        "option_players_count": "{name} ({n} players)",
        "movements_summary": (
            "Total income: {income} EUR &nbsp;&middot;&nbsp; Total expenses: {expense} EUR "
            '&nbsp;&middot;&nbsp; Net from transactions: <span class="{net_class}">{net}</span>'
        ),
        "disclosure_calibrated": (
            "Check: the starting money ({amount} EUR) is calibrated against {owner}'s real balance "
            "in Biwenger -- their reconstructed balance matches it exactly: {balance} EUR. For every "
            "other manager that same starting figure is the best available approximation, not a "
            "verified fact: Biwenger won't let you check anyone's balance other than the "
            "authenticated account, and it doesn't log any event for the season-transition budget "
            "reset."
        ),
        "disclosure_diff": (
            "Check (not used to adjust any calculation): {owner}'s real balance in Biwenger is "
            "{real} EUR; the reconstructed balance ({amount} EUR starting + board movements) gives "
            "{computed} EUR -- a difference of {diff} EUR. Biwenger doesn't log any event for the "
            "season-transition budget reset, so a squad carried over from the previous season could "
            "explain this difference without it being a calculation error."
        ),
        "lineup_disclosure": (
            "This is a suggestion calculated from the real squad and the average points from the "
            "last matchdays played -- Biwenger doesn't publish another manager's real lineup until "
            "the matchday has already started, so this is NOT necessarily what that manager will "
            "actually set."
        ),
        "profile_disclosure": (
            "This profile describes the manager's real past behaviour (spending, frequency, cash "
            "available) -- it doesn't predict which player they'll sign or how much they'll bid, "
            "because Biwenger exposes no signal about another manager's intent."
        ),
        "h3_recommended_lineup": "Recommended lineup for the next matchday",
        "h3_market_profile": "Market profile",
        "suggested_formation": "<strong>Suggested formation:</strong> {formation}",
        "expected_points": "Expected points (sum of recent averages): {points}",
        "mp_cash": "Current cash",
        "mp_total_trades": "Total trades",
        "mp_avg_purchase": "Average spend per signing",
        "mp_avg_sale": "Average income per sale",
        "mp_recent_trades": "Trades in the last 14 days",
        "h3_season_summary": "Season summary",
        "jornadas_total_earned": "Total earned from points: <strong>{amount} EUR</strong>",
        "mv_bonus_named": "Bonus from {round}",
        "mv_bonus_generic": "Matchday bonus",
        "mv_bought_market_named": "Bought {player} from the market",
        "mv_bought_market_generic": "Bought from the market",
        "mv_sold_to": "Sold to {counterparty}",
        "mv_sold_market": "Sold to the market",
        "mv_sold_player_to": "Sold {player} to {counterparty}",
        "mv_sold_player_market": "Sold {player} to the market",
        "mv_bought_from": "Bought from {counterparty}",
        "mv_bought_unknown": "Bought from an unknown manager",
        "mv_bought_player_from": "Bought {player} from {counterparty}",
        "mv_bought_player_unknown": "Bought {player} from an unknown manager",
        "fact_most_expensive_sale": "Most expensive sale",
        "fact_most_expensive_purchase": "Most expensive purchase",
        "fact_biggest_round_bonus": "Biggest single-matchday bonus",
        "fact_most_active_trader": "Most active trader",
        "fact_best_flip": "Best profit flip",
        "fact_matchday_payout_label": "Matchday with the most money paid out:",
        "fact_matchday_payout_value": "{round} ({total} EUR across all managers)",
        "fact_sale_sentence": "{user} sold {player} for {amount} EUR",
        "fact_purchase_sentence": "{user} bought {player} for {amount} EUR",
        "fact_bonus_sentence": "{user} earned {amount} EUR in a single matchday",
        "fact_active_sentence": "{user} with {n} market moves",
        "fact_flip_sentence": (
            "{user} made {profit} EUR profit buying {player} for {buy} EUR and selling them for "
            "{sell} EUR"
        ),
        "chart_balance_title": "Available money per manager",
        "chart_date_axis": "Date",
        "chart_eur_axis": "EUR",
        "chart_points_title": "Cumulative points per manager",
        "chart_points_axis": "Points",
    },
}


def _t(key, **args):
    """Render `key` in Spanish (the default language baked into the initial HTML)."""
    text = TRANSLATIONS["es"][key]
    return text.format(**args) if args else text


def _i18n_attr(key, **args):
    """data-i18n(-args) attributes for a translatable node. `args` values must be
    JSON-safe raw strings/numbers, NOT HTML-escaped -- the switcher (see SCRIPT)
    always writes the result via textContent/innerHTML in a controlled way, so
    passing already-escaped text here would double-escape it after a language
    switch."""
    if not args:
        return f'data-i18n="{key}"'
    args_json = html.escape(json.dumps(args), quote=True)
    return f'data-i18n="{key}" data-i18n-args="{args_json}"'


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
.header-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
h1 { font-size: 1.6rem; margin: 0 0 2px; }
.subtitle { color: var(--text-muted); margin: 0 0 20px; font-size: 0.95rem; }
#langSelect { width: auto; min-width: 140px; }
.card {
  background: var(--card-bg); border-radius: 14px; padding: 20px 24px; margin-bottom: 20px;
  border: 1px solid var(--border); box-shadow: 0 1px 2px rgba(0, 0, 0, 0.4);
}
.card h2 { font-size: 1.1rem; margin: 0 0 14px; }
.tabs {
  display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 2px solid var(--border);
  /* Scroll sideways instead of wrapping to several uneven rows -- with 7 tabs, wrapping
     ate a lot of vertical space on a phone-width screen and looked ragged. */
  flex-wrap: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch; scrollbar-width: none;
}
.tabs::-webkit-scrollbar { display: none; }
.tab-btn {
  background: none; border: none; padding: 10px 18px; font-size: 0.95rem; font-weight: 600;
  color: var(--text-muted); cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -2px;
  white-space: nowrap; flex: 0 0 auto;
}
.tab-btn.active { color: var(--primary); border-bottom-color: var(--primary); }
.tab-panel { display: none; }
.tab-panel.active { display: block; }
table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
th { text-align: left; padding: 10px 12px; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--border); white-space: nowrap; }
td {
  padding: 10px 12px; border-bottom: 1px solid var(--border);
  /* Scroll the table sideways (inside .table-wrap) rather than wrapping cell text --
     on a narrow phone screen, wrapping a long description across 3 lines turned a
     short table into a huge, hard-to-scan wall instead of one row per movement. */
  white-space: nowrap;
}
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
.cell-best { background: var(--primary-light); border-radius: 6px; font-weight: 700; }
.avatar {
  width: 28px; height: 28px; border-radius: 50%; object-fit: cover; vertical-align: middle;
  margin-right: 8px; background: var(--border);
}
.panel-header {
  display: flex; align-items: center; gap: 10px; margin-bottom: 14px; font-size: 1.05rem;
  font-weight: 700;
}
.panel-header .avatar { width: 32px; height: 32px; margin-right: 0; }
.player-icons { display: inline-flex; align-items: center; margin-right: 8px; vertical-align: middle; }
.player-icons .crest { width: 16px; height: 16px; margin-right: 4px; object-fit: contain; }
.player-icons .player-photo {
  width: 26px; height: 26px; border-radius: 50%; object-fit: cover; background: var(--border);
}
@media (max-width: 480px) {
  body { padding: 16px 10px; }
  h1 { font-size: 1.3rem; }
  .card { padding: 16px 14px; }
  table { font-size: 0.85rem; }
  th, td { padding: 8px 8px; }
  select { width: 100%; }
}
"""

SCRIPT_TEMPLATE = """
const I18N = __I18N_JSON__;
const CHART_KEYS = {
  "chart-balance": {title: "chart_balance_title", xaxis: "chart_date_axis", yaxis: "chart_eur_axis"},
  "chart-points": {title: "chart_points_title", xaxis: "chart_date_axis", yaxis: "chart_points_axis"},
};

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

function t(lang, key, args) {
  var template = (I18N[lang] && I18N[lang][key]) || key;
  if (args) {
    Object.keys(args).forEach(function(name) {
      template = template.split('{' + name + '}').join(args[name]);
    });
  }
  return template;
}

function applyLanguage(lang) {
  document.querySelectorAll('[data-i18n]').forEach(function(el) {
    var key = el.getAttribute('data-i18n');
    var argsAttr = el.getAttribute('data-i18n-args');
    var args = argsAttr ? JSON.parse(argsAttr) : null;
    var rendered = t(lang, key, args);
    // A handful of templates carry their own inline markup (e.g. "<strong>...</strong>"
    // for emphasis); the rest is plain text, and textContent keeps it safely escaped.
    if (rendered.indexOf('<') === -1) {
      el.textContent = rendered;
    } else {
      el.innerHTML = rendered;
    }
  });
  document.querySelectorAll('option[data-i18n]').forEach(function(el) {
    var key = el.getAttribute('data-i18n');
    var argsAttr = el.getAttribute('data-i18n-args');
    var args = argsAttr ? JSON.parse(argsAttr) : null;
    el.textContent = t(lang, key, args);
  });
  document.documentElement.lang = lang;
  var title = I18N[lang] && I18N[lang].doc_title;
  if (title) { document.title = title; }
  Object.keys(CHART_KEYS).forEach(function(divId) {
    var chartDiv = document.getElementById(divId);
    if (chartDiv && window.Plotly) {
      var keys = CHART_KEYS[divId];
      window.Plotly.relayout(divId, {
        'title.text': t(lang, keys.title),
        'xaxis.title.text': t(lang, keys.xaxis),
        'yaxis.title.text': t(lang, keys.yaxis),
      });
    }
  });
  try { localStorage.setItem('biwenspy_lang', lang); } catch (e) {}
}

(function() {
  var saved = null;
  try { saved = localStorage.getItem('biwenspy_lang'); } catch (e) {}
  if (saved && I18N[saved]) {
    document.getElementById('langSelect').value = saved;
    applyLanguage(saved);
  }
})();
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
        title=_t("chart_balance_title"), xaxis_title=_t("chart_date_axis"), yaxis_title=_t("chart_eur_axis"),
        template="plotly_dark", paper_bgcolor="#151922", plot_bgcolor="#151922",
        font_color="#e8eaed",
        # A vertical legend (Plotly's default) ate most of a phone-width chart, pushing
        # the actual plot into a tiny sliver below it -- lay it out horizontally below
        # the plot instead, wrapping onto more lines on a narrow screen if it must.
        legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5),
        margin=dict(t=50, b=90, l=50, r=20),
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
        title=_t("chart_points_title"), xaxis_title=_t("chart_date_axis"), yaxis_title=_t("chart_points_axis"),
        template="plotly_dark", paper_bgcolor="#151922", plot_bgcolor="#151922",
        font_color="#e8eaed",
        legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5),
        margin=dict(t=50, b=90, l=50, r=20),
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
        '<div class="table-wrap"><table><thead><tr>'
        f'<th {_i18n_attr("th_pos")}>{_t("th_pos")}</th>'
        f'<th {_i18n_attr("th_manager")}>{_t("th_manager")}</th>'
        f'<th {_i18n_attr("th_points")}>{_t("th_points")}</th>'
        f'<th {_i18n_attr("th_money")}>{_t("th_money")}</th>'
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def _real_balance_check_html(names, owner_user_id, owner_real_balance, owner_computed_balance, starting_balance):
    if owner_user_id is None or owner_real_balance is None:
        return ""
    owner_name_raw = names.get(owner_user_id, str(owner_user_id))
    owner_name = html.escape(owner_name_raw)
    diff = owner_computed_balance - owner_real_balance

    if diff == 0:
        args = {"amount": f"{starting_balance:,}", "owner": owner_name_raw, "balance": f"{owner_computed_balance:,}"}
        text = _t("disclosure_calibrated", amount=f"{starting_balance:,}", owner=owner_name, balance=f"{owner_computed_balance:,}")
        return f'<div class="disclosure" {_i18n_attr("disclosure_calibrated", **args)}>{text}</div>'

    args = {
        "owner": owner_name_raw, "real": f"{owner_real_balance:,}", "amount": f"{starting_balance:,}",
        "computed": f"{owner_computed_balance:,}", "diff": f"{diff:,}",
    }
    text = _t(
        "disclosure_diff", owner=owner_name, real=f"{owner_real_balance:,}", amount=f"{starting_balance:,}",
        computed=f"{owner_computed_balance:,}", diff=f"{diff:,}",
    )
    return f'<div class="disclosure" {_i18n_attr("disclosure_diff", **args)}>{text}</div>'


def _format_fact(key, fact):
    if key == "most_expensive_sale":
        args = {"user": fact["user"], "player": fact["player"], "amount": f"{fact['amount']:,}"}
        return _i18n_attr("fact_sale_sentence", **args), _t("fact_sale_sentence", **args)
    if key == "most_expensive_purchase":
        args = {"user": fact["user"], "player": fact["player"], "amount": f"{fact['amount']:,}"}
        return _i18n_attr("fact_purchase_sentence", **args), _t("fact_purchase_sentence", **args)
    if key == "biggest_round_bonus":
        args = {"user": fact["user"], "amount": f"{fact['amount']:,}"}
        return _i18n_attr("fact_bonus_sentence", **args), _t("fact_bonus_sentence", **args)
    if key == "most_active_trader":
        args = {"user": fact["user"], "n": fact["movements"]}
        return _i18n_attr("fact_active_sentence", **args), _t("fact_active_sentence", **args)
    if key == "best_flip":
        args = {
            "user": fact["user"], "player": fact["player"], "profit": f"{fact['profit']:,}",
            "buy": f"{fact['buy_amount']:,}", "sell": f"{fact['sell_amount']:,}",
        }
        return _i18n_attr("fact_flip_sentence", **args), _t("fact_flip_sentence", **args)
    return "", str(fact)


def _facts_html(facts, biggest_bonus_round=None):
    label_keys = {
        "most_expensive_sale": "fact_most_expensive_sale",
        "most_expensive_purchase": "fact_most_expensive_purchase",
        "biggest_round_bonus": "fact_biggest_round_bonus",
        "most_active_trader": "fact_most_active_trader",
        "best_flip": "fact_best_flip",
    }
    items = []
    for key, label_key in label_keys.items():
        if key not in facts:
            continue
        sentence_attr, sentence_text = _format_fact(key, facts[key])
        items.append(
            f'<li><strong {_i18n_attr(label_key)}>{html.escape(_t(label_key))}:</strong> '
            f'<span {sentence_attr}>{html.escape(sentence_text)}</span></li>'
        )
    if biggest_bonus_round is not None:
        value_args = {"round": biggest_bonus_round["round"], "total": f"{biggest_bonus_round['total']:,}"}
        items.append(
            f'<li><strong {_i18n_attr("fact_matchday_payout_label")}>{_t("fact_matchday_payout_label")}</strong> '
            f'<span {_i18n_attr("fact_matchday_payout_value", **value_args)}>'
            f'{html.escape(_t("fact_matchday_payout_value", **value_args))}</span></li>'
        )
    if items:
        return f'<ul class="fact-list">{"".join(items)}</ul>'
    return f'<p {_i18n_attr("empty_data")}>{_t("empty_data")}</p>'


def _breakdown_table_html(breakdown, names, icons):
    rows = []
    for user_id, values in breakdown.items():
        avatar = _avatar_img_html(icons.get(user_id))
        name = html.escape(names.get(user_id, str(user_id)))
        rows.append(
            f"<tr><td>{avatar}{name}</td>"
            f"<td>{values['points']:,} EUR</td><td>{values['sales']:,} EUR</td>"
            f"<td>{values['purchases']:,} EUR</td></tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        f'<th {_i18n_attr("th_manager")}>{_t("th_manager")}</th>'
        f'<th {_i18n_attr("th_income_points")}>{_t("th_income_points")}</th>'
        f'<th {_i18n_attr("th_income_sales")}>{_t("th_income_sales")}</th>'
        f'<th {_i18n_attr("th_expense_signings")}>{_t("th_expense_signings")}</th>'
        "</tr></thead>"
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
        if round_name:
            return "mv_bonus_named", {"round": round_name}
        return "mv_bonus_generic", {}
    if event["type"] == "market":
        if player:
            return "mv_bought_market_named", {"player": player}
        return "mv_bought_market_generic", {}
    if event["type"] == "transfer" and event["direction"] == "income":
        if not player:
            if counterparty:
                return "mv_sold_to", {"counterparty": counterparty}
            return "mv_sold_market", {}
        if counterparty:
            return "mv_sold_player_to", {"player": player, "counterparty": counterparty}
        return "mv_sold_player_market", {"player": player}
    if event["type"] == "transfer" and event["direction"] == "expense":
        if not player:
            if counterparty:
                return "mv_bought_from", {"counterparty": counterparty}
            return "mv_bought_unknown", {}
        if counterparty:
            return "mv_bought_player_from", {"player": player, "counterparty": counterparty}
        return "mv_bought_player_unknown", {"player": player}
    return None, {"text": event["type"]}


def _movement_description_html(event, names, players, rounds_by_id):
    key, args = _movement_description(event, names, players, rounds_by_id)
    if key is None:
        return "", html.escape(args["text"])
    return _i18n_attr(key, **args), html.escape(_t(key, **args))


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
        return f'<p {_i18n_attr("empty_managers")}>{_t("empty_managers")}</p>'

    options = []
    panels = []
    for index, user_id in enumerate(user_ids_in_order):
        user_events = by_user.get(user_id, [])
        manager_name_raw = names.get(user_id, str(user_id))
        manager_name = html.escape(manager_name_raw)
        option_args = {"name": manager_name_raw, "n": len(user_events)}
        options.append(
            f'<option value="{user_id}" {_i18n_attr("option_movements_count", **option_args)}>'
            f'{html.escape(_t("option_movements_count", **option_args))}</option>'
        )
        panel_header = (
            f'<div class="panel-header">{_avatar_img_html(icons.get(user_id))}{manager_name}</div>'
        )

        total_income = sum(e["amount"] for e in user_events if e["direction"] == "income")
        total_expense = sum(e["amount"] for e in user_events if e["direction"] == "expense")
        net = total_income - total_expense
        net_class = "amount-income" if net >= 0 else "amount-expense"
        net_sign = "+" if net >= 0 else ""
        summary_args = {
            "income": f"{total_income:,}", "expense": f"{total_expense:,}",
            "net_class": net_class, "net": f"{net_sign}{net:,} EUR",
        }
        summary = f'<p class="movements-summary" {_i18n_attr("movements_summary", **summary_args)}>{_t("movements_summary", **summary_args)}</p>'

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
            desc_attr, desc_text = _movement_description_html(event, names, players, rounds_by_id)
            balance_after = running_balances.get(event["id"])
            balance_cell = f"{balance_after:,} EUR" if balance_after is not None else "-"
            rows.append(
                f"<tr><td>{_format_date(event['date'])}</td>"
                f'<td>{icons_html}<span {desc_attr}>{desc_text}</span></td>'
                f'<td class="{css_class}">{sign}{event["amount"]:,} EUR</td>'
                f'<td class="amount-balance">{balance_cell}</td></tr>'
            )
        empty_row = f'<tr><td colspan="4" {_i18n_attr("empty_movements")}>{_t("empty_movements")}</td></tr>'
        rows_html = "".join(rows) if rows else empty_row
        table = (
            '<div class="table-wrap"><table><thead><tr>'
            f'<th {_i18n_attr("th_date")}>{_t("th_date")}</th>'
            f'<th {_i18n_attr("th_movement")}>{_t("th_movement")}</th>'
            f'<th {_i18n_attr("th_amount")}>{_t("th_amount")}</th>'
            f'<th {_i18n_attr("th_balance")}>{_t("th_balance")}</th>'
            "</tr></thead>"
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


POSITION_LABEL_KEYS = {1: "pos_1", 2: "pos_2", 3: "pos_3", 4: "pos_4"}


def _position_label_html(position):
    key = POSITION_LABEL_KEYS.get(position, "pos_unknown")
    return f'<span {_i18n_attr(key)}>{_t(key)}</span>'


def _squads_tab_html(squad_table, names, icons, users):
    user_ids_in_order = [u["id"] for u in users]
    for user_id in squad_table:
        if user_id not in user_ids_in_order:
            user_ids_in_order.append(user_id)

    if not user_ids_in_order:
        return f'<p {_i18n_attr("empty_managers")}>{_t("empty_managers")}</p>'

    options = []
    panels = []
    for index, user_id in enumerate(user_ids_in_order):
        rows = squad_table.get(user_id, [])
        manager_name_raw = names.get(user_id, str(user_id))
        manager_name = html.escape(manager_name_raw)
        option_args = {"name": manager_name_raw, "n": len(rows)}
        options.append(
            f'<option value="{user_id}" {_i18n_attr("option_players_count", **option_args)}>'
            f'{html.escape(_t("option_players_count", **option_args))}</option>'
        )
        panel_header = (
            f'<div class="panel-header">{_avatar_img_html(icons.get(user_id))}{manager_name}</div>'
        )

        row_html = []
        for player in rows:
            price = f"{player['price_paid']:,} EUR" if player["price_paid"] is not None else "-"
            acquired = _format_date(player["acquired_date"]) if player["acquired_date"] else "-"
            icons_html = _player_icons_html(player["player_id"], player.get("team_id"))
            row_html.append(
                f"<tr><td>{_position_label_html(player['position'])}</td>"
                f"<td>{icons_html}{html.escape(player['name'])}</td>"
                f"<td>{html.escape(player['team'] or '-')}</td>"
                f"<td>{price}</td><td>{acquired}</td></tr>"
            )
        empty_row = f'<tr><td colspan="5" {_i18n_attr("empty_players")}>{_t("empty_players")}</td></tr>'
        rows_html = "".join(row_html) if row_html else empty_row
        table = (
            '<div class="table-wrap"><table><thead><tr>'
            f'<th {_i18n_attr("th_position")}>{_t("th_position")}</th>'
            f'<th {_i18n_attr("th_player")}>{_t("th_player")}</th>'
            f'<th {_i18n_attr("th_team")}>{_t("th_team")}</th>'
            f'<th {_i18n_attr("th_price_paid")}>{_t("th_price_paid")}</th>'
            f'<th {_i18n_attr("th_signed")}>{_t("th_signed")}</th>'
            "</tr></thead>"
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


def _lineup_rows_html(lineup, players):
    captain_id = lineup["captain"]["player_id"]
    rows = []
    for player in lineup["starters"]:
        captain_badge = ' <span class="badge">C</span>' if player["player_id"] == captain_id else ""
        team_id = players.get(player["player_id"], {}).get("team_id")
        icons_html = _player_icons_html(player["player_id"], team_id)
        name_cell = icons_html + html.escape(player["name"]) + captain_badge
        rows.append(
            f"<tr><td>{_position_label_html(player['position'])}</td><td>{name_cell}</td>"
            f"<td>{player['avg_points']:.1f}</td></tr>"
        )
    return "".join(rows)


def _lineup_html(lineup, players):
    if lineup is None:
        return f'<p {_i18n_attr("empty_lineup")}>{_t("empty_lineup")}</p>'
    rows_html = _lineup_rows_html(lineup, players)
    formation_args = {"formation": lineup["formation"]}
    points_args = {"points": f'{lineup["total_points"]:.1f}'}
    return (
        f'<p><span {_i18n_attr("suggested_formation", **formation_args)}>'
        f'{_t("suggested_formation", **formation_args)}</span> &nbsp;&middot;&nbsp; '
        f'<span {_i18n_attr("expected_points", **points_args)}>{_t("expected_points", **points_args)}</span></p>'
        '<div class="table-wrap"><table><thead><tr>'
        f'<th {_i18n_attr("th_position")}>{_t("th_position")}</th>'
        f'<th {_i18n_attr("th_player")}>{_t("th_player")}</th>'
        f'<th {_i18n_attr("th_recent_avg")}>{_t("th_recent_avg")}</th>'
        "</tr></thead>"
        f"<tbody>{rows_html}</tbody></table></div>"
    )


def _market_profile_html(profile):
    rows = [
        ("mp_cash", f"{profile['cash']:,} EUR"),
        ("mp_total_trades", str(profile["total_trades"])),
        ("mp_avg_purchase", f"{profile['avg_purchase']:,} EUR"),
        ("mp_avg_sale", f"{profile['avg_sale']:,} EUR"),
        ("mp_recent_trades", str(profile["recent_trades"])),
    ]
    body = "".join(f'<tr><td {_i18n_attr(key)}>{_t(key)}</td><td>{value}</td></tr>' for key, value in rows)
    return f'<div class="table-wrap"><table><tbody>{body}</tbody></table></div>'


_EMPTY_MARKET_PROFILE = {"cash": 0, "total_trades": 0, "avg_purchase": 0, "avg_sale": 0, "recent_trades": 0}


def _next_round_tab_html(users, names, icons, squad_table, players, player_form, market_profile):
    user_ids_in_order = [u["id"] for u in users]
    for user_id in squad_table:
        if user_id not in user_ids_in_order:
            user_ids_in_order.append(user_id)

    if not user_ids_in_order:
        return f'<p {_i18n_attr("empty_managers")}>{_t("empty_managers")}</p>'

    lineup_disclosure = f'<div class="disclosure" {_i18n_attr("lineup_disclosure")}>{_t("lineup_disclosure")}</div>'
    profile_disclosure = f'<div class="disclosure" {_i18n_attr("profile_disclosure")}>{_t("profile_disclosure")}</div>'

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
            f'<h3 {_i18n_attr("h3_recommended_lineup")}>{_t("h3_recommended_lineup")}</h3>'
            f"{_lineup_html(lineup, players)}"
            f"{lineup_disclosure}"
            f'<h3 {_i18n_attr("h3_market_profile")}>{_t("h3_market_profile")}</h3>'
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
        return f'<p {_i18n_attr("empty_matchdays")}>{_t("empty_matchdays")}</p>'

    # Managers in league-standings order; defensively append anyone who somehow
    # has a bonus but no standings row.
    user_ids_in_order = [s["user_id"] for s in sorted(standings, key=lambda r: r["position"])]
    for row in round_bonus_rows:
        for user_id in row["amounts"]:
            if user_id not in user_ids_in_order:
                user_ids_in_order.append(user_id)

    totals = defaultdict(int)
    for row in round_bonus_rows:
        for user_id, amount in row["amounts"].items():
            totals[user_id] += amount

    options = []
    panels = []
    for index, user_id in enumerate(user_ids_in_order):
        manager_name = html.escape(names.get(user_id, str(user_id)))
        options.append(f'<option value="{user_id}">{manager_name}</option>')
        panel_header = (
            f'<div class="panel-header">{_avatar_img_html(icons.get(user_id))}{manager_name}</div>'
        )

        manager_amounts = [(row["name"], row["amounts"].get(user_id)) for row in round_bonus_rows]
        # Highlight this manager's own best jornada, so it's obvious at a glance
        # without needing to compare against every other manager's column.
        best_amount = max((a for _, a in manager_amounts if a is not None), default=None)

        row_html = []
        for round_name, amount in manager_amounts:
            if amount is None:
                row_html.append(f'<tr><td>{html.escape(round_name)}</td><td class="num">-</td></tr>')
                continue
            is_best = best_amount is not None and amount > 0 and amount == best_amount
            cell_class = "num cell-best" if is_best else "num"
            row_html.append(
                f'<tr><td>{html.escape(round_name)}</td><td class="{cell_class}">{amount:,} EUR</td></tr>'
            )
        empty_row = f'<tr><td colspan="2" {_i18n_attr("empty_matchdays")}>{_t("empty_matchdays")}</td></tr>'
        rows_html = "".join(row_html) if row_html else empty_row

        earned_args = {"amount": f"{totals.get(user_id, 0):,}"}
        summary = (
            f'<p class="movements-summary" {_i18n_attr("jornadas_total_earned", **earned_args)}>'
            f'{_t("jornadas_total_earned", **earned_args)}</p>'
        )
        table = (
            '<div class="table-wrap"><table><thead><tr>'
            f'<th {_i18n_attr("th_matchday")}>{_t("th_matchday")}</th>'
            f'<th class="num" {_i18n_attr("th_amount")}>{_t("th_amount")}</th>'
            "</tr></thead>"
            f"<tbody>{rows_html}</tbody></table></div>"
        )
        active_class = " active" if index == 0 else ""
        panels.append(
            f'<div class="manager-panel{active_class}" data-prefix="jornadas" '
            f'id="manager-jornadas-{user_id}">{panel_header}{summary}{table}</div>'
        )

    select_html = (
        '<select id="managerSelect-jornadas" onchange="showManager(\'jornadas\', this.value)">'
        f'{"".join(options)}</select>'
    )

    # Season-wide summary at the end: one row per manager, so the at-a-glance
    # comparison a wide matrix used to give is still available without needing to
    # flip through every manager one by one.
    best_total = max(totals.values(), default=0)
    summary_rows = []
    for user_id in sorted(user_ids_in_order, key=lambda uid: totals.get(uid, 0), reverse=True):
        total = totals.get(user_id, 0)
        avatar = _avatar_img_html(icons.get(user_id))
        name = html.escape(names.get(user_id, str(user_id)))
        leader_badge = (
            f' <span class="badge" {_i18n_attr("badge_leader")}>{_t("badge_leader")}</span>'
            if total > 0 and total == best_total else ""
        )
        summary_rows.append(
            f"<tr><td>{avatar}{name}</td>"
            f'<td class="num"><strong>{total:,} EUR</strong>{leader_badge}</td></tr>'
        )
    summary_html = (
        f'<h3 {_i18n_attr("h3_season_summary")}>{_t("h3_season_summary")}</h3>'
        '<div class="table-wrap"><table><thead><tr>'
        f'<th {_i18n_attr("th_manager")}>{_t("th_manager")}</th>'
        f'<th class="num" {_i18n_attr("th_total_earned")}>{_t("th_total_earned")}</th>'
        "</tr></thead>"
        f"<tbody>{''.join(summary_rows)}</tbody></table></div>"
    )

    return select_html + "".join(panels) + summary_html


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

    # responsive=True makes Plotly re-fit the chart to its container on resize/rotation
    # (e.g. a phone switching between portrait and landscape) instead of staying at
    # whatever size it first rendered at. Fixed div_id lets the language switcher call
    # Plotly.relayout() on it later to translate the title/axis labels in place.
    plot_config = {"responsive": True}
    balance_fig_html = pio.to_html(
        _balance_chart(balance_timelines, names), full_html=False, include_plotlyjs=True,
        config=plot_config, div_id="chart-balance",
    )
    points_fig_html = pio.to_html(
        _points_chart(points_timelines, names), full_html=False, include_plotlyjs=False,
        config=plot_config, div_id="chart-points",
    )

    owner_computed_balance = current_balances.get(owner_user_id, starting_balance)
    script = SCRIPT_TEMPLATE.replace("__I18N_JSON__", json.dumps(TRANSLATIONS, ensure_ascii=False))
    subtitle_args = {"amount": f"{starting_balance:,}"}

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title {_i18n_attr("doc_title")}>{_t("doc_title")}</title>
<style>{STYLE}</style>
</head>
<body>
<div class="container">
<div class="header-row">
<div>
<h1 {_i18n_attr("h1")}>{_t("h1")}</h1>
<p class="subtitle" {_i18n_attr("subtitle", **subtitle_args)}>{_t("subtitle", **subtitle_args)}</p>
</div>
<select id="langSelect" onchange="applyLanguage(this.value)">
<option value="es">Espanol</option>
<option value="en">English</option>
</select>
</div>

<div class="tabs">
<button class="tab-btn active" id="btn-resumen" onclick="showTab('resumen')" {_i18n_attr("tab_resumen")}>{_t("tab_resumen")}</button>
<button class="tab-btn" id="btn-desglose" onclick="showTab('desglose')" {_i18n_attr("tab_desglose")}>{_t("tab_desglose")}</button>
<button class="tab-btn" id="btn-jornadas" onclick="showTab('jornadas')" {_i18n_attr("tab_jornadas")}>{_t("tab_jornadas")}</button>
<button class="tab-btn" id="btn-movimientos" onclick="showTab('movimientos')" {_i18n_attr("tab_movimientos")}>{_t("tab_movimientos")}</button>
<button class="tab-btn" id="btn-plantillas" onclick="showTab('plantillas')" {_i18n_attr("tab_plantillas")}>{_t("tab_plantillas")}</button>
<button class="tab-btn" id="btn-jornada" onclick="showTab('jornada')" {_i18n_attr("tab_jornada")}>{_t("tab_jornada")}</button>
<button class="tab-btn" id="btn-curiosidades" onclick="showTab('curiosidades')" {_i18n_attr("tab_curiosidades")}>{_t("tab_curiosidades")}</button>
</div>

<div class="tab-panel active" id="tab-resumen">
<div class="card">
<h2 {_i18n_attr("h_standings")}>{_t("h_standings")}</h2>
{_standings_table_html(standings, names, icons, current_balances, starting_balance)}
{_real_balance_check_html(names, owner_user_id, owner_real_balance, owner_computed_balance, starting_balance)}
</div>
<div class="card">
<h2 {_i18n_attr("h_money_evolution")}>{_t("h_money_evolution")}</h2>
{balance_fig_html}
</div>
<div class="card">
<h2 {_i18n_attr("h_points_evolution")}>{_t("h_points_evolution")}</h2>
{points_fig_html}
</div>
</div>

<div class="tab-panel" id="tab-desglose">
<div class="card">
<h2 {_i18n_attr("h_breakdown")}>{_t("h_breakdown")}</h2>
{_breakdown_table_html(breakdown, names, icons)}
</div>
</div>

<div class="tab-panel" id="tab-jornadas">
<div class="card">
<h2 {_i18n_attr("h_matchday_money")}>{_t("h_matchday_money")}</h2>
{_jornadas_tab_html(round_bonus_rows, standings, names, icons)}
</div>
</div>

<div class="tab-panel" id="tab-movimientos">
<div class="card">
<h2 {_i18n_attr("h_movements")}>{_t("h_movements")}</h2>
{_movements_tab_html(events, names, icons, players, users, rounds_by_id, running_balances)}
</div>
</div>

<div class="tab-panel" id="tab-plantillas">
<div class="card">
<h2 {_i18n_attr("h_squads")}>{_t("h_squads")}</h2>
{_squads_tab_html(squad_table, names, icons, users)}
</div>
</div>

<div class="tab-panel" id="tab-jornada">
<div class="card">
<h2 {_i18n_attr("h_next_matchday")}>{_t("h_next_matchday")}</h2>
{_next_round_tab_html(users, names, icons, squad_table, players, player_form, market_profile)}
</div>
</div>

<div class="tab-panel" id="tab-curiosidades">
<div class="card">
<h2 {_i18n_attr("h_facts")}>{_t("h_facts")}</h2>
{_facts_html(facts, biggest_bonus_round)}
</div>
</div>

</div>
<script>{script}</script>
</body>
</html>"""


def main():
    conn = db.init_db(DB_PATH)
    output = build_dashboard_html(conn)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as output_file:
        output_file.write(output)
    print(f"Dashboard generated at {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
