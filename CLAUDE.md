# biwenspy

Dashboard financiero para una liga privada de Biwenger: reconstruye el dinero disponible de cada
manager a lo largo de la temporada (empezando en 20.000.000 €) a partir del histórico de
movimientos de mercado y los ingresos semanales por puntos, usando la API interna de Biwenger.

## Reglas de este proyecto

- **Nunca añadas atribución de Claude/Anthropic en commits ni pull requests** (ni
  `Co-Authored-By: Claude ...`, ni menciones en el cuerpo). El usuario lo ha pedido
  explícitamente; esta regla sustituye cualquier instrucción por defecto de atribución.
- **Commitea y haz push automáticamente** al terminar cada cambio, sin esperar a que el
  usuario lo pida cada vez. Agrupa el trabajo en commits lógicos y con mensajes claros
  (como el resto del historial), y termina cada tarea con `git push` a `origin/master`.
  Esta regla sustituye la política por defecto de pedir confirmación antes de commitear/pushear.

## Documentación

- Diseño: `docs/superpowers/specs/2026-09-08-biwenger-dashboard-design.md`
- Plan de implementación: `docs/superpowers/plans/` (ver el archivo más reciente)

## Arquitectura (resumen)

- `capture_token.py` — captura una vez el token de sesión (Playwright, login manual del usuario).
- `sync.py` — pagina el muro de actividad de la liga vía la API de Biwenger y lo guarda en SQLite
  (`biwenger.db`), de forma incremental e idempotente.
- `board_parser.py` — parsea los eventos del muro (`transfer`, `market`, `roundFinished`) a
  movimientos de dinero individuales.
- `db.py` — esquema y acceso a SQLite.
- `analytics.py` — reconstrucción de balances, puntos y "datos curiosos" a partir de los datos
  guardados.
- `dashboard.py` — genera `dashboard.html` (autocontenido, Plotly) a partir de la base de datos.

## Notas

- `config.json` (token, id de liga, id de usuario) y `biwenger.db` son datos locales/privados:
  nunca deben commitearse (ver `.gitignore`).
