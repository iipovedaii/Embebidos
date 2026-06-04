# Varios robots en la misma red · simpleBroker

Para integrar varios robots similares que se sincronicen vía broker, **no hace falta reescribir todo a clases**. Sí conviene **unificar contratos** (topics + JSON) y **separar identidad por robot**.

## Patrón recomendado

```
robot-A/telemetry   robot-B/telemetry
robot-A/commands    robot-B/commands
robot-A/camera      robot-B/camera
        \              /
         simple_server.py
              |
         dashboard (elige robot)
```

### En cada Pico (`config.py`)

```python
ROBOT_ID = "robot-A"   # único por placa
TOPIC_PREFIX = "robot-A/"   # o f"{ROBOT_ID}/"

MQTT_TOPIC = b"telemetry"          # NodePubSub añade prefix → robot-A/telemetry
MQTT_TOPIC_CMD = b"commands"
MQTT_TOPIC_CAMERA = b"camera"
```

### En el dashboard (`frontend/app.js`)

```javascript
const ROBOT_ID = "robot-A";
const TOPIC_PREFIX = `${ROBOT_ID}/`;
// TOPIC: TOPIC_PREFIX + "telemetry", etc.
```

## Sincronización entre robots

| Necesidad | Cómo |
|-----------|------|
| Misma telemetría / comandos | Mismo contrato en `docs/COMPATIBILITY.md` |
| Varios clientes leyendo un robot | Varios `SUB` al mismo topic en el broker |
| Orquestador / líder | Nodo extra (PC o Pico maestra) publica en `robot-B/commands` |
| Estado compartido (formación) | Topic adicional `fleet/sync` con JSON acordado |

## Gemelo digital exacto

El dashboard usa **telemetría real** (`drive.motor_l_pwm`, `drive.motor_r_pwm`, `mearm.servos`):

- **MeArm:** ángulos del gemelo = `mearm.servos` de telemetría (sin retardo artificial).
- **Chasis:** PWM y dirección del gemelo = telemetría; la pose X/Y se integra en el cliente (no hay odometría en firmware aún).

Para exactitud física total del chasis haría falta odometría en firmware (encoders / IMU) en una fase posterior.

## Evolución arquitectónica (opcional)

Si el flota crece mucho:

1. Mantener drivers por módulo (`motors_l298n.py`, …).
2. Añadir `class RobotNode` que envuelva `MainApp` + `ROBOT_ID`.
3. Broker central sigue siendo `simple_server.py` o MQTT enterprise.

No es obligatorio antes de tener 2–3 robots funcionando con `TOPIC_PREFIX`.
