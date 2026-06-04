#!/usr/bin/env bash
# SISEMB — servidor estático del dashboard (http, no file://)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8765}"

cd "$ROOT/frontend"

LAN_IP="$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | grep -v '^172\.' | head -1 || true)"

echo "Dashboard:"
echo "  http://127.0.0.1:${PORT}/index.html"
if [[ -n "${LAN_IP:-}" ]]; then
  echo "  http://${LAN_IP}:${PORT}/index.html"
fi
echo ""
echo "WebSocket broker: ws://127.0.0.1:5052 (misma máquina) o ws://${LAN_IP:-<IP>}:5052"
echo "Ctrl+C para detener."
echo ""

exec python3 -m http.server "$PORT"
