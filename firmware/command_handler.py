# API unificada: conduccion (IR/MQTT) + MeArm (IR/MQTT).
# Ultimo comando aplicado gana; STOP detiene motores al instante.

import time

DEFAULT_PWM = 70

# Codigos NEC (hex) → comando
_IR_HEX_MAP = {
    0xFF30CF: "STOP_EMERGENCIA",
    0xFF18E7: "FWD",
    0xFF4AB5: "REV",
    0xFF10EF: "LEFT",
    0xFF5AA5: "RIGHT",
    0xFF38C7: "GRIPPER_OPEN",
    0xFF22DD: "GRIPPER_CLOSE",
    0xFFA25D: "MODE_AUTO",
}

_TEXT_MAP = {
    "FWD": "FORWARD",
    "FORWARD": "FORWARD",
    "REV": "REVERSE",
    "REVERSE": "REVERSE",
    "BACK": "REVERSE",
    "BACKWARD": "REVERSE",
    "LEFT": "LEFT",
    "RIGHT": "RIGHT",
    "STOP": "STOP",
    "STOP_EMERGENCIA": "STOP",
    "HALT": "STOP",
    "IDLE": "STOP",
}

_MEARM_TEXT = frozenset({
    "GRIPPER_OPEN",
    "GRIPPER_CLOSE",
    "MODE_AUTO",
    "HOME_POSITION",
    "HOME",
    "ELBOW_UP",
    "ELBOW_DOWN",
})

# Maniobras con 4 motores (IN3/IN4 en Pico) — reservado si dejas de usar modo tanque
_MANEUVER_DIFF_MAP = {
    "FR45": (70, 35, True, True),
    "FL45": (35, 70, True, True),
    "RR45": (70, 35, False, False),
    "RL45": (35, 70, False, False),
    "FR90": (55, 55, False, True),
    "FL90": (55, 55, True, False),
    "BR90": (55, 55, True, False),
    "BL90": (55, 55, False, True),
}

# Modo tanque (IN3/IN4 puenteados): fases pivot + avance/retroceso por angulo/distancia
# pivot: gira sobre el eje (LEFT/RIGHT)
# drive: recto FORWARD/REVERSE tras el giro (maniobras 45°)
_MANEUVER_TANK = {
  # 90°: solo giro in situ
    "FR90": [("pivot", "RIGHT", 90)],
    "FL90": [("pivot", "LEFT", 90)],
    "BR90": [("pivot", "LEFT", 90)],
    "BL90": [("pivot", "RIGHT", 90)],
    "RR90": [("pivot", "RIGHT", 90)],
    "RL90": [("pivot", "LEFT", 90)],
  # 45°: gira 45° y avanza/retrocede una distancia calibrada
  # Nomenclatura: FR/FL = delantero-derecha/izquierda, RR/RL = trasero-derecha/izquierda
  # Para ir al trasero-derecho (RR/BR): pivota IZQUIERDA y marcha atrás
  # Para ir al trasero-izquierdo (RL/BL): pivota DERECHA y marcha atrás
    "FR45": [("pivot", "RIGHT", 45), ("drive", "FORWARD")],
    "FL45": [("pivot", "LEFT",  45), ("drive", "FORWARD")],
    "RR45": [("pivot", "LEFT",  45), ("drive", "REVERSE")],
    "RL45": [("pivot", "RIGHT", 45), ("drive", "REVERSE")],
    "BR45": [("pivot", "LEFT",  45), ("drive", "REVERSE")],
    "BL45": [("pivot", "RIGHT", 45), ("drive", "REVERSE")],
}

_direction = "STOP"
_l_pwm = 0
_r_pwm = 0
_last_ir_code = "0x000000"
_last_ir_cmd = "NONE"
_last_ir_ts = 0
_last_source = "none"

# Maniobra por fases (modo tanque)
_maneuver_label = ""
_maneuver_phases = []
_maneuver_phase_idx = 0
_maneuver_phase_until_ms = 0
_maneuver_pwm = DEFAULT_PWM

# Calibracion open-loop (ajusta en config.py)
_ms_per_deg = 10
_drive_45_ms = 550
_use_tank_maneuvers = True


def _parse_pwm(data, default=DEFAULT_PWM):
    l = data.get("l_pwm", data.get("motor_l_pwm", default))
    r = data.get("r_pwm", data.get("motor_r_pwm", default))
    try:
        l = int(l)
        r = int(r)
    except (TypeError, ValueError):
        l = r = default
    return max(0, min(100, l)), max(0, min(100, r))


def _is_tank_mode():
    try:
        import motors_l298n
        return bool(getattr(motors_l298n, "_tank_parallel", True))
    except Exception:
        return True


def _cancel_maneuver():
    global _maneuver_phases, _maneuver_phase_idx, _maneuver_phase_until_ms, _maneuver_label
    _maneuver_phases = []
    _maneuver_phase_idx = 0
    _maneuver_phase_until_ms = 0
    _maneuver_label = ""


def _phase_duration_ms(phase):
    kind = phase[0]
    if kind == "pivot":
        deg = int(phase[2])
        return max(80, deg * _ms_per_deg)
    if kind == "drive":
        return _drive_45_ms
    return 400


def _run_phase(phase):
    import motors_l298n

    kind = phase[0]
    pwm = _maneuver_pwm
    if kind == "pivot":
        turn = phase[1]
        inner = max(22, int(pwm * 0.4))
        outer = pwm
        if turn == "LEFT":
            motors_l298n.turn_left(inner, outer)
            return "LEFT"
        motors_l298n.turn_right(inner, outer)
        return "RIGHT"
    if kind == "drive":
        direction = phase[1]
        if direction == "REVERSE":
            motors_l298n.set_motors(pwm, pwm, forward=False)
            return "REVERSE"
        motors_l298n.set_motors(pwm, pwm, forward=True)
        return "FORWARD"
    return "STOP"


def _start_maneuver_phase(idx):
    global _maneuver_phase_idx, _maneuver_phase_until_ms, _direction, _l_pwm, _r_pwm
    if idx >= len(_maneuver_phases):
        _cancel_maneuver()
        _apply_direction("STOP", source="maneuver_done")
        return
    phase = _maneuver_phases[idx]
    _maneuver_phase_idx = idx
    dur = _phase_duration_ms(phase)
    _maneuver_phase_until_ms = time.ticks_add(time.ticks_ms(), dur)
    sub = _run_phase(phase)
    _direction = _maneuver_label if idx == 0 else "{}:{}".format(_maneuver_label, sub)
    import motors_l298n

    _l_pwm, _r_pwm = motors_l298n.get_pwm()


def _apply_maneuver_tank(code, source="mqtt"):
    global _maneuver_label, _maneuver_phases, _last_source
    key = str(code).upper().strip()
    phases = _MANEUVER_TANK.get(key)
    if not phases:
        return False
    _last_source = source
    _maneuver_label = key
    _maneuver_phases = list(phases)
    _start_maneuver_phase(0)
    return True


def _apply_direction(direction, l_pwm=None, r_pwm=None, source="mqtt"):
    global _direction, _l_pwm, _r_pwm, _last_source
    import motors_l298n

    _cancel_maneuver()
    direction = (direction or "STOP").upper()
    l_pwm = DEFAULT_PWM if l_pwm is None else l_pwm
    r_pwm = DEFAULT_PWM if r_pwm is None else r_pwm
    l_pwm, r_pwm = _parse_pwm({"l_pwm": l_pwm, "r_pwm": r_pwm}, DEFAULT_PWM)

    _last_source = source

    if direction == "STOP":
        motors_l298n.stop()
        _direction, _l_pwm, _r_pwm = "STOP", 0, 0
        return True

    if direction == "FORWARD":
        motors_l298n.set_motors(l_pwm, r_pwm, forward=True)
    elif direction == "REVERSE":
        motors_l298n.set_motors(l_pwm, r_pwm, forward=False)
    elif direction == "LEFT":
        # Si llegan l/r por comando, usarlos para giro rapido (inner=min, outer=max).
        inner = min(l_pwm, r_pwm)
        outer = max(l_pwm, r_pwm)
        motors_l298n.turn_left(inner, outer)
        l_pwm, r_pwm = motors_l298n.get_pwm()
    elif direction == "RIGHT":
        # Si llegan l/r por comando, usarlos para giro rapido (inner=min, outer=max).
        inner = min(l_pwm, r_pwm)
        outer = max(l_pwm, r_pwm)
        motors_l298n.turn_right(outer, inner)
        l_pwm, r_pwm = motors_l298n.get_pwm()
    else:
        return False

    _direction = direction
    _l_pwm, _r_pwm = l_pwm, r_pwm
    return True


def _apply_diff(l_pwm, r_pwm, l_fwd=True, r_fwd=True, label="DIFF", source="mqtt"):
    global _direction, _l_pwm, _r_pwm, _last_source
    import motors_l298n

    _cancel_maneuver()
    l_pwm, r_pwm = _parse_pwm({"l_pwm": l_pwm, "r_pwm": r_pwm}, DEFAULT_PWM)
    _last_source = source
    motors_l298n.set_differential(l_pwm, r_pwm, bool(l_fwd), bool(r_fwd))
    _direction = label
    _l_pwm, _r_pwm = l_pwm, r_pwm
    return True


def _apply_maneuver_diff(code, source="mqtt"):
    key = str(code).upper().strip()
    spec = _MANEUVER_DIFF_MAP.get(key)
    if not spec:
        return False
    l_pwm, r_pwm, l_fwd, r_fwd = spec
    return _apply_diff(l_pwm, r_pwm, l_fwd, r_fwd, label=key, source=source)


def _apply_maneuver(code, source="mqtt"):
    if _use_tank_maneuvers and _is_tank_mode():
        return _apply_maneuver_tank(code, source=source)
    return _apply_maneuver_diff(code, source=source)


def tick_drive(now_ms=None):
    """Avanza fases de maniobra (pivot N° + avance) y para al terminar."""
    global _maneuver_phase_idx
    if not _maneuver_phases:
        return
    now_ms = time.ticks_ms() if now_ms is None else now_ms
    if time.ticks_diff(now_ms, _maneuver_phase_until_ms) < 0:
        return
    nxt = _maneuver_phase_idx + 1
    if nxt < len(_maneuver_phases):
        _start_maneuver_phase(nxt)
    else:
        _cancel_maneuver()
        _apply_direction("STOP", source="maneuver_done")


def bind_config(cfg=None):
    global _ms_per_deg, _drive_45_ms, _maneuver_pwm, _use_tank_maneuvers
    if cfg is None:
        return
    _ms_per_deg = int(getattr(cfg, "MANEUVER_MS_PER_DEG", 10))
    _drive_45_ms = int(getattr(cfg, "MANEUVER_DRIVE_MS", 550))
    _maneuver_pwm = int(getattr(cfg, "MANEUVER_PWM", DEFAULT_PWM))
    _use_tank_maneuvers = bool(getattr(cfg, "MOTOR_TANK_PARALLEL", True))


def _apply_mearm_text(cmd, source="mqtt"):
    import mearm_controller
    return mearm_controller.handle_cmd(cmd)


def apply_text_cmd(cmd, l_pwm=None, r_pwm=None, source="mqtt"):
    """Aplica comando textual (motores o MeArm)."""
    if not cmd:
        return False
    key = str(cmd).upper().strip()

    if key in _MEARM_TEXT:
        return _apply_mearm_text(key, source)

    if key in _MANEUVER_TANK or key in _MANEUVER_DIFF_MAP:
        return _apply_maneuver(key, source=source)

    if key in _TEXT_MAP:
        direction = _TEXT_MAP[key]
        if direction == "STOP":
            return _apply_direction("STOP", source=source)
        return _apply_direction(direction, l_pwm, r_pwm, source=source)

    return False


def apply_ir_code(code_hex, mapped_cmd=None):
    global _last_ir_code, _last_ir_cmd, _last_ir_ts

    if isinstance(code_hex, str):
        try:
            code = int(code_hex, 16)
        except ValueError:
            return False
        code_str = code_hex.upper()
    else:
        code = int(code_hex)
        code_str = "0x{:06X}".format(code & 0xFFFFFF)

    cmd = mapped_cmd or _IR_HEX_MAP.get(code & 0xFFFFFF, "NONE")
    _last_ir_code = code_str
    _last_ir_cmd = cmd
    _last_ir_ts = time.ticks_ms()

    if cmd == "NONE":
        return False
    return apply_text_cmd(cmd, source="ir")


def apply_mqtt_payload(obj):
    """Parsea dict JSON de robot/commands."""
    if not obj or not isinstance(obj, dict):
        return False

    if "mearm" in obj:
        import mearm_controller
        if mearm_controller.apply_mqtt_mearm(obj["mearm"]):
            return True

    if "cmd" in obj:
        cmd = str(obj["cmd"]).upper().strip()
        if cmd == "DIFF":
            return _apply_diff(
                obj.get("l_pwm", DEFAULT_PWM),
                obj.get("r_pwm", DEFAULT_PWM),
                obj.get("l_fwd", True),
                obj.get("r_fwd", True),
                label="DIFF",
                source="mqtt",
            )
        return apply_text_cmd(
            obj["cmd"],
            obj.get("l_pwm"),
            obj.get("r_pwm"),
            source="mqtt",
        )

    drive = obj.get("drive")
    if isinstance(drive, dict):
        direction = drive.get("direction", drive.get("dir", "STOP"))
        return _apply_direction(
            _TEXT_MAP.get(str(direction).upper(), direction),
            drive.get("motor_l_pwm", drive.get("l_pwm")),
            drive.get("motor_r_pwm", drive.get("r_pwm")),
            source="mqtt",
        )

    if "direction" in obj:
        return _apply_direction(
            _TEXT_MAP.get(str(obj["direction"]).upper(), obj["direction"]),
            obj.get("motor_l_pwm", obj.get("l_pwm")),
            obj.get("motor_r_pwm", obj.get("r_pwm")),
            source="mqtt",
        )

    return False


def get_drive_telemetry():
    import motors_l298n

    return {
        "direction": _direction,
        "motor_l_pwm": _l_pwm,
        "motor_r_pwm": _r_pwm,
        "tank_parallel": motors_l298n.is_tank_parallel(),
        "tank_split_pwm": motors_l298n.is_tank_split_pwm(),
        "ms_per_deg": _ms_per_deg,
        "maneuver_drive_ms": _drive_45_ms,
    }


def get_ir_telemetry():
    return _last_ir_code, _last_ir_cmd, _last_ir_ts


def get_last_source():
    return _last_source
