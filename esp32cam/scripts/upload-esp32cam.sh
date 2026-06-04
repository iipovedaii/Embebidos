#!/usr/bin/env bash
# SISEMB — compila y sube firmware ESP32-CAM (PlatformIO)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/.." && pwd)"
CFG="$ROOT/include/config.h"
EXAMPLE="$ROOT/include/config.example.h"

if [[ ! -f "$CFG" ]]; then
  echo "Creando $CFG desde config.example.h — edítalo con Wi-Fi y BROKER_HOST."
  cp "$EXAMPLE" "$CFG"
fi

if ! command -v pio >/dev/null 2>&1; then
  echo "PlatformIO no encontrado. Instala: pip install platformio"
  exit 1
fi

cd "$ROOT"
pio run -t upload "$@"
echo ""
echo "Monitor serial: pio device monitor"
echo "Broker debe estar en $(grep BROKER_HOST include/config.h 2>/dev/null | head -1 || echo 'config.h')"
