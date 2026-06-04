#!/usr/bin/env python3
"""Escucha robot/camera y escribe debug-9facb1.log (NDJSON). Ctrl+C para salir."""

import json
import sys
import time
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent.parent / "debug-9facb1.log"
BROKER = "broker.emqx.io"
PORT = 1883
TOPIC = "robot/camera"
SESSION = "9facb1"
RUN = "pre-fix"


def write_log(hypothesis_id, location, message, data):
    entry = {
        "sessionId": SESSION,
        "runId": RUN,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print("[sniff]", message, data)


def main():
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print("Instala: pip install paho-mqtt")
        sys.exit(1)

    count = 0

    def on_connect(client, userdata, flags, rc, properties=None):
        del userdata, flags, properties
        write_log("C", "mqtt_camera_sniff.py", "connected", {"rc": rc})
        client.subscribe(TOPIC)

    def on_message(client, userdata, msg):
        del client, userdata
        nonlocal count
        count += 1
        raw = msg.payload.decode("utf-8", errors="replace")
        try:
            obj = json.loads(raw)
        except ValueError as e:
            write_log("C", "mqtt_camera_sniff.py", "bad json", {"err": str(e), "raw_len": len(raw)})
            return
        write_log(
            "C",
            "mqtt_camera_sniff.py",
            "camera message",
            {
                "n": count,
                "format": obj.get("format"),
                "source": obj.get("source"),
                "w": obj.get("width"),
                "h": obj.get("height"),
                "b64_len": len(obj.get("data", "")),
                "frame_id": obj.get("frame_id"),
                "dbg": obj.get("dbg"),
                "msg_bytes": len(raw),
            },
        )

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sniff-cam-9facb1")
    c.on_connect = on_connect
    c.on_message = on_message
    write_log("C", "mqtt_camera_sniff.py", "starting", {"broker": BROKER, "topic": TOPIC})
    c.connect(BROKER, PORT, 60)
    c.loop_forever()


if __name__ == "__main__":
    main()
