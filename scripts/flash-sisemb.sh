#!/usr/bin/env bash
# Limpia la Pico por completo y sube el firmware SISEMB.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FW="$ROOT/firmware"
SCRIPTS="$ROOT/scripts"
MPREMOTE="${MPREMOTE:-$HOME/.local/bin/mpremote}"
PORT="${1:-/dev/ttyACM0}"

if [[ ! -f "$FW/config.py" ]]; then
  echo "Falta firmware/config.py — copia config.example.py y edita Wi-Fi."
  exit 1
fi

if ! command -v "$MPREMOTE" &>/dev/null && [[ ! -x "$MPREMOTE" ]]; then
  echo "Instala mpremote: pipx install mpremote"
  exit 1
fi
MPREMOTE="$(command -v mpremote 2>/dev/null || echo "$MPREMOTE")"

echo "==> Liberando puerto $PORT (cierra el REPL de MicroPico si falla)..."
fuser -k "$PORT" 2>/dev/null || true
sleep 1.5

echo "==> Borrando filesystem de la Pico..."
"$MPREMOTE" connect "$PORT" run "$SCRIPTS/pico_wipe.py"

echo "==> Subiendo firmware SISEMB..."
for f in boot.py config.py robot_ctl.py robot_repl.py run_sisemb.py wifi_manager.py repl_test_wifi_mqtt.py repl_test_camera.py diag_camera.py telemetry.py main.py sisemb_loop.py runtime_simplebroker.py hardware_pins.py ov7670_registers.py ov7670_pio.py \
  battery.py hcsr04.py motors_l298n.py hardware.py command_handler.py \
  mqtt_commands.py ir_remote.py lcd_display.py i2c_bus.py oled_display.py \
  mearm_controller.py ov7670.py camera_stream.py color_analysis.py debug_cam.py; do
  "$MPREMOTE" connect "$PORT" fs cp "$FW/$f" ":$f"
done

echo "==> Subiendo libreria umqtt..."
"$MPREMOTE" connect "$PORT" fs mkdir :lib 2>/dev/null || true
"$MPREMOTE" connect "$PORT" fs mkdir :lib/umqtt 2>/dev/null || true
"$MPREMOTE" connect "$PORT" fs cp "$FW/lib/umqtt/__init__.py" :lib/umqtt/__init__.py
"$MPREMOTE" connect "$PORT" fs cp "$FW/lib/umqtt/simple.py"  :lib/umqtt/simple.py

echo "==> Contenido final:"
"$MPREMOTE" connect "$PORT" fs ls

echo "==> Reiniciando Pico..."
"$MPREMOTE" connect "$PORT" reset

echo "Listo. REPL: import robot_repl · robot_repl.help() · robot_repl.start()"
