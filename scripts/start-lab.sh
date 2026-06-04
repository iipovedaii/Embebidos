#!/usr/bin/env bash
# SISEMB laboratorio: broker + instrucciones para red AP de la Pico (WIFI_MODE=ap).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="$("$ROOT/scripts/ensure-broker-venv.sh")"
LOG="/tmp/sisemb-broker.log"
DASHBOARD_PORT="${1:-8765}"

pkill -f "simple_server.py" 2>/dev/null || true
sleep 0.5

echo ""
echo "=== SISEMB lab (Pico en modo AP) ==="
echo ""
echo "1) Sube firmware/config.py a la Pico (upload-firmware.sh o Run en MicroPico)"
echo "2) En la Pico: ejecuta run_sisemb.py (o robot_repl.run_all())"
echo "3) En ESTE PC: conecta Wi-Fi a  SISEMB-G3  clave: SisembG3Lab"
echo "4) Comprueba IP del PC (debe ser 192.168.4.x):"
echo "     ip -4 addr show wlan0"
echo "   Si no es .2, pon esa IP en firmware/config.py -> BROKER_HOST"
echo ""

nohup "$PYTHON" broker/simpleBroker/simple_server.py >>"$LOG" 2>&1 &
BROKER_PID=$!
sleep 1.5

if ! kill -0 "$BROKER_PID" 2>/dev/null; then
  echo "Error: broker no arrancó. Ver $LOG"
  exit 1
fi

echo "Broker PID $BROKER_PID (log: $LOG)"
python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',5051)); print('TCP 5051 OK')" 2>/dev/null || echo "AVISO: puerto 5051 no responde en localhost"

PC_IP=""
for _ in $(seq 1 45); do
  PC_IP="$(ip -4 -o addr show wlan0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | grep '^192\.168\.4\.' | head -1 || true)"
  if [[ -n "${PC_IP:-}" ]]; then
    break
  fi
  sleep 1
done

if [[ -n "${PC_IP:-}" ]]; then
  echo ""
  echo "PC en red Pico: $PC_IP"
  if [[ "$PC_IP" != "192.168.4.2" ]]; then
    echo "Actualiza BROKER_HOST en firmware/config.py a: \"$PC_IP\""
  else
    echo "BROKER_HOST=192.168.4.2 coincide con config.py"
  fi
  echo "Dashboard: http://${PC_IP}:${DASHBOARD_PORT}/index.html"
else
  echo ""
  echo "Aún no hay IP 192.168.4.x en wlan0 — conecta el PC a SISEMB-G3 y vuelve a:"
  echo "  ip -4 addr show wlan0"
  echo "Dashboard local (tras conectar): http://127.0.0.1:${DASHBOARD_PORT}/index.html"
fi

echo ""
echo "Ctrl+C no detiene el broker (nohup). Para parar: pkill -f simple_server.py"
echo ""
