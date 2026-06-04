# Decodificacion de mensajes MQTT en topic robot/commands.

import json

import command_handler


def handle_message(raw):
    """raw: bytes o str con JSON de comando."""
    if not raw:
        return False
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        obj = json.loads(raw)
    except (ValueError, TypeError) as e:
        print("[mqtt_cmd] JSON invalido:", e)
        return False
    ok = command_handler.apply_mqtt_payload(obj)
    if ok:
        print("[mqtt_cmd] aplicado:", raw[:80])
    return ok
