# SISEMB - Generador del payload de telemetria.
#
# Con HARDWARE_ENABLED=True lee bateria, ultrasonido, drive, MeArm e IR reales.
# Sin datos de camara: vision en estado neutro (sin simulacion).

import time

USONIC_MIN_CM = 2
USONIC_MAX_CM = 400

_VISION_IDLE = (False, 160, 120, "UNKNOWN", [])
_USONIC_IDLE = (0.0, False, "OUT_OF_RANGE")
_BATTERY_IDLE = (0, 0.0)
_MEARM_IDLE = ("IDLE", 90, 70, 110, 50, "WAITING")
_IR_IDLE = ("0x000000", "NONE", 0)

_uptime0_ms = time.ticks_ms()
_hw = False
_cfg = None


def bind_hardware(enabled, cfg_module=None):
    global _hw, _cfg
    _hw = bool(enabled)
    _cfg = cfg_module


def _read_battery():
    if _hw and _cfg:
        try:
            import battery
            import hardware_pins as pins

            return battery.read_smoothed(
                pins.BATTERY_ADC_PIN,
                _cfg.BATTERY_DIVIDER_RATIO,
                _cfg.BATTERY_V_MIN,
                _cfg.BATTERY_V_MAX,
                vref=getattr(_cfg, "BATTERY_VREF", 3.3),
                calib_scale=getattr(_cfg, "BATTERY_CALIB_SCALE", 1.0),
            )
        except Exception as e:
            print("[battery]", e)
    return _BATTERY_IDLE


def _read_wifi_rssi():
    try:
        import wifi_manager

        return wifi_manager.get_rssi(-99)
    except Exception:
        return -99


def _read_drive():
    if _hw:
        try:
            import command_handler

            return command_handler.get_drive_telemetry()
        except Exception as e:
            print("[drive]", e)
    return {
        "direction": "STOP",
        "motor_l_pwm": 0,
        "motor_r_pwm": 0,
        "tank_parallel": True,
        "tank_split_pwm": False,
        "ms_per_deg": 18,
        "maneuver_drive_ms": 950,
    }


def _read_mearm(t_sec):
    del t_sec
    if _hw:
        try:
            import mearm_controller

            return mearm_controller.get_telemetry()
        except Exception as e:
            print("[mearm]", e)
    return _MEARM_IDLE


def _read_vision_from_camera():
    if not _hw or not _cfg:
        return None
    if not getattr(_cfg, "TELEMETRY_VISION_ENABLED", True):
        return None
    try:
        import ov7670
        import camera_stream

        if ov7670.is_stub_mode():
            return None
        # Cache llenada en capture_and_pack (misma captura que robot/camera).
        return camera_stream.get_cached_vision()
    except Exception as e:
        print("[vision]", e)
    return None


def _read_vision(t_sec):
    del t_sec
    cam = _read_vision_from_camera()
    if cam:
        return cam
    return _VISION_IDLE


def _read_ultrasonic(t_sec):
    del t_sec
    if _hw:
        try:
            import hcsr04

            return hcsr04.read(USONIC_MIN_CM, USONIC_MAX_CM)
        except Exception as e:
            print("[usonic]", e)
    return _USONIC_IDLE


def _read_ir(t_ms):
    if _hw:
        try:
            import command_handler

            return command_handler.get_ir_telemetry()
        except Exception as e:
            print("[ir]", e)
    return _IR_IDLE


def build_payload(t_ms):
    """Construye el dict JSON para el broker."""
    t_sec = time.ticks_diff(t_ms, _uptime0_ms) / 1000.0
    if t_sec < 0:
        t_sec = 0.0

    bat_pct, bat_v = _read_battery()
    rssi = _read_wifi_rssi()
    drive_t = _read_drive()
    if not isinstance(drive_t, dict):
        drive_t = {
            "direction": "STOP",
            "motor_l_pwm": 0,
            "motor_r_pwm": 0,
        }
    direction = drive_t.get("direction", "STOP")
    l_pwm = drive_t.get("motor_l_pwm", 0)
    r_pwm = drive_t.get("motor_r_pwm", 0)
    mearm_t = _read_mearm(t_sec)
    if isinstance(mearm_t, dict):
        status = mearm_t.get("status", "IDLE")
        servos = mearm_t.get("servos", {})
        action = mearm_t.get("last_action", "WAITING")
        mearm_hw_ok = mearm_t.get("hardware_ok", False)
        mearm_servo_pins = mearm_t.get("servo_pins", {})
    else:
        status, base, shoulder, elbow, gripper, action = mearm_t
        servos = {
            "base": base,
            "shoulder": shoulder,
            "elbow": elbow,
            "gripper": gripper,
        }
        mearm_hw_ok = False
        mearm_servo_pins = {}
    tgt_det, vx, vy, dom, analysis = _read_vision(t_sec)
    ir_code, ir_cmd, ir_ts = _read_ir(t_ms)
    usonic_cm, usonic_valid, usonic_zone = _read_ultrasonic(t_sec)

    camera_status = {"ready": False, "stub": True, "source": "none"}
    if _hw:
        try:
            import ov7670

            if getattr(_cfg, "CAMERA_ENABLED", False):
                camera_status = ov7670.get_status()
                camera_status["source"] = (
                    "ov7670_stub" if camera_status.get("stub") else "ov7670"
                )
        except Exception:
            pass

    return {
        "system": {
            "battery_pct": bat_pct,
            "battery_v": bat_v,
            "wifi_rssi": rssi,
            "uptime_sec": int(t_sec),
        },
        "mearm": {
            "status": status,
            "servos": servos,
            "last_action": action,
            "hardware_ok": mearm_hw_ok,
            "servo_pins": mearm_servo_pins,
        },
        "drive": drive_t,
        "vision": {
            "target_detected": tgt_det,
            "target_coords": {"x": vx, "y": vy},
            "dominant_color": dom,
            "analysis": analysis,
        },
        "ir_sensor": {
            "last_raw_code": ir_code,
            "mapped_command": ir_cmd,
            "timestamp_ms": ir_ts,
        },
        "ultrasonic": {
            "distance_cm": usonic_cm,
            "object_detected": usonic_valid,
            "zone": usonic_zone,
            "min_cm": USONIC_MIN_CM,
            "max_cm": USONIC_MAX_CM,
        },
        "camera": camera_status,
    }
