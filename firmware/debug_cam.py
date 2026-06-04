# Instrumentacion debug OV7670 -> MQTT -> dashboard (sesion 9facb1).
# En la Pico solo imprime; el dashboard y mqtt_camera_sniff escriben debug-9facb1.log.

import time

_ENABLED = False
_RUN = "post-fix"


def _refresh_enabled():
    global _ENABLED
    try:
        import config

        _ENABLED = bool(getattr(config, "CAMERA_DEBUG", False))
    except ImportError:
        pass


def log(hypothesis_id, location, message, data=None):
    _refresh_enabled()
    if not _ENABLED:
        return
    payload = {
        "sessionId": "9facb1",
        "runId": _RUN,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": time.ticks_ms(),
    }
    try:
        import json

        print("[DBG_CAM]", json.dumps(payload))
    except Exception:
        print("[DBG_CAM]", hypothesis_id, location, message, data)


def dbg_dict(**kwargs):
    _refresh_enabled()
    if not _ENABLED:
        return {}
    return {"dbg": kwargs}
