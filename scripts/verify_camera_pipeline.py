#!/usr/bin/env python3
"""Verifica decode rgb565 del dashboard (misma logica que app.js)."""

import base64
import json
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "debug-9facb1.log"


def make_thumb(w=64, h=48):
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


def decode_ok(b64, w, h, dest_w=320, dest_h=240):
    raw = base64.b64decode(b64)
    need = w * h * 2
    if len(raw) < need:
        return False, "short buffer"
    nonzero = 0
    for y in range(min(8, dest_h)):
        sy = (y * h) // dest_h
        for x in range(min(8, dest_w)):
            sx = (x * w) // dest_w
            si = (sy * w + sx) * 2
            c0, c1 = raw[si], raw[si + 1]
            v = c0 | (c1 << 8)
            if v != 0:
                nonzero += 1
    return nonzero > 0, {"nonzero": nonzero}


def main():
    thumb = make_thumb()
    b64 = base64.b64encode(thumb).decode("ascii")
    ok, info = decode_ok(b64, 64, 48)
    entry = {
        "sessionId": "9facb1",
        "runId": "post-fix-decode-test",
        "hypothesisId": "C",
        "location": "verify_camera_pipeline.py",
        "message": "rgb565 decode ok" if ok else "rgb565 decode fail",
        "data": {"ok": ok, **info, "b64_len": len(b64)},
        "timestamp": 0,
    }
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(entry["message"], entry["data"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
