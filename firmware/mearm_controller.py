# Brazo MeArm · 4 servos con PWM directo desde GPIO de la Pico 2W.

import time

try:
    from machine import Pin, PWM
except ImportError:
    Pin = PWM = None

JOINTS = ("base", "shoulder", "elbow", "gripper")
_DEFAULT_PINS = {"base": 17, "shoulder": 18, "elbow": 20, "gripper": 21}
_DEFAULT_HOME = {"base": 90, "shoulder": 70, "elbow": 110, "gripper": 50}
_GRIPPER_OPEN = 25
_GRIPPER_CLOSE = 155
_SCAN_DELTA = 12
_SERVO_FREQ_HZ = 50
_SERVO_PERIOD_US = 20000

_pins = dict(_DEFAULT_PINS)
_pwms = {}
_home = dict(_DEFAULT_HOME)
_angles = dict(_DEFAULT_HOME)
_limits = {j: (0, 180) for j in JOINTS}
_status = "IDLE"
_last_action = "HOME_POSITION"
_servo_min_us = 500
_servo_max_us = 2500
_invert = {"base": False, "shoulder": False, "elbow": False, "gripper": False}
_disabled = {"base": False, "shoulder": False, "elbow": False, "gripper": False}
_enabled = False
_moving_until = 0
_hold_refresh_ms = 300
_last_hold_ms = 0


def maintain_hold(now_ms=None):
    """Reenvía PWM periódicamente para que los servos mantengan torque."""
    global _last_hold_ms
    if not _enabled:
        return
    now_ms = time.ticks_ms() if now_ms is None else now_ms
    if time.ticks_diff(now_ms, _last_hold_ms) < _hold_refresh_ms:
        return
    _last_hold_ms = now_ms
    for joint in JOINTS:
        if not _disabled.get(joint):
            _write_servo(joint)


def _clamp_angle(joint, angle):
    lo, hi = _limits.get(joint, (0, 180))
    return max(lo, min(hi, int(angle)))


def _hw_angle(joint, angle):
    """Ángulo lógico (dashboard) → PWM físico."""
    if _invert.get(joint):
        lo, hi = _limits.get(joint, (0, 180))
        return hi + lo - int(angle)
    return int(angle)


def _angle_to_us(joint, angle):
    lo, hi = _limits.get(joint, (0, 180))
    span = max(1, hi - lo)
    hw = _hw_angle(joint, angle)
    pos = max(0, min(span, hw - lo))
    return int(_servo_min_us + (((_servo_max_us - _servo_min_us) * pos) // span))


def _write_servo(joint):
    if _disabled.get(joint):
        return
    pwm = _pwms.get(joint)
    if pwm is None:
        return
    pulse_us = _angle_to_us(joint, _angles[joint])
    duty = int((pulse_us * 65535) // _SERVO_PERIOD_US)
    pwm.duty_u16(max(0, min(65535, duty)))


def _apply_hw():
    global _status, _moving_until
    if not _enabled:
        return
    for joint in JOINTS:
        if not _disabled.get(joint):
            _write_servo(joint)
    _status = "ACTIVE"
    _moving_until = time.ticks_add(time.ticks_ms(), 400)


def _touch_idle():
    global _status
    if time.ticks_diff(time.ticks_ms(), _moving_until) > 0:
        _status = "IDLE"


def init(cfg=None):
    """Inicializa PWM directo para los 4 servos del MeArm."""
    global _pins, _pwms, _limits, _servo_min_us, _servo_max_us, _invert, _disabled, _enabled, _home
    global _angles, _last_action, _status

    deinit()
    if cfg:
        _pins = dict(getattr(cfg, "MEARM_SERVO_PINS", _DEFAULT_PINS))
        _servo_min_us = getattr(cfg, "MEARM_SERVO_MIN_US", 500)
        _servo_max_us = getattr(cfg, "MEARM_SERVO_MAX_US", 2500)
        inv = getattr(cfg, "MEARM_SERVO_INVERT", None)
        if isinstance(inv, dict):
            for j in JOINTS:
                _invert[j] = bool(inv.get(j, _invert.get(j, False)))
        dis = getattr(cfg, "MEARM_SERVO_DISABLE", None)
        if isinstance(dis, dict):
            for j in JOINTS:
                _disabled[j] = bool(dis.get(j, _disabled.get(j, False)))
        for joint in JOINTS:
            lim = getattr(cfg, "MEARM_LIMITS", {}).get(joint)
            if lim and len(lim) >= 2:
                _limits[joint] = (int(lim[0]), int(lim[1]))
        home = getattr(cfg, "MEARM_HOME", None)
        if home:
            for j in JOINTS:
                if j in home:
                    _home[j] = _clamp_angle(j, home[j])
                    _angles[j] = _clamp_angle(j, home[j])

    _enabled = False
    _last_action = "HOME_POSITION"
    _status = "IDLE"
    if Pin is None or PWM is None:
        print("[mearm] PWM no disponible (deshabilitado)")
        return False

    try:
        for joint in JOINTS:
            if _disabled.get(joint):
                print("[mearm] {} GP{} DESHABILITADO (sin PWM)".format(joint, _pins.get(joint)))
                continue
            gpio = int(_pins.get(joint))
            pin = Pin(gpio, Pin.OUT)
            pwm = PWM(pin)
            pwm.freq(_SERVO_FREQ_HZ)
            _pwms[joint] = pwm
        _enabled = True
        home_position()
        inv_on = [j for j in JOINTS if _invert.get(j)]
        off = [j for j in JOINTS if _disabled.get(j)]
        print("[mearm] PWM GPIO", _pins, "invert", inv_on or "ninguno", "off", off or "ninguno")
        for j in JOINTS:
            us = _angle_to_us(j, _angles[j])
            print("[mearm] {} GP{} -> {}us".format(j, _pins.get(j), us))
        return True
    except Exception as e:
        print("[mearm] init PWM fallo:", e)
        deinit()
        return False


def deinit():
    """Libera PWM de servos; útil al reconfigurar desde REPL."""
    global _pwms, _enabled
    for pwm in _pwms.values():
        try:
            pwm.deinit()
        except Exception:
            pass
    _pwms = {}
    _enabled = False


def set_joint(joint, angle, action=None):
    joint = str(joint).lower()
    if joint not in JOINTS:
        return False
    global _last_action
    _angles[joint] = _clamp_angle(joint, angle)
    if action:
        _last_action = action
    else:
        _last_action = "SET_{}".format(joint.upper())
    _apply_hw()
    return True


def set_servos(servo_map, action=None):
    if not servo_map or not isinstance(servo_map, dict):
        return False
    global _last_action
    ok = False
    for joint, angle in servo_map.items():
        j = str(joint).lower()
        if j in JOINTS:
            _angles[j] = _clamp_angle(j, angle)
            ok = True
    if not ok:
        return False
    _last_action = action or "SET_SERVOS"
    _apply_hw()
    return True


def nudge_joint(joint, delta):
    joint = str(joint).lower()
    if joint not in JOINTS:
        return False
    return set_joint(joint, _angles[joint] + int(delta), "NUDGE_{}".format(joint.upper()))


def open_gripper():
    return set_joint("gripper", _GRIPPER_OPEN, "GRIPPER_OPEN")


def close_gripper():
    return set_joint("gripper", _GRIPPER_CLOSE, "GRIPPER_CLOSE")


def home_position():
    return set_servos(dict(_home), "HOME_POSITION")


def scan_step():
    """Incrementa base (preset SCAN / MODE_AUTO por IR)."""
    return nudge_joint("base", _SCAN_DELTA) or set_joint("base", _angles["base"], "SCAN_AREA")


def handle_cmd(cmd):
    """Comandos textuales (IR / MQTT cmd)."""
    key = str(cmd or "").upper().strip()
    if key == "GRIPPER_OPEN":
        return open_gripper()
    if key == "GRIPPER_CLOSE":
        return close_gripper()
    if key == "ELBOW_UP":
        return nudge_joint("elbow", 5)
    if key == "ELBOW_DOWN":
        return nudge_joint("elbow", -5)
    if key == "MODE_AUTO":
        return scan_step()
    if key == "HOME_POSITION" or key == "HOME":
        return home_position()
    return False


def apply_mqtt_mearm(obj):
    """Bloque JSON bajo clave 'mearm'."""
    if not obj or not isinstance(obj, dict):
        return False

    if "servos" in obj and isinstance(obj["servos"], dict):
        return set_servos(obj["servos"], obj.get("action"))

    joint = obj.get("joint")
    if joint:
        if "angle" in obj:
            return set_joint(joint, obj["angle"], obj.get("action"))
        if "delta" in obj:
            return nudge_joint(joint, obj["delta"])
    return False


def test_joint(joint, lo=None, hi=None, step=15, pause_ms=400):
    """REPL: barrido manual de un servo para diagnosticar cable/GPIO."""
    joint = str(joint).lower()
    if joint not in JOINTS or not _enabled:
        print("[mearm] test_joint: servo no listo:", joint)
        return False
    lim = _limits.get(joint, (0, 180))
    lo = int(lo if lo is not None else lim[0])
    hi = int(hi if hi is not None else lim[1])
    print("[mearm] test {} GP{} {}..{}".format(joint, _pins.get(joint), lo, hi))
    for angle in range(lo, hi + 1, max(1, int(step))):
        set_joint(joint, angle, "TEST_{}".format(joint.upper()))
        print("[mearm]  {} -> {}° ({}us)".format(joint, angle, _angle_to_us(joint, angle)))
        time.sleep_ms(pause_ms)
    set_joint(joint, _home.get(joint, 90), "TEST_DONE")
    return True


def is_hardware_enabled():
    return _enabled and bool(_pwms)


def get_pins():
    return dict(_pins)


def get_telemetry():
    _touch_idle()
    maintain_hold()
    return {
        "status": _status,
        "servos": dict(_angles),
        "last_action": _last_action,
        "hardware_ok": is_hardware_enabled(),
        "servo_pins": get_pins(),
        "invert": dict(_invert),
        "limits": {j: list(_limits[j]) for j in JOINTS},
        "home": dict(_home),
        "gripper_open": _GRIPPER_OPEN,
        "gripper_close": _GRIPPER_CLOSE,
    }
