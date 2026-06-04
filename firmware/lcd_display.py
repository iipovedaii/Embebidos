# LCD 16x2 HD44780 via backpack I2C PCF8574 (modo 4 bits).
# LEGACY: reemplazado por oled_display.py (SSD1306). No se inicializa en hardware.py.

from machine import I2C, Pin

_lcd = None
_i2c = None
_addr = 0x27
_anim_frame = 0

# Bits del PCF8574: P7-P4 datos, P3 backlight, P2 E, P1 R/W, P0 RS
_BL = 0x08
_EN = 0x04
_RS = 0x01


class LcdI2c:
    def __init__(self, i2c, addr=0x27, cols=16, rows=2):
        self.i2c = i2c
        self.addr = addr
        self.cols = cols
        self.rows = rows
        self._backlight = _BL
        self._init_hw()

    def _write4(self, nibble):
        data = (nibble & 0xF0) | self._backlight
        self.i2c.writeto(self.addr, bytes([data | _EN]))
        self.i2c.writeto(self.addr, bytes([data]))
        data = ((nibble << 4) & 0xF0) | self._backlight
        self.i2c.writeto(self.addr, bytes([data | _EN]))
        self.i2c.writeto(self.addr, bytes([data]))

    def _write_cmd(self, cmd):
        self._write4(cmd & 0xF0)
        self._write4((cmd << 4) & 0xF0)

    def _write_data(self, data):
        self._backlight = _BL
        n = data | _RS
        self._write4(n & 0xF0)
        self._write4((n << 4) & 0xF0)

    def _init_hw(self):
        import time

        time.sleep_ms(50)
        self._write4(0x30)
        time.sleep_ms(5)
        self._write4(0x30)
        time.sleep_ms(1)
        self._write4(0x30)
        time.sleep_ms(1)
        self._write4(0x20)
        time.sleep_ms(1)
        self._write_cmd(0x28)
        self._write_cmd(0x0C)
        self._write_cmd(0x06)
        self.clear()

    def clear(self):
        self._write_cmd(0x01)
        import time

        time.sleep_ms(2)

    def home(self):
        self._write_cmd(0x02)

    def set_cursor(self, col, row):
        addr = 0x80 + (row * 0x40) + col
        self._write_cmd(addr)

    def putstr(self, s):
        for c in s:
            self._write_data(ord(c))

    def print_line(self, row, text):
        text = (text or "")[: self.cols]
        self.set_cursor(0, row)
        self.putstr(text.ljust(self.cols))


_LCD_ADDRS = (0x27, 0x3F)


def init(sda_pin=None, scl_pin=None, addr=0x27, freq=100000, bus=None):
    global _lcd, _i2c, _addr
    _addr = addr
    _lcd = None
    if bus is not None:
        _i2c = bus
    elif sda_pin is not None and scl_pin is not None:
        _i2c = I2C(0, sda=Pin(sda_pin), scl=Pin(scl_pin), freq=freq)
    else:
        print("[lcd] sin bus I2C")
        return False

    try:
        addrs = _i2c.scan()
    except OSError as e:
        print("[lcd] scan I2C fallo:", e)
        return False

    if addr not in addrs:
        for alt in _LCD_ADDRS:
            if alt in addrs:
                addr = alt
                break
        else:
            print("[lcd] 0x{:02X} no encontrado; I2C:".format(_addr), [hex(a) for a in addrs])
            return False

    try:
        _lcd = LcdI2c(_i2c, addr=addr)
        _lcd.print_line(0, "SISEMB listo")
        _lcd.print_line(1, "WiFi/MQTT...")
    except OSError as e:
        print("[lcd] init fallo @ 0x{:02X}:".format(addr), e)
        _lcd = None
        return False

    if sda_pin is not None:
        print("[lcd] I2C SDA=GP{} SCL=GP{} addr=0x{:02X}".format(sda_pin, scl_pin, addr))
    else:
        print("[lcd] I2C compartido addr=0x{:02X}".format(addr))
    return True


def _battery_bar(pct, frame):
    """Barra animada 10 caracteres."""
    width = 10
    fill = int((pct / 100.0) * width)
    fill = max(0, min(width, fill))
    # Pequena animacion: un bloque extra parpadea en el borde
    if fill < width and (frame % 4) < 2:
        fill = min(width, fill + 1)
    filled = "#" * fill
    empty = "-" * (width - len(filled))
    return "[" + filled + empty + "]"


def _arrow_for_direction(direction):
    d = (direction or "STOP").upper()
    arrows = {
        "FORWARD": "^",
        "REVERSE": "v",
        "LEFT": "<",
        "RIGHT": ">",
        "STOP": "#",
    }
    return arrows.get(d, "#")


def update(bat_pct, bat_v, direction, usonic_cm, usonic_zone, frame=0, mearm=None):
    """Refresca las dos lineas del LCD (16 columnas)."""
    global _lcd, _anim_frame
    if _lcd is None:
        return
    _anim_frame = frame
    # L0: porcentaje + mini barra animada (10 celdas)
    bar = _battery_bar(bat_pct, frame)
    head = "B{:3d}%".format(bat_pct)
    line0 = (head + bar)[:16]

    arrow = _arrow_for_direction(direction)
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
    line1 = "{:1s}{:3d}cm {:3s}G{:2d}".format(arrow, cm, zone_abbr, gr)[:16]
    _lcd.print_line(0, line0)
    _lcd.print_line(1, line1)
