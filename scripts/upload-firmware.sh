#!/usr/bin/env bash
# Sube todos los modulos del firmware a la Raspberry Pi Pico 2W.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FW="$ROOT/firmware"
MPREMOTE="${MPREMOTE:-$HOME/.local/bin/mpremote}"

if [[ ! -x "$MPREMOTE" ]] && ! command -v mpremote &>/dev/null; then
  echo "mpremote no encontrado. Instalar: pipx install mpremote"
  exit 1
fi

MPREMOTE="$(command -v mpremote || echo "$MPREMOTE")"

if [[ ! -f "$FW/config.py" ]]; then
  echo "No existe firmware/config.py — cp firmware/config.example.py firmware/config.py"
  exit 1
fi

PORT="${1:-auto}"
echo "Conectando a $PORT ..."

FILES=(
  boot.py config.py robot_ctl.py robot_repl.py run_sisemb.py wifi_manager.py repl_test_wifi_mqtt.py repl_test_camera.py diag_camera.py telemetry.py main.py sisemb_loop.py runtime_simplebroker.py hardware_pins.py ov7670_registers.py ov7670_pio.py
  battery.py hcsr04.py motors_l298n.py hardware.py command_handler.py
  mqtt_commands.py ir_remote.py lcd_display.py i2c_bus.py oled_display.py
  mearm_controller.py ov7670.py camera_stream.py color_analysis.py debug_cam.py
)

for f in "${FILES[@]}"; do
  "$MPREMOTE" connect "$PORT" fs cp "$FW/$f" ":$f"
done

"$MPREMOTE" connect "$PORT" fs mkdir :lib 2>/dev/null || true
"$MPREMOTE" connect "$PORT" fs mkdir :lib/umqtt 2>/dev/null || true
"$MPREMOTE" connect "$PORT" fs cp "$FW/lib/umqtt/__init__.py" :lib/umqtt/__init__.py
"$MPREMOTE" connect "$PORT" fs cp "$FW/lib/umqtt/simple.py"  :lib/umqtt/simple.py

echo ""
echo "Listo. Archivos en la Pico:"
"$MPREMOTE" connect "$PORT" fs ls

echo ""
echo "Reiniciando la Pico (soft reset)..."
"$MPREMOTE" connect "$PORT" reset
