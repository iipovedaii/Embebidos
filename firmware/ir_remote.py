# Receptor IR NEC en GPIO (TSOP1838 / VS1838B).
# Decodifica por ancho de pulso; no bloquea el bucle principal.

import time
from machine import Pin

import command_handler

_pin = None
_enabled = False

# Estado del decodificador NEC
_buf = 0
_bits = 0
_last_us = 0
_pending = False

# Umbrales aproximados (microsegundos)
_T_LEADER = 12000
_T_REPEAT = 110000
_T_BIT_0 = 1500
_T_BIT_1 = 2500


def _us_now():
    return time.ticks_us()


def _delta_us(now, prev):
    d = time.ticks_diff(now, prev)
    if d < 0:
        d += 0x40000000
    return d


def _irq_handler(pin):
    global _buf, _bits, _last_us, _pending
    now = _us_now()
    if _last_us == 0:
        _last_us = now
        return
    width = _delta_us(now, _last_us)
    _last_us = now

    # Flanco bajo tras pulso alto: ignorar fin de bit
    if pin.value() != 0:
        return

    if width > _T_REPEAT:
        _bits = 0
        _buf = 0
        return

    if width > _T_LEADER:
        _bits = 0
        _buf = 0
        return

    if _bits >= 32:
        return

    if width > _T_BIT_1:
        _buf = (_buf << 1) | 1
    elif width > 400:
        _buf = (_buf << 1)
    else:
        return
    _bits += 1
    if _bits == 32:
        _pending = True


def init(data_pin):
    global _pin, _enabled, _last_us, _buf, _bits, _pending
    _pin = Pin(data_pin, Pin.IN, Pin.PULL_UP)
    _pin.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, handler=_irq_handler)
    _enabled = True
    _last_us = 0
    _buf = 0
    _bits = 0
    _pending = False
    print("[ir] receptor en GP", data_pin)


def poll():
    """Procesa un codigo NEC pendiente; devuelve True si se aplico comando."""
    global _pending, _buf, _bits
    if not _enabled or not _pending:
        return False
    _pending = False
    code = _buf & 0xFFFFFFFF
    _bits = 0
    # NEC 32b: [addr][~addr][cmd][~cmd] → clave 24b 0xFF18E7
    addr = (code >> 24) & 0xFF
    cmd = (code >> 8) & 0xFF
    cmd_inv = code & 0xFF
    code24 = (addr << 16) | (cmd << 8) | cmd_inv
    return command_handler.apply_ir_code(code24)


def disable():
    global _enabled
    _enabled = False
    if _pin:
        try:
            _pin.irq(handler=None)
        except Exception:
            pass
