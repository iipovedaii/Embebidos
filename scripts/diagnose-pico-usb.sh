#!/usr/bin/env bash
# Diagnostico USB Pico (sin depender de lsusb).
set -u

echo "=== Puertos serie ==="
found=0
for g in /dev/ttyACM* /dev/ttyUSB* /dev/serial/by-id/*; do
  [[ -e "$g" ]] || continue
  echo "  $g"
  found=1
done
[[ "$found" -eq 0 ]] && echo "  (ninguno — MicroPico no puede conectar aun)"

echo ""
echo "=== Discos tipo BOOTSEL (UF2) ==="
if command -v lsblk &>/dev/null; then
  lsblk -o NAME,SIZE,TYPE,LABEL,MOUNTPOINT 2>/dev/null | grep -iE 'RPI|RP2|RP2350|NAME' || lsblk | head -15
else
  echo "  instala util-linux (lsblk)"
fi
for m in /run/media/*/*/RPI-RP2 /run/media/*/RPI-RP2; do
  [[ -d "$m" ]] && echo "  Montado: $m  -> modo BOOTSEL (arrastra UF2, no es REPL)"
done

echo ""
echo "=== USB Raspberry Pi (sysfs) ==="
shopt -s nullglob
for d in /sys/bus/usb/devices/*; do
  [[ -f "$d/idVendor" ]] || continue
  v=$(cat "$d/idVendor" 2>/dev/null)
  [[ "$v" == "2e8a" ]] || continue
  p=$(cat "$d/idProduct" 2>/dev/null)
  prod=$(cat "$d/product" 2>/dev/null || echo "?")
  echo "  idVendor=2e8a idProduct=$p  $prod"
  echo "    0003 = bootloader RP2040 (BOOTSEL)"
  echo "    0005 = MicroPython CDC (REPL OK)"
  echo "    000f = bootloader RP2350 / Pico 2 (BOOTSEL)"
done
shopt -u nullglob

echo ""
echo "=== Ultimos mensajes kernel (USB) ==="
if command -v journalctl &>/dev/null; then
  journalctl -k -n 40 --no-pager 2>/dev/null | grep -iE 'usb|acm|tty|2e8a|cdc' | tail -12 || echo "  (sin entradas recientes)"
elif command -v dmesg &>/dev/null; then
  dmesg 2>/dev/null | grep -iE 'usb|acm|tty|2e8a|cdc' | tail -12
else
  echo "  journalctl/dmesg no disponible"
fi

echo ""
echo "=== Que hacer ==="
echo "1. Cable USB con DATOS (no solo carga)."
echo "2. Sin BOOTSEL: enchufa normal -> debe salir /dev/ttyACM0 y idProduct 0005."
echo "3. Si solo ves RPI-RP2 o 0003/000f: copia RPI_PICO2_W-*.uf2 y espera reinicio."
echo "4. Arch: grupo uucp (ya lo tienes). Opcional: udev/99-rpi-pico-serial.rules"
echo "5. Instalar lsusb: sudo pacman -S usbutils"
