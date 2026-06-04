# SISEMB - Configuracion de ejemplo
#
# Copiar este archivo a `config.py` y completar las credenciales reales.
# `config.py` esta gitignored para no comitear secretos.

# ----- Wi-Fi -----
# "ap" = Pico como punto de acceso (PC se conecta a la Pico; evita aislamiento en hotspot movil)
# "sta" = Pico se une a tu router / hotspot
WIFI_MODE = "ap"
WIFI_AP_SSID = "SISEMB-G3"
WIFI_AP_PASS = "cambia_esta_clave"
WIFI_AP_IP = "192.168.4.1"
WIFI_SSID = "MI_RED_WIFI"
WIFI_PASS = "MI_PASSWORD"
WIFI_COUNTRY = "MX"
WIFI_TIMEOUT_SEC = 45
WIFI_CONNECT_RETRIES = 3
WIFI_SCAN_BEFORE_CONNECT = True
# Tras init I2C/servos, reinicia CYW43 antes de MQTT (evita STALL / send_ethernet -5)
WIFI_RECOVER_AFTER_HW = True

# ----- simpleBroker (socket JSON-line PUB/SUB) -----
# Ejecuta `broker/simpleBroker/simple_server.py` en tu PC:
#   TCP 5051 (Pico) + WS 5052 (frontend)
# Con WIFI_MODE=ap: IP del PC en la red de la Pico (suele ser 192.168.4.2).
# Con WIFI_MODE=sta: IP LAN del PC en la misma Wi-Fi que la Pico.
BROKER_HOST = "192.168.4.2"
BROKER_PORT = 5051
TOPIC_PREFIX = ""
BROKER_CONNECT_TIMEOUT_MS = 9000
SOCKET_POLL_INTERVAL_MS = 20
SCHEDULER_IDLE_MS = 3
HEARTBEAT_INTERVAL_MS = 2000
TOPIC_HEARTBEAT = b"robot/heartbeat"

# Alias legacy (compat interna con nombres historicos)
MQTT_BROKER = BROKER_HOST
MQTT_PORT = BROKER_PORT
MQTT_TOPIC = b"robot/telemetry"
MQTT_TOPIC_CMD = b"robot/commands"
MQTT_CLIENT_ID = b"pico-grupo3-01"
TEAM_NAME = "Grupo 3"
TEAM_SHORT = "G3"
MQTT_KEEPALIVE = 30

PUBLISH_INTERVAL_MS = 1000
OLED_UPDATE_INTERVAL_MS = 600
GC_INTERVAL = 20

# False = REPL libre; control con robot_repl.start() / stop() / pause()
# True  = robot autonomo al encender (bloquea REPL hasta Ctrl+C)
RUN_MAIN_ON_BOOT = False

# True = tras cada reset ejecuta Wi-Fi + HW + MQTT (main.py / run_sisemb)
# MicroPico: tambien puedes abrir run_sisemb.py y pulsar Run (dejar esto False)
RUN_ALL_ON_MAIN = False

# ----- Hardware (True = perifericos reales por defecto) -----
HARDWARE_ENABLED = True

# Bateria: divisor de tension en GP26 (ADC0) — R1 arriba, R2 a GND
# Ratio teorico = (R1+R2)/R2  (22k+10k = 3.2)
BATTERY_DIVIDER_RATIO = 3.2
# Ajuste con multimetro: V_real / V_firmware (antes de calibrar)
BATTERY_CALIB_SCALE = 1.0
BATTERY_VREF = 3.3
# Limites del pack (2S tipico). Capacidad mAh no entra en el calculo de %.
BATTERY_V_MIN = 6.0
BATTERY_V_MAX = 8.4

# L298N PCB: IN1/IN2/IN3/IN4 independientes + ENA/ENB (ver docs/PINOUT_PCB.md)
MOTOR_USE_PWM_ENABLE = True
MOTOR_PWM_FREQ = 1000
MOTOR_TANK_PARALLEL = False
MOTOR_TURN_INNER_PCT = 28
MOTOR_TURN_OUTER_PCT = 78

# Receptor IR retirado del hardware (control solo por MQTT/dashboard).

# OLED SSD1306 128x64 (I2C GP4/GP5)
OLED_ENABLED = True
OLED_I2C_ADDR = 0x3C
OLED_WIDTH = 128
OLED_HEIGHT = 64
# "ssd1306" (mayoría) o "sh1106" si ves ruido/tipo QR en lugar de texto
OLED_DRIVER = "ssd1306"
OLED_COL_OFFSET = 0
I2C_SDA_PIN = 4
I2C_SCL_PIN = 5
I2C_FREQ = 100000

# MeArm · servos directos por PWM GPIO (senal; alimentacion externa 5-6 V)
MEARM_SERVO_PINS = {
    "base": 17,
    "shoulder": 18,
    "elbow": 20,
    "gripper": 21,
}
MEARM_HOME = {"base": 90, "shoulder": 70, "elbow": 110, "gripper": 50}
MEARM_SERVO_INVERT = {"base": True, "shoulder": True, "elbow": False, "gripper": False}
MEARM_SERVO_DISABLE = {"base": False, "shoulder": False, "elbow": False, "gripper": False}
MANEUVER_MS_PER_DEG = 18
MANEUVER_DRIVE_MS = 950
MANEUVER_PWM = 70
MEARM_LIMITS = {
    "base": (0, 180),
    "shoulder": (20, 160),
    "elbow": (100, 150),
    "gripper": (0, 180),
}
MEARM_SERVO_MIN_US = 500
MEARM_SERVO_MAX_US = 2500

MEARM_ENABLED = True

# ----- Camara: ESP32-CAM por Wi-Fi al broker (sin GPIO en Pico) -----
CAMERA_ENABLED = False
CAMERA_FORCE_STUB = False
CAMERA_PUBLISH_STUB = False
CAM_RESET_PIN = None
CAM_PWDN_PIN = None
# ESP32-CAM publica a MQTT_TOPIC_CAMERA; Pico solo telemetria/motores/brazo
OV7670_I2C_ADDR = 0x21
CAMERA_WIDTH = 160
CAMERA_HEIGHT = 120
CAMERA_SIZE_DIV = 2
CAMERA_USE_PIO = True
CAMERA_XCLK_HZ = 12_000_000
CAMERA_PUBLISH_INTERVAL_MS = 15000
CAMERA_MIN_CAPTURE_INTERVAL_MS = 12000
CAMERA_THUMB_W = 48
CAMERA_THUMB_H = 36
CAMERA_DEBUG = False
TELEMETRY_VISION_ENABLED = True
CAMERA_VISION_STALE_MS = 20000
SOCKET_TX_MAX_ITEMS = 3
SOCKET_TX_MAX_BYTES = 8192
SOCKET_TX_STUCK_MS = 15000
SOCKET_DROP_CAMERA_ON_PRESSURE = True
CAMERA_FPS_MAX = 2
MQTT_TOPIC_CAMERA = b"robot/camera"
