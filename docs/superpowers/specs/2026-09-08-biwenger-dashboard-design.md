# Dashboard financiero de liga Biwenger — Diseño

Fecha: 2026-09-08

## Contexto

El usuario juega en una liga privada de Biwenger ("LA SECTA 🛐🐶", id `1967092`, 7 managers) que
empezó con 20.000.000 € para cada participante. Quiere un dashboard que muestre, por manager:
los movimientos de mercado (compras/ventas) desde el inicio de la liga, la posición actual en la
clasificación, y el dinero disponible — reconstruido a lo largo del tiempo, no solo el valor actual.

## Fuente de datos: API interna de Biwenger

Biwenger no expone una API pública documentada, pero su propia web usa una API JSON en
`https://biwenger.as.com/api/v2/` autenticada con un JWT (`Bearer` token) más las cabeceras
`X-League`, `X-User`, `X-Lang`, `X-Version`. Se confirmó funcionando contra la liga real del
usuario:

- `GET /league/{leagueId}` — info básica y lista de usuarios de la liga.
- `GET /league/{leagueId}?fields=standings` — clasificación (id, nombre, puntos, posición).
- `GET /league/{leagueId}/board?limit=500&offset=N` — muro de actividad, paginado (máx. 500 por
  página, orden descendente por fecha). Devuelve ~537 eventos para esta liga, desde su creación.
- `GET /competitions/la-liga/data?lang=es&score=5` — base de datos de jugadores (nombre, equipo)
  para resolver los IDs de jugador que aparecen en el muro.

Importante: el ajuste de privacidad de esta liga (`settings.balance = "hidden"`) oculta el saldo
actual de los demás managers vía API. Por eso el dashboard **no** pide el balance directamente:
lo reconstruye sumando 20.000.000 € iniciales + todos los movimientos de dinero de cada manager
que sí aparecen en el muro (público para todos los miembros de la liga).

### Tipos de evento relevantes del muro

- `roundFinished`: por jornada, cada manager recibe `content.results[].bonus` (dinero ganado por
  puntos) con desglose en `reason` (bonusPoint, bonusFixed, bonusIdealLineup, bonusGameMVP,
  bonusRoundMVP, ...). → ingreso.
- `transfer`: `content[]` con `player`, `from` (siempre), `to` (opcional), `amount`.
  - Solo `from` → venta al mercado (el manager `from` cobra `amount`). → ingreso para `from`.
  - `from` + `to` → traspaso directo entre managers. `from` cobra, `to` paga `amount`. → ingreso
    para `from`, gasto para `to`.
- `market`: `content[]` con `player`, `to`, `amount` → compra al mercado, el manager `to` paga
  `amount`. → gasto para `to`.
- Se ignoran para el cálculo de dinero (pero pueden guardarse para contexto): `playerMovements`
  (altas/bajas de jugadores en equipos reales), `text`, `adminText`, `roundStarted`,
  `bettingPool`, `leagueSettings`.

## Autenticación

El token se captura una sola vez con un script Playwright (`capture_token.py`) que abre un Chrome
real, deja que el usuario inicie sesión manualmente (para no manejar sus credenciales), y lee
`localStorage.satellizer_token` junto con el id de liga y el id de usuario de
`localStorage.lastSession`. Se guarda en `config.json` (excluido de git vía `.gitignore`).

El JWT no muestra expiración corta visible; si una llamada devuelve 401, `sync.py` lo notifica
claramente pidiendo re-ejecutar `capture_token.py`.

## Componentes

1. **`capture_token.py`** — Playwright, un solo uso (o re-uso si el token caduca). Escribe
   `config.json`: `{token, leagueId, userId}`.
2. **`sync.py`** — Lee `config.json`, pagina `/league/{id}/board` hacia atrás (offset creciente)
   hasta agotar el histórico o llegar a eventos ya guardados (sync incremental por fecha/id
   sintético del evento). Normaliza cada evento en movimientos de dinero individuales y los
   guarda en SQLite (`biwenger.db`). También sincroniza el diccionario de jugadores (una vez, o
   si faltan IDs nuevos) y la clasificación actual.
3. **`dashboard.py`** — Lee `biwenger.db` y genera `dashboard.html` autocontenido (Plotly
   embebido) con las vistas descritas abajo. No requiere servidor, se abre directamente en el
   navegador.

## Modelo de datos (SQLite)

- `users(id, name, icon)`
- `players(id, name, team)`
- `rounds(id, name, date)`
- `money_events(id TEXT PK, date, round_id, type, user_id, counterparty_id, player_id, amount,
  direction, reason_json)` — `direction` es `income`/`expense`; `id` es un hash estable de
  (fecha, tipo, índice dentro del evento del muro) para que `sync.py` sea idempotente.
- `sync_state(key, value)` — guarda el último offset/fecha sincronizado.

## Dashboard: contenido

**Por manager:**
- Línea temporal de dinero disponible (partiendo de 20.000.000 €).
- Línea temporal de puntos y posición.
- Tabla de movimientos (jugador, fecha, tipo, contrapartida, importe).
- Desglose de ingresos (puntos vs. ventas) y gastos (fichajes).

**Vista de liga:**
- Clasificación actual (puntos, posición, dinero reconstruido).
- Gráfica combinada con las 7 líneas de dinero.
- Datos curiosos: venta más cara, compra más cara, mayor plusvalía en un mismo jugador (comprado
  y vendido por el mismo manager), bonus semanal más alto y su motivo, manager más activo en
  mercado, jornada con más dinero repartido en bonus.

## Errores y actualización

- 401 en cualquier llamada → mensaje claro pidiendo recapturar el token.
- `sync.py` es incremental e idempotente (reejecutar no duplica datos).
- Ejecución manual: `python sync.py && python dashboard.py`. Automatización (cron) queda fuera de
  este alcance, se puede añadir después si se quiere.

## Testing

- Tests unitarios del parseo de eventos del muro → movimientos de dinero, usando los ejemplos
  reales capturados durante el diseño (roundFinished, transfer con/sin `to`, market).
- Verificación manual: el balance reconstruido del propio usuario debe coincidir con el balance
  real visible en su sesión (dato de control: 38.470.000 € en el momento del diseño) menos/más
  cualquier movimiento posterior a esa fecha.

## Fuera de alcance

- Scraping visual del DOM (se descartó a favor de la API interna, más fiable).
- Automatización programada (cron) del sync — se puede añadir en una iteración futura.
- Multi-liga / multi-usuario — el diseño asume una sola liga y un solo `config.json` local.
