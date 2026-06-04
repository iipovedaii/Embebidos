#!/usr/bin/env python3
"""Publica un frame rgb565 de prueba en robot/camera y registra en debug-9facb1.log."""

import base64
import json
import struct
import time
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "debug-9facb1.log"
BROKER = "broker.emqx.io"
PORT = 1883
TOPIC = "robot/camera"
SESSION = "9facb1"


def _make_rgb565_thumb(w=64, h=48):
    buf = bytearray(w * h * 2)
    for y in range(h):
        for x in range(w):
            r5 = ((x * 31) // max(w - 1, 1)) & 0x1F
            g6 = ((y * 63) // max(h - 1, 1)) & 0x3F
            b5 = (((x + y) * 11) // 32) & 0x1F
            v = (r5 << 11) | (g6 << 5) | b5
            i = (y * w + x) * 2
            buf[i] = v & 0xFF
            buf[i + 1] = (v >> 8) & 0xFF
    return bytes(buf)


def log(hypothesis_id, message, data):
    entry = {
        "sessionId": SESSION,
        "runId": "post-fix-publish-test",
        "hypothesisId": hypothesis_id,
        "location": "publish_test_camera_frame.py",
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(message, data)


def main():
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print("pip install paho-mqtt")
        return 1

    thumb = _make_rgb565_thumb()
    payload = {
        "format": "rgb565",
        "width": 64,
        "height": 48,
        "data": base64.b64encode(thumb).decode("ascii"),
        "ts": int(time.time() * 1000),
        "source": "ov7670_stub",
        "frame_id": 9999,
        "dbg": {"test": True},
    }
    msg = json.dumps(payload)
    log("C", "payload built", {"bytes": len(msg), "b64_len": len(payload["data"])})

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test-pub-cam")
    c.connect(BROKER, PORT, 60)
    c.publish(TOPIC, msg, qos=0, retain=False)
    c.disconnect()
    log("C", "published test frame", {"topic": TOPIC, "bytes": len(msg)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
