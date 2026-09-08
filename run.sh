#!/usr/bin/env bash
# Sincroniza la liga y regenera el dashboard, abriéndolo al terminar.
# Si no existe config.json (primera vez, o el token caducó), captura la
# sesión primero (abre Chrome y espera a que inicies sesión manualmente).
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f config.json ]; then
    echo "No se encontró config.json — capturando sesión de Biwenger..."
    python3 capture_token.py
fi

echo "Sincronizando datos de la liga..."
python3 sync.py

echo "Generando dashboard..."
python3 dashboard.py

if command -v xdg-open >/dev/null 2>&1; then
    xdg-open dashboard.html >/dev/null 2>&1 &
elif command -v open >/dev/null 2>&1; then
    open dashboard.html
else
    echo "Abre dashboard.html manualmente en tu navegador."
fi
