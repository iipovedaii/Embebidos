# color_analysis.py — Histograma rgb565 por umbrales RGB (misma lógica que frontend/vision_color.js)

COLOR_RANGES = {
    "RED": ((120, 0, 0), (255, 100, 100)),
    "ORANGE": ((160, 60, 0), (255, 180, 90)),
    "YELLOW": ((120, 120, 0), (255, 255, 120)),
    "GREEN": ((0, 90, 0), (120, 255, 120)),
    "CYAN": ((0, 120, 120), (120, 255, 255)),
    "BLUE": ((0, 0, 90), (100, 120, 255)),
    "MAGENTA": ((120, 0, 120), (255, 100, 255)),
    "WHITE": ((170, 170, 170), (255, 255, 255)),
    "BLACK": ((0, 0, 0), (55, 55, 55)),
}

COLOR_ORDER = (
    "RED",
    "ORANGE",
    "YELLOW",
    "GREEN",
    "CYAN",
    "BLUE",
    "MAGENTA",
    "WHITE",
    "BLACK",
)

TARGET_MIN_PCT = 8
ANALYSIS_TOP_N = 4


def _rgb565_pixel(frame_bytes, w, x, y):
    i = (y * w + x) * 2
    v = frame_bytes[i] | (frame_bytes[i + 1] << 8)
    r = ((v >> 11) & 0x1F) << 3
    g = ((v >> 5) & 0x3F) << 2
    b = (v & 0x1F) << 3
    return r, g, b


def _in_range(r, g, b, mn, mx):
    return mn[0] <= r <= mx[0] and mn[1] <= g <= mx[1] and mn[2] <= b <= mx[2]


def _fit_score(r, g, b, mn, mx):
    s = 0.0
    for i in range(3):
        mid = (mn[i] + mx[i]) * 0.5
        half = max((mx[i] - mn[i]) * 0.5, 1.0)
        s += abs(r - mid) / half
    return s


def _classify_pixel(r, g, b):
    best = None
    best_score = 1e9
    for name in COLOR_ORDER:
        mn, mx = COLOR_RANGES[name]
        if not _in_range(r, g, b, mn, mx):
            continue
        sc = _fit_score(r, g, b, mn, mx)
        if sc < best_score:
            best_score = sc
            best = name
    return best if best else "BLACK"


def analyze_rgb565(frame_bytes, w, h, display_w=320, display_h=240):
    """
    Devuelve (target_detected, vx, vy, dominant, analysis_list).
    Porcentajes en analysis suman ~100 entre los top N.
    """
    if not frame_bytes or w < 2 or h < 2:
        return False, display_w // 2, display_h // 2, "UNKNOWN", []

    total = w * h
    counts = {c: 0 for c in COLOR_ORDER}
    cent_x = {c: 0 for c in COLOR_ORDER}
    cent_y = {c: 0 for c in COLOR_ORDER}

    for y in range(h):
        for x in range(w):
            r, g, b = _rgb565_pixel(frame_bytes, w, x, y)
            color = _classify_pixel(r, g, b)
            counts[color] += 1
            cent_x[color] += x
            cent_y[color] += y

    ranked = []
    for color in COLOR_ORDER:
        n = counts[color]
        if n <= 0:
            continue
        ranked.append((color, int(round((n / total) * 100)), n))

    ranked.sort(key=lambda t: t[1], reverse=True)
    if not ranked:
        return False, display_w // 2, display_h // 2, "BLACK", [{"color": "BLACK", "pct": 100}]

    analysis = [{"color": ranked[i][0], "pct": ranked[i][1]} for i in range(min(ANALYSIS_TOP_N, len(ranked)))]
    sum_pct = sum(a["pct"] for a in analysis)
    if analysis and sum_pct != 100:
        analysis[0]["pct"] = max(0, analysis[0]["pct"] + (100 - sum_pct))

    dominant = ranked[0][0]
    dom_pct = ranked[0][1]
    dn = ranked[0][2]

    vx = display_w // 2
    vy = display_h // 2
    if dn > 0:
        vx = int((cent_x[dominant] / dn) * display_w / w)
        vy = int((cent_y[dominant] / dn) * display_h / h)

    detected = dom_pct >= TARGET_MIN_PCT and dominant != "BLACK" and dn > 0
    return detected, vx, vy, dominant, analysis


def analyze_thumbnail(frame_bytes, thumb_w=80, thumb_h=60):
    """Analiza thumbnail ya reducido (p. ej. el de camera_stream)."""
    return analyze_rgb565(frame_bytes, thumb_w, thumb_h)
