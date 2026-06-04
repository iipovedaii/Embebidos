# HC-SR04 · sensor ultrasonico (Trig/Echo).
# Montaje: fijo al frente del chasis, apuntando hacia adelante.

import time
import machine
from machine import Pin

_trig = None
_echo = None
_last_cm = None


def init(trig_pin, echo_pin):
    global _trig, _echo
    _trig = Pin(trig_pin, Pin.OUT, value=0)
    _echo = Pin(echo_pin, Pin.IN)


def measure_cm(timeout_us=30000):
    """Devuelve distancia en cm o None si no hay eco valido."""
    global _last_cm
    if _trig is None or _echo is None:
        return _last_cm

    _trig.value(0)
    time.sleep_us(2)
    _trig.value(1)
    time.sleep_us(10)
    _trig.value(0)

    pulse = machine.time_pulse_us(_echo, 1, timeout_us)

    if pulse < 0:
        return _last_cm

    # velocidad del sonido ~343 m/s → ~0.0343 cm/us, ida y vuelta /2
    cm = (pulse * 0.0343) / 2.0
    if cm < 0.5:
        return _last_cm
    _last_cm = round(cm, 1)
    return _last_cm


def read(min_cm=2, max_cm=400):
    """Distancia, eco valido y zona para el dashboard."""
    cm = measure_cm()
    if cm is None:
        return 0.0, False, "OUT_OF_RANGE"

    valid = min_cm <= cm <= max_cm
    if cm < 15:
        zone = "CRITICAL"
    elif cm < 35:
        zone = "WARNING"
    elif cm < 120:
        zone = "OK"
    elif cm <= max_cm:
        zone = "CLEAR"
    else:
        zone = "OUT_OF_RANGE"
        valid = False

    return cm, valid, zone
