# ESP32-CAM · Guía de integración SISEMB

Documentación detallada del firmware: **[../esp32cam/README.md](../esp32cam/README.md)**.

## Resumen

La ESP32-CAM es un **cliente broker independiente**. No usa GPIO de la Pico.

| Item | Valor |
|------|-------|
| Topic | `robot/camera` |
| Puerto | TCP **5051** (simpleBroker) |
| Formato | JPEG base64 |
| Pico | `CAMERA_ENABLED = False` |

## Pasos

1. Copiar `esp32cam/include/config.example.h` → `esp32cam/include/config.h`
2. Misma Wi-Fi y `BROKER_HOST` que la Pico
3. `./esp32cam/scripts/upload-esp32cam.sh`
4. `./scripts/start_stack.sh` + dashboard

## Coexistencia con Pico

```
ESP32-CAM  ──PUB──► robot/camera
Pico 2W    ──PUB──► robot/telemetry
Pico 2W    ◄─SUB──  robot/commands
Dashboard  ◄─SUB──  camera + telemetry
Dashboard  ──PUB──► commands
```

No hay conflicto: cada dispositivo publica su topic.
