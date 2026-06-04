# OLED SSD1306 / SH1106 128x64 (I2C) — reemplaza LCD 16x2.
# Bus compartido GP4/GP5 con OV7670 SCCB (0x3C vs 0x21).

from micropython import const

import i2c_bus

_oled = None
_i2c = None
_addr = 0x3C
_w = 128
_h = 64
_col_offset = 0
_anim_frame = 0
_team_short = "G3"
_team_name = "Grupo 3"

_OLED_ADDRS = (0x3C, 0x3D)

_SET_CONTRAST = const(0x81)
_SET_ENTIRE_ON = const(0xA4)
_SET_NOR = const(0xA6)
_SET_DISP = const(0xAE)
_SET_MEM_ADDR = const(0x20)
_SET_COL_ADDR = const(0x21)
_SET_PAGE_ADDR = const(0x22)
_SET_DISP_START_LINE = const(0x40)
_SET_SEG_REMAP = const(0xA1)
_SET_MUX_RATIO = const(0xA8)
_SET_COM_OUT_DIR = const(0xC8)
_SET_DISP_OFFSET = const(0xD3)
_SET_CLK_DIV = const(0xD5)
_SET_PRECHARGE = const(0xD9)
_SET_VCOM_DESEL = const(0xDB)
_SET_CHARGE_PUMP = const(0x8D)


class SSD1306_I2C:
    def __init__(self, i2c, addr, width=128, height=64, col_offset=0):
        import framebuf

        self.i2c = i2c
        self.addr = addr
        self.width = width
        self.height = height
        self.col_offset = col_offset
        self.pages = height // 8
        self.buffer = bytearray(self.pages * width)
        self.framebuf = framebuf.FrameBuffer(
            self.buffer, width, height, framebuf.MONO_VLSB
        )
        self._init_hw()
        self.poweron()
        self.fill(0)
        self.show()

    def _write_cmd(self, cmd):
        i2c_bus.lock()
        try:
            self.i2c.writeto(self.addr, b"\x80" + bytes([cmd]))
        finally:
            i2c_bus.unlock()

    def _write_data(self, buf):
        i2c_bus.lock()
        try:
            chunk = 16
            for i in range(0, len(buf), chunk):
                self.i2c.writeto(self.addr, b"\x40" + buf[i : i + chunk])
        finally:
            i2c_bus.unlock()

    def _init_hw(self):
        import time

        for cmd in (
            _SET_DISP,
            _SET_MEM_ADDR,
            0x00,
            _SET_SEG_REMAP,
            _SET_COM_OUT_DIR,
            _SET_DISP_START_LINE,
            _SET_MUX_RATIO,
            self.height - 1,
            _SET_DISP_OFFSET,
            0x00,
            _SET_CLK_DIV,
            0x80,
            _SET_PRECHARGE,
            0xF1,
            _SET_VCOM_DESEL,
            0x40,
            _SET_ENTIRE_ON,
            _SET_NOR,
            _SET_CONTRAST,
            0xCF,
            _SET_CHARGE_PUMP,
            0x14,
        ):
            self._write_cmd(cmd)
        time.sleep_ms(50)

    def poweron(self):
        self._write_cmd(_SET_DISP | 0x01)

    def poweroff(self):
        self._write_cmd(_SET_DISP)

    def fill(self, col):
        self.framebuf.fill(col)

    def text(self, s, x, y, col=1):
        self.framebuf.text(s, x, y, col)

    def fill_rect(self, x, y, w, h, col):
        self.framebuf.fill_rect(x, y, w, h, col)

    def show(self):
        """Envío página a página (evita patrón tipo QR por burst incorrecto)."""
        co = self.col_offset
        w = self.width
        for page in range(self.pages):
            self._write_cmd(0xB0 | page)
            self._write_cmd(0x00 | (co & 0x0F))
            self._write_cmd(0x10 | ((co >> 4) & 0x0F))
            start = page * w
            self._write_data(self.buffer[start : start + w])


def _driver_col_offset(cfg):
    driver = "ssd1306"
    if cfg is not None:
        driver = str(getattr(cfg, "OLED_DRIVER", "ssd1306")).lower()
    if driver in ("sh1106", "sh1107"):
        off = getattr(cfg, "OLED_COL_OFFSET", 2) if cfg else 2
        return int(off)
    if cfg is not None:
        return int(getattr(cfg, "OLED_COL_OFFSET", 0))
    return 0


def init(sda_pin=None, scl_pin=None, addr=0x3C, freq=100000, bus=None, width=128, height=64, cfg=None):
    global _oled, _i2c, _addr, _w, _h, _col_offset, _team_short, _team_name
    if cfg is not None:
        _team_name = getattr(cfg, "TEAM_NAME", "Grupo 3")
        _team_short = getattr(cfg, "TEAM_SHORT", "G3")
        if isinstance(_team_short, bytes):
            _team_short = _team_short.decode()
        _team_short = str(_team_short)[:10]
    _addr = addr
    _w = width
    _h = height
    _col_offset = _driver_col_offset(cfg)
    _oled = None

    if bus is not None:
        _i2c = bus
    elif sda_pin is not None and scl_pin is not None:
        _i2c = i2c_bus.get_bus(sda_pin, scl_pin, freq)
    else:
        print("[oled] sin bus I2C")
        return False

    try:
        addrs = i2c_bus.scan(_i2c)
    except OSError as e:
        print("[oled] scan I2C fallo:", e)
        return False

    if addr not in addrs:
        for alt in _OLED_ADDRS:
            if alt in addrs:
                addr = alt
                break
        else:
            print("[oled] 0x{:02X} no encontrado; I2C:".format(_addr), [hex(a) for a in addrs])
            return False

    try:
        _oled = SSD1306_I2C(_i2c, addr, width=width, height=height, col_offset=_col_offset)
        _oled.fill(0)
        _oled.text(_team_short, 0, 0, 1)
        _oled.text("OLED OK", 0, 12, 1)
        _oled.text("SUB broker", 0, 24, 1)
        _oled.text("espera...", 0, 36, 1)
        _oled.show()
    except OSError as e:
        print("[oled] init fallo @ 0x{:02X}:".format(addr), e)
        _oled = None
        return False

    driver = "ssd1306"
    if cfg is not None:
        driver = getattr(cfg, "OLED_DRIVER", "ssd1306")
    if sda_pin is not None:
        print(
            "[oled] {} SDA=GP{} SCL=GP{} addr=0x{:02X} {}x{} off={}".format(
                driver, sda_pin, scl_pin, addr, width, height, _col_offset
            )
        )
    else:
        print("[oled] {} addr=0x{:02X} {}x{} off={}".format(driver, addr, width, height, _col_offset))
    return True


def _battery_bar(pct, frame, x, y, w=100, h=8):
    if _oled is None:
        return
    fill = int((pct / 100.0) * w)
    fill = max(0, min(w, fill))
    if fill < w and (frame % 4) < 2:
        fill = min(w, fill + 2)
    _oled.fill_rect(x, y, w, h, 0)
    _oled.framebuf.hline(x, y, w, 1)
    _oled.framebuf.hline(x, y + h - 1, w, 1)
    _oled.framebuf.vline(x, y, h, 1)
    _oled.framebuf.vline(x + w - 1, y, h, 1)
    if fill > 0:
        _oled.fill_rect(x + 1, y + 1, max(0, fill - 2), h - 2, 1)


def _arrow_for_direction(direction):
    d = (direction or "STOP").upper()
    return {
        "FORWARD": "^ FWD",
        "FWD": "^ FWD",
        "REVERSE": "v REV",
        "REV": "v REV",
        "LEFT": "< LFT",
        "RIGHT": "> RGT",
        "STOP": "# STP",
    }.get(d, "# STP")


def update(bat_pct, bat_v, direction, usonic_cm, usonic_zone, frame=0, mearm=None, broker_ok=False):
    """Refresca pantalla OLED 128x64 con telemetria resumida."""
    global _oled, _anim_frame
    if _oled is None:
        return
    _anim_frame = frame

    zone_abbr = {
        "CRITICAL": "CRT",
        "WARNING": "WRN",
        "OK": "OK",
        "CLEAR": "CLR",
        "OUT_OF_RANGE": "OOR",
    }.get((usonic_zone or "").upper(), "---")

    try:
        cm = int(float(usonic_cm))
    except (TypeError, ValueError):
        cm = 0

    gr = 0
    if mearm and isinstance(mearm, dict):
        servos = mearm.get("servos") or {}
        try:
            gr = int(servos.get("gripper", 0))
        except (TypeError, ValueError):
            gr = 0

    try:
        v = float(bat_v)
    except (TypeError, ValueError):
        v = 0.0

    try:
        _oled.fill(0)
        _oled.text(_team_short, 0, 0, 1)
        _oled.text("SUB" if broker_ok else "NO-SUB", 88, 0, 1)
        _oled.text("B{:3d}% {:.1f}V".format(int(bat_pct), v)[:16], 0, 10, 1)
        _battery_bar(bat_pct, frame, 0, 20, 120, 8)
        _oled.text(_arrow_for_direction(direction), 0, 32, 1)
        _oled.text("US{:3d} {:3s}".format(cm, zone_abbr)[:16], 0, 44, 1)
        _oled.text("G{:3d}".format(gr), 90, 44, 1)
        _oled.show()
    except OSError as e:
        print("[oled] update:", e)
