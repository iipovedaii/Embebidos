#!/usr/bin/env bash
# SISEMB — levanta simpleBroker (TCP 5051 + WS 5052) en el portátil
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="$("$ROOT/scripts/ensure-broker-venv.sh")"

echo ""
echo "Broker simpleBroker:"
echo "  TCP 5051  → Pico 2W (firmware)"
echo "  WS  5052  → dashboard (frontend)"
echo ""

LAN_IP="$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | grep -v '^172\.' | head -1 || true)"
if [[ -n "${LAN_IP:-}" ]]; then
  echo "IP LAN detectada: $LAN_IP"
  echo "Pon en firmware/config.py: BROKER_HOST = \"$LAN_IP\""
else
  echo "No se detectó IP LAN; usa: ip -4 addr show scope global"
fi
echo ""
echo "Ctrl+C para detener."
echo ""

exec "$PYTHON" broker/simpleBroker/simple_server.py
