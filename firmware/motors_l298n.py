# Control de 2 motores DC via modulo L298N (puente H).
#
# Modo SISEMB (tanque cableado):
#   IN1+IN3 → mismo GPIO (GP14), IN2+IN4 → mismo GPIO (GP15): misma direccion ambas ruedas.
#   ENA (motor izq) y ENB (motor der) en GPIO separados → giro = bajar PWM en una rueda.
#
# Modo diferencial (4 GPIO direccion): IN1/IN2 izq, IN3/IN4 der en la Pico.

from machine import Pin, PWM

_in1 = _in2 = _in3 = _in4 = None
_pwm_l = _pwm_r = None
_use_pwm_enable = False
_tank_parallel = True
_tank_split_pwm = False
_dir = "STOP"
_l_pct = 0
_r_pct = 0
_turn_inner = 30
_turn_outer = 75


def _duty(pct):
    pct = max(0, min(100, int(pct)))
    return int(pct * 655.35)


def configure(cfg=None):
    """PWM de giro (rueda lenta / rapida) desde config.py."""
    global _turn_inner, _turn_outer
    if cfg is None:
        return
    _turn_inner = int(getattr(cfg, "MOTOR_TURN_INNER_PCT", 30))
    _turn_outer = int(getattr(cfg, "MOTOR_TURN_OUTER_PCT", 75))


def init(in1, in2, ena, in3, in4, enb, pwm_freq=1000, use_pwm_enable=True):
    global _in1, _in2, _in3, _in4, _pwm_l, _pwm_r, _use_pwm_enable, _tank_parallel, _tank_split_pwm
    _in1 = Pin(in1, Pin.OUT, value=0)
    _in2 = Pin(in2, Pin.OUT, value=0)
    _tank_parallel = in3 is None or in4 is None
    if _tank_parallel:
        _in3 = _in4 = None
        print("[motors] L298N modo TANQUE (IN1/IN3 e IN2/IN4 en comun)")
    else:
        _in3 = Pin(in3, Pin.OUT, value=0)
        _in4 = Pin(in4, Pin.OUT, value=0)
        print("[motors] L298N modo DIFERENCIAL (IN1-IN4 en Pico)")

    _use_pwm_enable = bool(use_pwm_enable) and ena is not None and enb is not None
    _tank_split_pwm = bool(_tank_parallel and _use_pwm_enable)
    _pwm_l = _pwm_r = None
    if _use_pwm_enable:
        _pwm_l = PWM(Pin(ena))
        _pwm_r = PWM(Pin(enb))
        _pwm_l.freq(pwm_freq)
        _pwm_r.freq(pwm_freq)
        if _tank_split_pwm:
            print("[motors] Giro por PWM asimetrico ENA/ENB (rueda lenta + rueda rapida)")
        else:
            print("[motors] PWM ENA/ENB activo")
    elif _tank_parallel:
        print("[motors] AVISO: sin ENA/ENB en Pico no hay giro LEFT/RIGHT (solo FWD/REV)")

    stop()


def _set_direction_pins(forward):
    if forward:
        _in1.on()
        _in2.off()
    else:
        _in1.off()
        _in2.on()


def _set_tank_split_pwm(l_pct, r_pct, forward=True):
    """Misma direccion (IN1/IN2), velocidades distintas por ENA (izq) y ENB (der)."""
    global _dir, _l_pct, _r_pct
    _l_pct = max(0, min(100, int(l_pct)))
    _r_pct = max(0, min(100, int(r_pct)))

    if _l_pct == 0 and _r_pct == 0:
        stop()
        return

    _set_direction_pins(forward)

    if _l_pct == _r_pct:
        if forward:
            _dir = "FORWARD" if _l_pct > 0 else "STOP"
        else:
            _dir = "REVERSE"
    elif _l_pct < _r_pct:
        _dir = "LEFT" if forward else "LEFT_REV"
    else:
        _dir = "RIGHT" if forward else "RIGHT_REV"

    if _pwm_l:
        _pwm_l.duty_u16(_duty(_l_pct))
    if _pwm_r:
        _pwm_r.duty_u16(_duty(_r_pct))


def _motor_side(in_a, in_b, pwm, pct, forward):
    pct = max(0, min(100, int(pct)))
    if pct == 0:
        in_a.off()
        in_b.off()
        if pwm:
            pwm.duty_u16(0)
        return
    if forward:
        in_a.on()
        in_b.off()
    else:
        in_a.off()
        in_b.on()
    if pwm:
        pwm.duty_u16(_duty(pct))


def set_motors(l_pct, r_pct, forward=True):
    """l_pct/r_pct 0-100. En tanque+ENA/ENB: PWM distinto por rueda, misma direccion."""
    global _dir, _l_pct, _r_pct
    _l_pct = max(0, min(100, int(l_pct)))
    _r_pct = max(0, min(100, int(r_pct)))

    if _tank_split_pwm:
        _set_tank_split_pwm(_l_pct, _r_pct, forward=forward)
        return

    if _tank_parallel:
        pct = max(_l_pct, _r_pct)
        if pct == 0:
            _dir = "STOP"
        elif forward:
            _dir = "FORWARD"
        else:
            _dir = "REVERSE"
        _motor_side(_in1, _in2, _pwm_l, pct, forward)
        if _pwm_r and _pwm_l is not _pwm_r:
            _pwm_r.duty_u16(_duty(pct))
        return

    if _l_pct == 0 and _r_pct == 0:
        _dir = "STOP"
    elif forward:
        _dir = "FORWARD"
    else:
        _dir = "REVERSE"
    _motor_side(_in1, _in2, _pwm_l, _l_pct, forward)
    _motor_side(_in3, _in4, _pwm_r, _r_pct, forward)


def set_differential(l_pct, r_pct, l_forward=True, r_forward=True):
    global _dir, _l_pct, _r_pct
    _l_pct = max(0, min(100, int(l_pct)))
    _r_pct = max(0, min(100, int(r_pct)))
    l_forward = bool(l_forward)
    r_forward = bool(r_forward)

    if _l_pct == 0 and _r_pct == 0:
        stop()
        return

    if _tank_split_pwm and l_forward == r_forward:
        set_motors(_l_pct, _r_pct, forward=l_forward)
        return

    if _tank_parallel:
        if l_forward == r_forward:
            set_motors(_l_pct, _r_pct, forward=l_forward)
        elif l_forward and not r_forward:
            turn_left(_l_pct, _r_pct)
        elif not l_forward and r_forward:
            turn_right(_l_pct, _r_pct)
        else:
            stop()
        return

    if l_forward and r_forward:
        _dir = "FORWARD" if _l_pct >= _r_pct else "ARC_FWD"
    elif not l_forward and not r_forward:
        _dir = "REVERSE" if _l_pct >= _r_pct else "ARC_REV"
    else:
        _dir = "DIFF"
    _motor_side(_in1, _in2, _pwm_l, _l_pct, l_forward)
    _motor_side(_in3, _in4, _pwm_r, _r_pct, r_forward)


def turn_left(l_pct=None, r_pct=None):
    """Giro izquierda: rueda izquierda lenta, derecha rapida (misma direccion)."""
    global _dir, _l_pct, _r_pct
    inner = _turn_inner if l_pct is None else l_pct
    outer = _turn_outer if r_pct is None else r_pct
    if _tank_split_pwm:
        _set_tank_split_pwm(inner, outer, forward=True)
        return
    if _tank_parallel:
        print("[motors] LEFT: conecta ENA y ENB a la Pico para PWM por rueda")
        stop()
        _dir = "LEFT"
        return
    _dir = "LEFT"
    _l_pct, _r_pct = inner, outer
    _motor_side(_in1, _in2, _pwm_l, _l_pct, False)
    _motor_side(_in3, _in4, _pwm_r, _r_pct, True)


def turn_right(l_pct=None, r_pct=None):
    """Giro derecha: rueda derecha lenta, izquierda rapida."""
    global _dir, _l_pct, _r_pct
    inner = _turn_inner if r_pct is None else r_pct
    outer = _turn_outer if l_pct is None else l_pct
    if _tank_split_pwm:
        _set_tank_split_pwm(outer, inner, forward=True)
        return
    if _tank_parallel:
        print("[motors] RIGHT: conecta ENA y ENB a la Pico para PWM por rueda")
        stop()
        _dir = "RIGHT"
        return
    _dir = "RIGHT"
    _l_pct, _r_pct = outer, inner
    _motor_side(_in1, _in2, _pwm_l, _l_pct, True)
    _motor_side(_in3, _in4, _pwm_r, _r_pct, False)


def is_tank_parallel():
    return _tank_parallel


def is_tank_split_pwm():
    return _tank_split_pwm


def get_pwm():
    return _l_pct, _r_pct


def stop():
    global _dir, _l_pct, _r_pct
    _dir = "STOP"
    _l_pct = _r_pct = 0
    if _in1:
        _in1.off()
        _in2.off()
    if _in3:
        _in3.off()
        _in4.off()
    if _pwm_l:
        _pwm_l.duty_u16(0)
    if _pwm_r:
        _pwm_r.duty_u16(0)


def get_telemetry():
    return _dir, _l_pct, _r_pct
