# Empaquetado de frames OV7670 para MQTT (JPEG base64 o RGB565 thumbnail).

import gc
import time

try:
    import ubinascii
except ImportError:
    import binascii as ubinascii

try:
    import micropython
except ImportError:
    micropython = None

# Thumbnail al broker (pequeno = menos RAM/JSON; subir solo si sobra memoria).
_THUMB_W = 48
_THUMB_H = 36


def _thumb_size():
    try:
        import config

        return (
            int(getattr(config, "CAMERA_THUMB_W", _THUMB_W)),
            int(getattr(config, "CAMERA_THUMB_H", _THUMB_H)),
        )
    except ImportError:
        return _THUMB_W, _THUMB_H

# Buffers preasignados (se reasignan si cambia el tamano)
_thumb_buf = bytearray(_THUMB_W * _THUMB_H * 2)
_thumb_w = _THUMB_W
_thumb_h = _THUMB_H

# Vision analizada en la misma captura que robot/camera (telemetria lee cache)
_cached_vision = None
_cached_vision_ms = 0


def _get_thumb_buf(tw, th):
    global _thumb_buf, _thumb_w, _thumb_h
    n = tw * th * 2
    if len(_thumb_buf) < n:
        _thumb_buf = bytearray(n)
    _thumb_w, _thumb_h = tw, th
    return _thumb_buf


if micropython is not None:

    @micropython.viper
    def _downsample_avg_2x2(src, dst, sw: int, sh: int, tw: int, th: int):
        """Downsample con promedio 2x2 RGB565 (sw=2*tw, sh=2*th).
        Promediar 4 pixels reduce aliasing y se ve mucho mejor que nearest.
        """
        s = ptr8(src)
        d = ptr8(dst)
        y: int = 0
        while y < th:
            sy: int = y * 2
            x: int = 0
            while x < tw:
                sx: int = x * 2
                # 4 indices de pixel rgb565 (2 bytes c/u)
                i0: int = ((sy * sw) + sx) << 1
                i1: int = ((sy * sw) + sx + 1) << 1
                i2: int = (((sy + 1) * sw) + sx) << 1
                i3: int = (((sy + 1) * sw) + sx + 1) << 1
                # rgb565 little-endian (byte_order = le)
                p0: int = int(s[i0]) | (int(s[i0 + 1]) << 8)
                p1: int = int(s[i1]) | (int(s[i1 + 1]) << 8)
                p2: int = int(s[i2]) | (int(s[i2 + 1]) << 8)
                p3: int = int(s[i3]) | (int(s[i3 + 1]) << 8)
                r: int = (((p0 >> 11) & 31) + ((p1 >> 11) & 31) + ((p2 >> 11) & 31) + ((p3 >> 11) & 31)) >> 2
                g: int = (((p0 >> 5) & 63) + ((p1 >> 5) & 63) + ((p2 >> 5) & 63) + ((p3 >> 5) & 63)) >> 2
                b: int = ((p0 & 31) + (p1 & 31) + (p2 & 31) + (p3 & 31)) >> 2
                v: int = (r << 11) | (g << 5) | b
                oi: int = ((y * tw) + x) << 1
                d[oi] = v & 0xFF
                d[oi + 1] = (v >> 8) & 0xFF
                x = x + 1
            y = y + 1
else:
    _downsample_avg_2x2 = None


def _downsample_rgb565(src, sw, sh, tw, th):
    needed = sw * sh * 2
    if len(src) < needed:
        return None
    out = _get_thumb_buf(tw, th)
    # viper necesita objetos con interfaz buffer (bytes/bytearray/memoryview)
    if _downsample_avg_2x2 is not None and sw == tw * 2 and sh == th * 2:
        try:
            _downsample_avg_2x2(src, out, sw, sh, tw, th)
            return out
        except Exception as e:
            print("[camera] viper downsample fallo:", e)
    # Fallback nearest neighbor
    for y in range(th):
        sy = (y * sh) // th
        for x in range(tw):
            sx = (x * sw) // tw
            si = (sy * sw + sx) * 2
            oi = (y * tw + x) * 2
            out[oi] = src[si]
            out[oi + 1] = src[si + 1]
    return out


def _rgb565_to_jpeg_minimal(rgb565, w, h):
    return None


def get_cached_vision():
    """Ultimo analisis de color (sin nueva captura). None si expiro o no hay."""
    global _cached_vision, _cached_vision_ms
    if _cached_vision is None:
        return None
    try:
        import config

        if not getattr(config, "TELEMETRY_VISION_ENABLED", True):
            return None
        stale_ms = int(getattr(config, "CAMERA_VISION_STALE_MS", 20000))
    except ImportError:
        stale_ms = 20000
    if stale_ms > 0 and time.ticks_diff(time.ticks_ms(), _cached_vision_ms) > stale_ms:
        return None
    return _cached_vision


def _update_vision_cache(thumb, tw, th):
    """Analiza colores sobre thumbnail ya generado (48x36, bajo costo RAM)."""
    global _cached_vision, _cached_vision_ms
    try:
        import config

        if not getattr(config, "TELEMETRY_VISION_ENABLED", True):
            return
    except ImportError:
        pass
    try:
        import color_analysis

        _cached_vision = color_analysis.analyze_rgb565(thumb, tw, th)
        _cached_vision_ms = time.ticks_ms()
    except Exception as e:
        print("[vision] analyze:", e)


def _pack_thumb_payload(thumb, tw, th, ts_ms=None, prefer_jpeg=True, source="ov7670"):
    if not thumb:
        return None
    gc.collect()
    ts = ts_ms if ts_ms is not None else time.ticks_ms()
    n = tw * th * 2

    jpeg = None
    if prefer_jpeg:
        jpeg = _rgb565_to_jpeg_minimal(thumb, tw, th)

    if jpeg:
        b64 = ubinascii.b2a_base64(jpeg).decode().strip()
        return {
            "format": "jpeg",
            "width": tw,
            "height": th,
            "data": b64,
            "ts": ts,
            "source": source,
        }

    if isinstance(thumb, (bytes, bytearray)):
        thumb_bytes = bytes(thumb) if isinstance(thumb, bytearray) else thumb
        if len(thumb_bytes) > n:
            thumb_bytes = thumb_bytes[:n]
    else:
        thumb_bytes = bytes(thumb[:n])
    b64 = ubinascii.b2a_base64(thumb_bytes).decode().strip()
    del thumb_bytes
    gc.collect()
    return {
        "format": "rgb565",
        "byte_order": "le",
        "width": tw,
        "height": th,
        "data": b64,
        "ts": ts,
        "source": source,
    }


def pack_mqtt_payload(frame_w, frame_h, rgb565, ts_ms=None, prefer_jpeg=True, source="ov7670"):
    if not rgb565:
        return None
    expected = frame_w * frame_h * 2
    if len(rgb565) < expected:
        print("[camera] frame parcial:", len(rgb565), "/", expected)
        return None

    max_tw, max_th = _thumb_size()
    if frame_w <= max_tw and frame_h <= max_th:
        tw, th = frame_w, frame_h
        thumb = rgb565
    else:
        tw = min(max_tw, frame_w)
        th = min(max_th, frame_h)
        thumb = _downsample_rgb565(rgb565, frame_w, frame_h, tw, th)
        if thumb is None:
            return None
    return _pack_thumb_payload(thumb, tw, th, ts_ms=ts_ms, prefer_jpeg=prefer_jpeg, source=source)


def capture_and_pack(frame_id=0, prefer_jpeg=True):
    import ov7670

    gc.collect()
    t0 = time.ticks_ms()
    cap = ov7670.capture_frame(frame_id)
    cap_ms = time.ticks_diff(time.ticks_ms(), t0)
    if not cap:
        try:
            import debug_cam

            debug_cam.log(
                "A",
                "camera_stream.py:capture_and_pack",
                "no frame from ov7670",
                {"frame_id": frame_id, "cap_ms": cap_ms, "stub": ov7670.is_stub_mode()},
            )
        except Exception:
            pass
        return None
    w, h, raw = cap
    src = "ov7670_stub" if ov7670.is_stub_mode() else "ov7670"
    max_tw, max_th = _thumb_size()
    if w <= max_tw and h <= max_th:
        tw, th = w, h
        thumb = raw
    else:
        tw = min(max_tw, w)
        th = min(max_th, h)
        thumb = _downsample_rgb565(raw, w, h, tw, th)
        if thumb is None:
            return None
    _update_vision_cache(thumb, tw, th)
    payload = _pack_thumb_payload(thumb, tw, th, prefer_jpeg=prefer_jpeg, source=src)
    if payload is not None:
        payload["frame_id"] = int(frame_id)
        try:
            import debug_cam

            dbg = debug_cam.dbg_dict(
                cap_ms=cap_ms,
                stub=ov7670.is_stub_mode(),
                b64_len=len(payload.get("data", "")),
                format=payload.get("format"),
                w=payload.get("width"),
                h=payload.get("height"),
            )
            if dbg:
                payload.update(dbg)
            debug_cam.log(
                "B",
                "camera_stream.py:capture_and_pack",
                "payload packed",
                {
                    "frame_id": frame_id,
                    "source": src,
                    "cap_ms": cap_ms,
                    "b64_len": len(payload.get("data", "")),
                    "format": payload.get("format"),
                },
            )
        except Exception:
            pass
    return payload
