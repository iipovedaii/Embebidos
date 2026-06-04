#!/usr/bin/env bash
# Conecta el PC a la red AP de la Pico (WIFI_AP_SSID en config.py).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSID="SISEMB-G3"
PASS="SisembG3Lab"
IFACE="wlan0"

if [[ -f "$ROOT/firmware/config.py" ]]; then
  SSID="$(python3 -c "import importlib.util; s=importlib.util.spec_from_file_location('c','$ROOT/firmware/config.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(getattr(m,'WIFI_AP_SSID', 'SISEMB-G3'))")"
  PASS="$(python3 -c "import importlib.util; s=importlib.util.spec_from_file_location('c','$ROOT/firmware/config.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(getattr(m,'WIFI_AP_PASS', 'SisembG3Lab'))")"
fi

if ! command -v iwctl >/dev/null 2>&1; then
  echo "iwctl no encontrado. Conecta manualmente a Wi-Fi: $SSID"
  exit 1
fi

echo "Conectando $IFACE -> $SSID ..."
iwctl --passphrase "$PASS" station "$IFACE" connect "$SSID" --dont-ask

sleep 2
ip -4 addr show "$IFACE" | grep -E 'inet |^[0-9]:' || true
PC_IP="$(ip -4 -o addr show "$IFACE" 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | grep '^192\.168\.4\.' | head -1 || true)"
if [[ -n "${PC_IP:-}" ]]; then
  echo "IP PC: $PC_IP — BROKER_HOST en config.py debe ser esta IP."
  if [[ -f "$ROOT/firmware/config.py" ]]; then
    python3 - "$ROOT/firmware/config.py" "$PC_IP" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
ip = sys.argv[2]
text = path.read_text()
new_text = re.sub(r'BROKER_HOST = "[^"]+"', f'BROKER_HOST = "{ip}"', text, count=1)
if new_text != text:
    path.write_text(new_text)
    print(f"Actualizado firmware/config.py -> BROKER_HOST = {ip}")
PY
  fi
else
  echo "Sin IP 192.168.4.x. ¿La Pico ya ejecutó run_sisemb (modo AP)?"
fi
