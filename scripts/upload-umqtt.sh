#!/usr/bin/env bash
# Sube solo lib/umqtt a la Pico (cierra el REPL antes: el puerto no puede estar en uso).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FW="$ROOT/firmware"
PORT="${1:-/dev/ttyACM0}"
MPREMOTE="$(command -v mpremote)"

if [[ -z "$MPREMOTE" ]]; then
  echo "Instala mpremote: pipx install mpremote"
  exit 1
fi

if fuser "$PORT" 2>/dev/null | grep -q .; then
  echo "Puerto $PORT en uso. Cierra el REPL de Cursor/Thonny y vuelve a ejecutar."
  fuser -v "$PORT" 2>&1 || true
  exit 1
fi

echo "==> Subiendo umqtt a $PORT ..."
"$MPREMOTE" connect "$PORT" fs mkdir :lib 2>/dev/null || true
"$MPREMOTE" connect "$PORT" fs mkdir :lib/umqtt 2>/dev/null || true
"$MPREMOTE" connect "$PORT" fs cp "$FW/lib/umqtt/__init__.py" :lib/umqtt/__init__.py
"$MPREMOTE" connect "$PORT" fs cp "$FW/lib/umqtt/simple.py" :lib/umqtt/simple.py
"$MPREMOTE" connect "$PORT" exec "from umqtt.simple import MQTTClient; print('umqtt OK')"
echo "Listo."
