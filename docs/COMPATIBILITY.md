# Compatibilidad de contratos (dashboard <-> firmware)

Este documento fija los contratos que se preservan durante la migracion a runtime por clases (`Task/Scheduler/Node/MainApp`) con transporte simpleBroker por socket JSON-line.

## Topicos mantenidos (sin cambios)

- `robot/telemetry` (publicacion del firmware)
- `robot/camera` (publicacion del firmware **ESP32-CAM** o legacy Pico/OV7670)
- `robot/commands` (suscripcion del firmware)

Los mensajes se encapsulan internamente con `action: "PUB"/"SUB"` para simpleBroker, pero el dashboard y el payload de datos conservan las mismas claves y estructuras.

## Estructura de payload mantenida

`robot/telemetry` conserva estos bloques:

- `system`: `battery_pct`, `battery_v`, `wifi_rssi`, `uptime_sec`
- `mearm`: `status`, `servos`, `last_action`, `hardware_ok`, `servo_pins`
- `drive`: `direction`, `motor_l_pwm`, `motor_r_pwm`
- `vision`: `target_detected`, `target_coords`, `dominant_color`, `analysis`
- `ir_sensor`: `last_raw_code`, `mapped_command`, `timestamp_ms`
- `ultrasonic`: `distance_cm`, `object_detected`, `zone`, `min_cm`, `max_cm`
- `camera`: `ready`, `stub`, `source`

`robot/camera` mantiene:

- `format`, `width`, `height`, `data`, `ts`, `source` (`esp32cam` | `ov7670`), `frame_id` (si aplica)

`robot/commands` mantiene semantica:

- Drive por `{"cmd":"FWD|REV|LEFT|RIGHT|STOP","l_pwm":..,"r_pwm":..}`
- MeArm por `{"cmd":"GRIPPER_OPEN|GRIPPER_CLOSE|HOME_POSITION"}` o `{"mearm":{...}}`

## Pinout v3 preservado

- OV7670 + OLED por I2C en `GP4/GP5`
- Sin receptor IR fisico
- `GP6` libre

Fuente de verdad: `firmware/hardware_pins.py`.
