#!/usr/bin/env bash
# One-command start for macOS / Linux:   ./start.sh
set -e
cd "$(dirname "$0")"

PY=$(command -v python3 || command -v python || true)
if [ -z "$PY" ]; then
  echo "Python 3.10+ is required. Get it from https://www.python.org/downloads/"; exit 1
fi
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || {
  echo "Python 3.10 or newer is required (you have $("$PY" --version))."; exit 1; }

if [ ! -d .venv ]; then
  echo "First run: setting up (about a minute)..."
  "$PY" -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
fi

if [ -f .env ]; then echo "Using keys from .env in this folder."
elif [ -f ../.env ]; then echo "Using keys from ../.env (the folder above this repo)."
else echo "No .env found here or one folder up: demo mode (offline AI). Add PORTKEY_API_KEY or OPENAI_API_KEY for live AI."; fi
PORT=${PORT:-8000}
echo ""
echo "  Yale Jeopardy is running:  http://localhost:$PORT"
echo "  Press Ctrl+C to stop."
echo ""
( sleep 2; (open "http://localhost:$PORT" || xdg-open "http://localhost:$PORT") >/dev/null 2>&1 ) &
HOST=${HOST:-127.0.0.1}
if [ "$HOST" = "0.0.0.0" ]; then
  IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}')
  echo "  Phones on the same Wi-Fi: open  http://$IP:$PORT  (open the teacher screen with that address too)"
  echo ""
fi
exec .venv/bin/python -m uvicorn app.server:app --host "$HOST" --port "$PORT"
