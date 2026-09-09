#!/usr/bin/env bash
# Syncs the league and regenerates the dashboard, opening it when done.
# If config.json doesn't exist (first run, or the token expired), captures
# the session first (opens Chrome and waits for you to log in manually).
set -euo pipefail
cd "$(dirname "$0")"

if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

if [ ! -f config.json ]; then
    echo "config.json not found — capturing Biwenger session..."
    python3 capture_token.py
fi

echo "Syncing league data..."
python3 sync.py

echo "Generating dashboard..."
python3 dashboard.py

if command -v xdg-open >/dev/null 2>&1; then
    xdg-open index.html >/dev/null 2>&1 &
elif command -v open >/dev/null 2>&1; then
    open index.html
else
    echo "Open index.html manually in your browser."
fi
