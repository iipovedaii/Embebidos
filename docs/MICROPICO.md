# MicroPico / vREPL con Pico 2 W

## Si ves esto al abrir vREPL

```
Failed to get MicroPython version and machine type.
Waiting for board to connect...
```

**No significa que las 4 Pico estén mal.** En muchos casos la placa **sí responde** unos segundos después (banner `Pico 2 W with RP2350` y `>>>`). Es un fallo de **timing** entre Cursor y el puerto USB al arrancar.

## Arranque con un solo clic (botón Run)

1. Sube el firmware (incluye **`sisemb_loop.py`** y **`run_sisemb.py`**).
2. En el editor, abre **`firmware/run_sisemb.py`** (o `main.py` si `RUN_ALL_ON_MAIN = True` en `config.py`).
3. Pulsa **Run** (reinicia la Pico y ejecuta todo: Wi-Fi → hardware → MQTT).

Verás `=== SISEMB arranque automatico ===` y luego `[mqtt] conectado...`. **Ctrl+C** para parar.

`Run` siempre hace un reinicio suave antes (normal). El bucle va en **primer plano** (`blocking=True`) porque `_thread` en Pico 2 W a veces falla sin mostrar el error.

### Si `start()` dice "Exception occured"

Causas habituales:

| Causa | Solución |
|-------|----------|
| Falta `sisemb_loop.py` en la Pico | Vuelve a subir firmware / `upload-firmware.sh` |
| `start()` en segundo plano falla | Usa `robot_repl.start(blocking=True)` o **Run** en `run_sisemb.py` |
| Wi-Fi aún no listo | Espera `[wifi] OK` antes de `start()` |

En REPL (opcional): `import robot_repl` → `robot_repl.run_all()`

Comprueba `RUN_MAIN_ON_BOOT = False` y, si quieres Run en `main.py`, `RUN_ALL_ON_MAIN = True`.

## Flujo que funciona (Pico 2 W)

1. Enchufa la Pico **sin BOOTSEL**.
2. Espera **3–5 s** y comprueba:
   ```bash
   ls /dev/ttyACM0
   ./scripts/diagnose-pico-usb.sh
   ```
   Debe verse `idProduct=0005` y `MicroPython`.
3. En la Pico: **`RUN_MAIN_ON_BOOT = False`** en `config.py` y control con `robot_repl` (no se auto-ejecuta `main.py`).
4. Tras conectar, en el REPL: `import robot_repl` → `robot_repl.start()` para telemetria; `robot_repl.stop()` para parar.
5. **Cierra** vREPL viejos (solo una conexión al puerto).
6. Paleta → **MicroPico: Connect** (no solo abrir terminal vREPL).
7. Si sigue en "Waiting…": **MicroPico: Reset (soft)** → espera 2 s → **Connect** otra vez.

## Errores de notificación en Cursor

| Mensaje | Causa | Solución |
|---------|--------|----------|
| `stubPath .../~/.micropico-stubs` no válido | `~` mal resuelto dentro del proyecto | Corregido: ruta absoluta `/home/hell/.micropico-stubs/included` |
| No COM device found | Pico desenchufada o USB error -71 | Enchufa, espera `ttyACM0`, `./scripts/diagnose-pico-usb.sh` |
| autoConnect off sin manualComDevice | Config antigua | `autoConnect: true` de nuevo en `.vscode/settings.json` |

## Configuración del proyecto

- `micropico.openOnStart`: **false**
- `micropico.autoConnect`: **true** (detecta la Pico al enchufar)
- `micropico.syncFolder`: **firmware**

## Varias Pico 2 W

Cada placa tiene distinto serial en `/dev/serial/by-id/`. No fijes `ttyACM0` si cambias de board; deja auto o elige el puerto en **MicroPico: Switch Pico**.

## Si nunca aparece `/dev/ttyACM0`

Eso es USB/kernel (cable, puerto, error -71 en `dmesg`), no MicroPico. Ver `scripts/diagnose-pico-usb.sh`.

## Alternativa fiable

```bash
mpremote connect auto repl
```

O Thonny con interpreter **MicroPython (Raspberry Pi Pico 2 W)**.
