# Broker local + Dashboard · Guía rápida (Linux)

Telemetría Pico 2W → **simpleBroker** (portátil) → **dashboard web** por WebSocket.

```
Pico 2W (TCP 5051)  →  simple_server.py  ←  Dashboard (WS 5052)
ESP32-CAM (TCP 5051) →       PUB/SUB              subscribe
       publish              robot/camera         robot/commands
   robot/telemetry      robot/camera
```

La **ESP32-CAM** publica `robot/camera` por su cuenta (ver [ESP32_CAM.md](ESP32_CAM.md)). La Pico publica telemetría y deja la cámara desactivada (`CAMERA_ENABLED = False`).

## Requisitos

- Portátil y Pico 2W en la **misma red Wi-Fi**
- Python 3 con dependencias del broker (se crea `.venv` automáticamente en Linux/Arch):

```bash
./scripts/ensure-broker-venv.sh
```

O manualmente: `python3 -m venv .venv && .venv/bin/pip install -r requirements-broker.txt`
- Puertos libres en el portátil: **5051** (TCP), **5052** (WebSocket), **8765** (HTTP dashboard, configurable)

## 1. Arrancar el stack en el portátil

Opción recomendada (broker + dashboard juntos):

```bash
./scripts/start_stack.sh
```

Solo broker:

```bash
./scripts/start-broker.sh
```

Solo dashboard (con broker ya corriendo):

```bash
./scripts/start-dashboard.sh
# o puerto custom: ./scripts/start-dashboard.sh 8000
```

Debe aparecer en consola:

```text
TCP listening on 5051
TCP on 5051 | WS on 5052
```

Abre: **http://127.0.0.1:8765/index.html**

## 2. Configurar la Pico (`firmware/config.py`)

| Campo | Valor | Notas |
|-------|-------|-------|
| `WIFI_SSID` / `WIFI_PASS` | Tu red | Misma Wi-Fi que el portátil |
| `BROKER_HOST` | IP LAN del portátil | Ej. `10.104.69.249` — **no** uses IP de otra red |
| `BROKER_PORT` | `5051` | TCP hacia `simple_server.py` |
| `TOPIC_PREFIX` | `""` | Debe coincidir con el dashboard |
| `MQTT_TOPIC` | `b"robot/telemetry"` | Sin cambios |
| `MQTT_TOPIC_CMD` | `b"robot/commands"` | Comandos D-pad / MeArm |
| `MQTT_TOPIC_CAMERA` | `b"robot/camera"` | Stream cámara (**ESP32-CAM**, no Pico) |

## 2b. Configurar ESP32-CAM (cámara independiente)

Ver guía completa: **[ESP32_CAM.md](ESP32_CAM.md)** y `esp32cam/README.md`.

```bash
cp esp32cam/include/config.example.h esp32cam/include/config.h
# Editar WIFI_SSID, WIFI_PASS, BROKER_HOST (misma IP que la Pico)
./esp32cam/scripts/upload-esp32cam.sh
```

En la Pico mantén `CAMERA_ENABLED = False`.

Obtener IP del portátil:

```bash
ip -4 -o addr show scope global | awk '{print $4}' | cut -d/ -f1
```

Tras editar, sube firmware:

```bash
./scripts/upload-firmware.sh
```

En REPL (MicroPico / mpremote):

```python
import robot_repl
robot_repl.wifi_connect()
robot_repl.start()
```

Log esperado en la Pico:

```text
[wifi] OK -> ('10.104.69.x', ...)
[broker] conectado a 10.104.69.249 5051
```

## 3. Dashboard (`frontend/app.js`)

El WebSocket se resuelve automáticamente con el hostname del navegador:

```js
BROKER_WS_URL: `ws://${window.location.hostname}:5052`
```

| Dónde abres el dashboard | URL HTTP | WebSocket efectivo |
|--------------------------|----------|-------------------|
| Mismo portátil | `http://127.0.0.1:8765/` | `ws://127.0.0.1:5052` |
| Otro dispositivo en LAN | `http://<IP_PC>:8765/` | `ws://<IP_PC>:5052` |

**No uses `file://`** — algunos navegadores bloquean WebSocket.

## 4. Verificación end-to-end

1. Broker activo → consola muestra `TCP on 5051 | WS on 5052`
2. Dashboard → pill **BROKER ON**
3. Pico publicando → pill **PICO ONLINE**, widgets con datos
4. D-pad LIVE → motores responden (`robot/commands`)
5. `system.uptime_sec` incrementa; latencia ~50–300 ms

Prueba rápida Wi-Fi + broker desde REPL:

```python
import repl_test_wifi_mqtt
repl_test_wifi_mqtt.run()
```

## 5. Diagnóstico por síntomas

### `BROKER OFF` en el dashboard

| Causa probable | Qué hacer |
|----------------|-----------|
| Broker no arrancado | `./scripts/start-broker.sh` o `start_stack.sh` |
| Falta `websockets` | `pip install -r requirements-broker.txt` — si falta, consola dice "Solo TCP activo" |
| Puerto 5052 ocupado/bloqueado | `ss -tlnp \| grep 5052`; abrir firewall |
| URL WS incorrecta | F12 → Network/Console; debe ser `ws://<host>:5052` |
| Dashboard en `file://` | Usar `http.server` vía scripts |

### `BROKER ON` pero `PICO OFFLINE`

| Causa probable | Qué hacer |
|----------------|-----------|
| `BROKER_HOST` incorrecto en `config.py` | IP LAN actual del portátil, misma subred que la Pico |
| Pico sin Wi-Fi | REPL: `robot_repl.wifi_connect()` |
| Bucle no iniciado | REPL: `robot_repl.start()` |
| Puerto 5051 bloqueado | Firewall del portátil; la Pico debe alcanzar TCP 5051 |
| Red distinta | PC y Pico deben estar en la misma Wi-Fi |
| Cola TX llena (`camera esperando TX cola=3`) | Reinicia broker; sube firmware con fix de socket; la Pico reconecta sola |
| `status()` muestra `broker=OFF` pero TCP activo | Bug corregido: tras reconexión `mqtt_linked` se actualiza de nuevo |

### Pico conecta y luego “no reconecta”

En serial de la Pico deberías ver:

```text
[broker] enlace perdido: ...
[broker] reintentando conexion a 10.104.69.249 5051
[broker] conectado a 10.104.69.249 5051
```

Si no aparece `reintentando`, sube el firmware actualizado (`runtime_simplebroker.py`).
Reinicia el broker tras actualizar `simple_server.py` (publicación async + logs).

### Broker log sin `[PUB] robot/telemetry`

- Pico no conectada o `BROKER_HOST` erróneo
- Revisar serial: `[broker] connect fallo:` o `timeout conectando`

### Broker log con `[PUB]` pero dashboard vacío

- Dashboard no suscrito → recargar página con broker ya activo
- Consola navegador: errores WebSocket o JSON parse

### Comandos D-pad no funcionan

- Requiere **BROKER ON** y **PICO ONLINE**
- Topic: `robot/commands` — formato `{"cmd":"FWD","l_pwm":70,"r_pwm":70}`

## Firewall (Arch Linux / firewalld)

Si usas firewalld:

```bash
sudo firewall-cmd --add-port=5051/tcp --add-port=5052/tcp --add-port=8765/tcp
```

## Archivos de referencia

| Archivo | Rol |
|---------|-----|
| [broker/simpleBroker/simple_server.py](../broker/simpleBroker/simple_server.py) | Broker TCP + WS |
| [firmware/config.py](../firmware/config.py) | Wi-Fi + `BROKER_HOST` |
| [frontend/app.js](../frontend/app.js) | Cliente WebSocket dashboard |
| [docs/COMPATIBILITY.md](COMPATIBILITY.md) | Contratos topics/payload |
| [scripts/start_stack.sh](../scripts/start_stack.sh) | Arranque todo-en-uno Linux |
