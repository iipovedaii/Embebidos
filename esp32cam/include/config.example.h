#pragma once

// Copiar a config.h y completar (config.h está en .gitignore).

// ----- Wi-Fi (misma red que Pico y PC broker) -----
#define WIFI_SSID "HONORX8B"
#define WIFI_PASS "CambiaTuPassword"

// ----- simpleBroker (TCP JSON-line, mismo protocolo que la Pico) -----
#define BROKER_HOST "10.104.69.249"
#define BROKER_PORT 5051
#define BROKER_TOPIC_CAMERA "robot/camera"

// Identificador en payload (dashboard / logs)
#define CAMERA_SOURCE "esp32cam"

// ----- Captura -----
#define CAMERA_FRAME_SIZE FRAMESIZE_QQVGA   // 160x120 JPEG
#define CAMERA_JPEG_QUALITY 14              // 0-63 (menor = mejor calidad, más peso)
#define CAMERA_PUBLISH_INTERVAL_MS 2000
#define CAMERA_CONNECT_TIMEOUT_MS 8000

// Reintento broker si se cae el socket
#define BROKER_RECONNECT_MS 3000
