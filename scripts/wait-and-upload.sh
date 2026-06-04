#!/usr/bin/env bash
# Espera a que aparezca la Pico y sube firmware + umqtt.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-auto}"
MAX_WAIT="${2:-90}"

echo "Esperando dispositivo serie (max ${MAX_WAIT}s)..."
deadline=$((SECONDS + MAX_WAIT))
found=""

while (( SECONDS < deadline )); do
  if [[ "$PORT" != "auto" && -e "$PORT" ]]; then
    found="$PORT"
    break
  fi
  for d in /dev/ttyACM0 /dev/ttyACM1 /dev/serial/by-id/usb*; do
    [[ -e "$d" ]] || continue
    found="$d"
    break 2
  done
  sleep 1
done

if [[ -z "$found" ]]; then
  echo "No se detecto Pico. Comprueba USB (cable datos) y que no este solo en BOOTSEL."
  echo "  ls /dev/ttyACM*"
  exit 1
fi

echo "Detectado: $found"
"$ROOT/scripts/upload-firmware.sh" "$found"
"$ROOT/scripts/upload-umqtt.sh" "$found" 2>/dev/null || true
echo ""
echo "Prueba REPL: mpremote connect $found exec \"import sys; print(sys.implementation._machine)\""
echo "Luego en Cursor: MicroPico > Connect (o vREPL)"
