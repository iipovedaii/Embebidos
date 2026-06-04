#!/usr/bin/env bash
# SISEMB — arranca broker + dashboard en Linux (equivalente a start_stack.ps1)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DASHBOARD_PORT="${1:-8765}"
BROKER_PID=""

cleanup() {
  if [[ -n "${BROKER_PID:-}" ]] && kill -0 "$BROKER_PID" 2>/dev/null; then
    echo ""
    echo "Deteniendo broker (PID $BROKER_PID)..."
    kill "$BROKER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

cd "$ROOT"

PYTHON="$("$ROOT/scripts/ensure-broker-venv.sh")"

echo "Iniciando broker (TCP 5051 | WS 5052)..."
"$PYTHON" broker/simpleBroker/simple_server.py &
BROKER_PID=$!
sleep 2

if ! kill -0 "$BROKER_PID" 2>/dev/null; then
  echo "Error: el broker no arrancó. Revisa puertos 5051/5052 libres."
  exit 1
fi

LAN_IP="$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | grep -v '^172\.' | head -1 || true)"

echo ""
echo "=== SISEMB stack local ==="
echo "Broker:  TCP 5051 | WS 5052"
echo "Dashboard: http://127.0.0.1:${DASHBOARD_PORT}/index.html"
if [[ -n "${LAN_IP:-}" ]]; then
  echo "           http://${LAN_IP}:${DASHBOARD_PORT}/index.html"
  echo ""
  echo "Pon en firmware/config.py: BROKER_HOST = \"${LAN_IP}\""
fi
echo ""
echo "Ctrl+C detiene broker y dashboard."
echo ""

cd "$ROOT/frontend"
exec python3 -m http.server "$DASHBOARD_PORT"
