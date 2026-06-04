# SISEMB · Robot Telemetry Dashboard

Dashboard de control y telemetria para un robot movil basado en **Raspberry Pi Pico 2W** (MicroPython) con brazo robotico MeArm, chasis de 2 motores, camara OV7670, pantalla OLED y vision/IA. El firmware publica telemetria con runtime por clases sobre simpleBroker (socket JSON-line PUB/SUB) y el dashboard web consume los mismos topicos/JSON en tiempo real.

```
+-------------+  telemetry 500ms   +------------------+   WebSocket TLS   +-------------+
|  Pico 2W    | -----------------> | simple_server.py | <---------------- |  Dashboard  |
| MicroPython | robot/telemetry    | TCP 5051 / WS5052|  ws://...:5052    |  (SPA web)  |
| OLED + CAM  | <----------------- | robot/commands   |  D-pad LIVE       |             |
+-------------+   comandos drive   +------------------+                   +-------------+
```

---

## Estructura del proyecto

```
SISEMB/
├── blink.py                 # demo original (intacto)
├── frontend/
│   ├── index.html           # SPA Tailwind + Chart.js
│   ├── styles.css           # estilos cyberpunk + animaciones
│   └── app.js               # logica simpleBroker WS + render
├── firmware/
│   ├── main.py              # bucle telemetria (no auto-arranque)
│   ├── robot_repl.py        # start/stop/pause desde REPL
│   ├── robot_ctl.py         # estado compartido del bucle
│   ├── config.example.py    # template de credenciales
│   ├── config.py            # tu copia real (gitignored)
│   ├── wifi_manager.py      # conexion + reconexion exponencial
│   ├── telemetry.py         # payload JSON (hardware + MeArm real)
│   ├── mearm_controller.py  # brazo MeArm 4 servos PWM GPIO
│   ├── i2c_bus.py           # bus I2C compartido
│   ├── command_handler.py   # conduccion dashboard/simpleBroker
│   ├── mqtt_commands.py       # parser topic robot/commands
│   ├── oled_display.py        # OLED SSD1306 128x64 I2C (GP4/GP5)
│   ├── ir_remote.py           # (legacy, no conectado)
│   ├── lcd_display.py         # (legacy, reemplazado por OLED)
│   ├── hardware_pins.py     # mapa de GPIO
│   ├── battery.py           # ADC bateria
│   ├── hcsr04.py            # ultrasonido
│   ├── motors_l298n.py      # L298N 2 motores
│   └── hardware.py          # init perifericos
├── esp32cam/                # ESP32-CAM → broker robot/camera (independiente)
│   ├── README.md
│   ├── platformio.ini
│   ├── include/
│   └── src/
├── docs/
│   ├── HARDWARE.md          # cableado y montaje
│   ├── PINOUT_PCB.md        # pinout definitivo PCB
│   └── ESP32_CAM.md         # integración cámara Wi-Fi
├── .gitignore
└── README.md
```

---

## 1. Dashboard (frontend)

### Abrirlo

No requiere build. Tres opciones:

1. **Doble click** en `frontend/index.html` (`file://`). Funciona pero algunos navegadores bloquean WebSocket desde `file://`.
2. **Servidor estatico local** (recomendado):
   ```bash
   cd frontend
   python3 -m http.server 8000
   ```
   Luego abrir <http://localhost:8000>.
3. **GitHub Pages / Vercel / Netlify**: subir la carpeta `frontend/` tal cual.

### Telemetria en vivo

Al cargar, el dashboard se conecta por WebSocket a `robot/telemetry`. El **D-pad** y los controles **MeArm** publican a `robot/commands` cuando el broker esta conectado.

> El broker EMQX publico es gratuito y sin auth. **No publiques informacion sensible**; cualquiera puede leer el topic.
>
> Contratos de compatibilidad (topics y payload): ver `docs/COMPATIBILITY.md`.
> Arranque broker + dashboard en Linux: ver `docs/SETUP_BROKER.md`.

### Widgets

| Widget          | Datos consumidos                          |
| --------------- | ----------------------------------------- |
| Header          | `system.battery_pct/v`, `wifi_rssi`, ping |
| MeArm           | `mearm.servos.*`, `status`, `last_action` |
| Drive           | `drive.direction`, `motor_l_pwm`, `motor_r_pwm` |
| Vision Stream   | `vision.target_coords`, `target_detected` |
| Analisis IA     | `vision.dominant_color`, `vision.analysis[]` (umbrales RGB en `vision_color.js` + frame `robot/camera`) |
| Log IR          | `ir_sensor.last_raw_code`, `mapped_command` |
| Ultrasonido     | `ultrasonic.distance_cm`, `zone`, `object_detected` |

---

## 2. Hardware (bateria, ultrasonido, motores)

Guía completa de montaje, pines y calibración: **[docs/HARDWARE.md](docs/HARDWARE.md)**.

Resumen de pines Pico 2W:

| Periferico | Pines |
|------------|--------|
| Bateria (ADC) | GP26 |
| HC-SR04 Trig / Echo | GP2 / GP3 |
| OLED I2C SDA / SCL | GP4 / GP5 (@ 0x3C) |
| GP6 | Libre |
| L298N IN1, IN2 (modo tanque) | GP14, GP15 · IN3/IN4 puenteados a IN1/IN2 en el módulo |
| L298N ENA/ENB | En el módulo a 5 V (sin GPIO) · ver `MOTOR_USE_PWM_ENABLE` |
| MeArm servos base / hombro / codo / pinza | GP17 / GP18 / GP20 / GP21 |
| OV7670 D0–D7, VSYNC, HREF, PCLK, XCLK | GP0–1, GP7–13, GP27–28, GP22 |
| OV7670 RESET / PWDN | GP16 / GP19 |
| OV7670 SCCB (I2C) | GP4 / GP5 (compartido con OLED) |

Por defecto `HARDWARE_ENABLED = True` en `config.example.py`. Detalle: **[docs/HARDWARE.md](docs/HARDWARE.md)**.

---

## 3. Firmware (Raspberry Pi Pico 2W)

### Requisitos

- Raspberry Pi Pico 2W con firmware **MicroPython oficial**.
- Herramienta de flasheo:
  - VSCode + extension **MicroPico**, o
  - [Thonny](https://thonny.org/), o
  - `rshell` / `mpremote`.

### Configuracion

1. Copiar el template:
   ```bash
   cp firmware/config.example.py firmware/config.py
   ```
2. Editar `firmware/config.py` con tu **SSID**, **password** y `BROKER_HOST` (IP local de tu PC).

### Levantar broker simpleBroker (PC)

En tu computadora (misma red que la Pico):

**Linux (recomendado):**

```bash
./scripts/start_stack.sh          # broker + dashboard
# o por separado:
./scripts/start-broker.sh
./scripts/start-dashboard.sh
```

**Windows:**

```powershell
.\scripts\start_stack.ps1
```

**Manual:**

```bash
python broker/simpleBroker/simple_server.py
```

Guía completa, firewall y diagnóstico: **[docs/SETUP_BROKER.md](docs/SETUP_BROKER.md)**.

Debe mostrar:

```text
TCP on 5051 | WS on 5052
```

### MicroPico: "Failed to get MicroPython version" (varias Pico 2 W)

Ese mensaje suele ser **carrera al conectar**, no placa rota. Tras unos segundos puede aparecer `Pico 2 W with RP2350`. Guia completa: **[docs/MICROPICO.md](docs/MICROPICO.md)**.

Resumen: enchufa → espera 3 s → `RUN_MAIN_ON_BOOT = False` → **MicroPico: Connect** (autoConnect desactivado) → si falla, **Reset soft** y Connect otra vez.

### Prueba rapida en REPL (Wi-Fi + broker)

Con la Pico conectada por USB y Thonny / MicroPico / `mpremote`:

```python
import repl_test_wifi_mqtt
repl_test_wifi_mqtt.run()
```

Debe imprimir `[test] Wi-Fi OK`, conexion TCP y publicacion de prueba en `b'robot/telemetry'`. Luego abre el dashboard.

### Control desde el REPL (recomendado)

Por defecto `RUN_MAIN_ON_BOOT = False`: al encender solo veras el REPL. Control manual:

```python
import robot_repl
robot_repl.help()
robot_repl.wifi_connect()
robot_repl.start()      # bucle en segundo plano (_thread)
robot_repl.status()
robot_repl.pause()
robot_repl.resume()
robot_repl.stop()
robot_repl.wifi_disconnect()
```

`start(blocking=True)` ocupa el REPL hasta Ctrl+C (equivale a `stop()`).

### Arranque automatico

Con `RUN_MAIN_ON_BOOT = True` en `config.py`, `boot.py` arranca el robot al encender (sin REPL libre). Sube con `./scripts/flash-sisemb.sh`.

### Subida a la Pico

Con `mpremote` (la opcion mas simple desde CLI):

```bash
./scripts/flash-sisemb.sh
# o solo actualizar:
./scripts/upload-firmware.sh
```

Con VSCode + MicroPico: abrir cada archivo y `Run` o `Upload project to Pico`.

Al iniciar veras en la consola algo como:

```
[wifi] conectando a MI_RED_WIFI ...
[wifi] OK -> ('192.168.1.42', '255.255.255.0', '192.168.1.1', '192.168.1.1')
[broker] conectado a 192.168.1.100 5051
[main] simpleBroker runtime host=192.168.1.100 port=5051 topic=robot/telemetry
```

El LED interno parpadea durante la conexion y queda encendido fijo cuando esta conectado.

---

## 3. Verificacion end-to-end

1. Levantar `simple_server.py` en la PC.
2. Subir firmware al Pico y esperar el log `[broker] conectado`.
3. Abrir dashboard y verificar telemetría/cámara en vivo.
4. Probar D-pad y verificar respuesta de motores/MeArm.
4. Verificar que `system.uptime_sec` se incremente y que la latencia ronde los 50-300 ms.

Si la pestana no recibe nada en LIVE:
- Verifica firewall en tu PC para puertos TCP **5051** y **5052**.
- Revisa la consola del navegador (F12): debe abrir `ws://<IP_PC>:5052`.
- Confirma que Pico y dashboard usan la misma IP local del broker.

---

## 4. Personalizacion rapida

- **Cambiar broker**: editar `firmware/config.py` (broker, puerto, topic) y en `frontend/app.js` la constante `CONFIG.BROKER_URL` y `CONFIG.TOPIC`.
- **Mover broker de PC**: cambiar `BROKER_HOST`/`BROKER_PORT` en `config.py` y `BROKER_WS_URL` en `frontend/app.js`.
- **Reducir RAM**: subir `GC_INTERVAL` y/o aumentar `PUBLISH_INTERVAL_MS` (p.ej. 1000 ms).
- **Comandos**: topic `robot/commands`, JSON `{"cmd":"FWD","l_pwm":70,"r_pwm":70}`.
- **MeArm**: servos en GP17/18/20/21; alimentacion externa 5-6 V y GND comun. **Camara**: RST/PWDN en GP16/GP19 (`CAM_RESET_PIN` / `CAM_PWDN_PIN`); vision real con `CAMERA_FORCE_STUB = False`.

---

## 5. Notas tecnicas

- El payload pesa ~400 bytes. Publicar a 2 Hz sobre Wi-Fi estable es comodo para el Pico 2W.
- `gc.collect()` se invoca cada `GC_INTERVAL` iteraciones (default 20 ~= 10 s).
- Sin telemetria, los paneles muestran valores en espera; el gemelo 3D no anima el brazo hasta recibir `mearm.servos`.
- Lucide, Tailwind y Chart.js se cargan por CDN (cero `npm install`).
