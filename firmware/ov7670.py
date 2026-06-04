# OV7670 · SCCB + captura paralela (esqueleto → captura real)
#
# I2C compartido GP4/5 con OLED. Direccion SCCB tipica: 0x21.
# Resolucion objetivo: QQVGA 160x120 RGB565 (bajo FPS en main).

import time

try:
    from machine import I2C, Pin, PWM
except ImportError:
    I2C = Pin = PWM = None

# Reset + RGB565 QQVGA (160x120). Basado en Linux ov7670 + Adafruit OV7670.
_REG_RESET = ((0x12, 0x80),)  # COM7 soft reset

_REG_RGB565_QQVGA = (
    (0x12, 0x00),  # COM7 limpio (sin color bar ni formatos viejos)
    (0x8C, 0x00),  # RGB444 desactivado
    (0x40, 0xD0),  # COM15 RGB565 + rango 0-255 (0xC0|0x10)
    (0x12, 0x04),  # COM7 salida RGB (COM7_COLORBAR=0)
    (0x0C, 0x04),  # COM3 DCW enable (QQVGA)
    (0x3E, 0x1A),  # COM14 escala QQVGA
    (0x72, 0x22),  # SCALING_DCWCTR
    (0x73, 0xF2),  # SCALING_PCLK_DIV
    (0xA2, 0x02),  # SCALING_PCLK_DELAY
    (0x70, 0x3A),  # SCALING_XSC (sin test pattern en bit7)
    (0x71, 0x35),  # SCALING_YSC
    (0x42, 0x00),  # COM17: quitar color bar DSP (default 0x08 lo activa)
    (0x15, 0x00),  # COM10
    # CLKRC: prescaler /32 -> PCLK = XCLK/32 (~250 kHz con XCLK 8 MHz).
    # Necesario porque MicroPython no alcanza a PCLK alto en polling.
    (0x11, 0x1F),  # CLKRC prescaler maximo
    (0x0F, 0x4A),  # COM6
    (0x3A, 0x04),  # TSLB
    (0x3D, 0xC0),  # COM13 gamma + UV sat
)

_i2c = None
_ready = False
_last_frame = None
_width = 160
_height = 120
_use_stub = True
_sccb_addr = None
_pio_ready = False
_last_capture_ms = 0
_OV7670_ADDR_CANDIDATES = (0x21, 0x60)


def _find_sccb_addr(bus, preferred):
    addrs = list(_OV7670_ADDR_CANDIDATES)
    if preferred not in addrs:
        addrs.insert(0, preferred)
    try:
        found = set(bus.scan())
    except Exception:
        return None
    for a in addrs:
        if a in found:
            return a
    return None


def _sccb_write(addr, reg, val):
    """SCCB write: addr+W, reg, val, STOP. Una sola transaccion."""
    global _i2c
    if _i2c is None:
        return False
    try:
        _i2c.writeto(addr, bytes((reg, val)))
        return True
    except OSError:
        return False


def _sccb_read(addr, reg):
    """SCCB read: la OV7670 NO soporta repeated-START.
    Hay que hacer dos transacciones separadas:
       1) addr+W, reg, STOP
       2) addr+R, leer 1 byte, STOP
    """
    if _i2c is None:
        return None
    try:
        _i2c.writeto(addr, bytes((reg,)))
    except OSError:
        return None
    time.sleep_us(100)
    try:
        return _i2c.readfrom(addr, 1)[0]
    except OSError:
        return None


def _disable_test_patterns(addr):
    """Apaga color bar COM7/COM17 y test pattern en SCALING_XSC/YSC (bit 7)."""
    com17 = _sccb_read(addr, 0x42)
    if com17 is not None:
        _sccb_write(addr, 0x42, com17 & ~0x08)
    com7 = _sccb_read(addr, 0x12)
    if com7 is not None:
        _sccb_write(addr, 0x12, com7 & ~0x02)  # COM7_COLORBAR
    xsc = _sccb_read(addr, 0x70)
    ysc = _sccb_read(addr, 0x71)
    if xsc is not None:
        _sccb_write(addr, 0x70, xsc & 0x7F)
    if ysc is not None:
        _sccb_write(addr, 0x71, ysc & 0x7F)


def _apply_qqvga_window(addr):
    """Ventana 160x120 (Adafruit OV7670_SIZE_DIV4)."""
    vstart, hstart, edge, delay = 11, 186, 2, 2
    vstop = vstart + 480
    hstop = (hstart + 640) % 784
    _sccb_write(addr, 0x17, hstart >> 3)
    _sccb_write(addr, 0x18, hstop >> 3)
    _sccb_write(addr, 0x32, (edge << 6) | ((hstop & 7) << 3) | (hstart & 7))
    _sccb_write(addr, 0x19, vstart >> 2)
    _sccb_write(addr, 0x1A, vstop >> 2)
    _sccb_write(addr, 0x03, ((vstop & 3) << 2) | (vstart & 3))
    _sccb_write(addr, 0xA2, delay)


def _init_sccb(sda_pin, scl_pin, addr, freq):
    global _i2c, _sccb_addr
    if I2C is None:
        return False
    try:
        import i2c_bus

        _i2c = i2c_bus.get_bus(sda_pin, scl_pin, freq)
    except Exception:
        _i2c = I2C(0, sda=Pin(sda_pin), scl=Pin(scl_pin), freq=freq)
    detected = _find_sccb_addr(_i2c, addr)
    if detected is None:
        try:
            scan = ["0x{:02x}".format(a) for a in _i2c.scan()]
        except Exception:
            scan = []
        print("[ov7670] OV7670 no en I2C; visto:", scan)
        return False
    addr = detected
    _sccb_addr = addr

    # 1) Soft reset SCCB (COM7=0x80) y espera larga
    _sccb_write(addr, 0x12, 0x80)
    time.sleep_ms(150)

    # 2) Verifica identidad del chip (PID=0x76, VER=0x73/0x76; MIDH=0x7F, MIDL=0xA2)
    pid = ver = midh = midl = None
    for attempt in range(4):
        pid = _sccb_read(addr, 0x0A)
        ver = _sccb_read(addr, 0x0B)
        midh = _sccb_read(addr, 0x1C)
        midl = _sccb_read(addr, 0x1D)
        print(
            "[ov7670] intento {} PID=0x{:02x} VER=0x{:02x} MIDH=0x{:02x} MIDL=0x{:02x}".format(
                attempt + 1, pid or 0, ver or 0, midh or 0, midl or 0
            )
        )
        if pid == 0x76:
            break
        time.sleep_ms(60)

    if pid != 0x76:
        if midh == 0x7F and midl == 0xA2:
            print("[ov7670] MID Omnivision OK pero PID raro; continuo de todas formas")
        else:
            print("[ov7670] chip no identificado como OV7670 (PID esperado 0x76)")
            print("[ov7670] Si MID=0x7F/0xA2 falta, modulo distinto o SDA/SCL ruidosos")
            return False

    # 3) Configuracion completa Adafruit/GerardoMunoz (COM10 VS_NEG, RGB565, 80x60)
    import ov7670_registers as oreg

    try:
        import config as _cfg

        size_div = int(getattr(_cfg, "CAMERA_SIZE_DIV", oreg.SIZE_DIV8))
    except ImportError:
        size_div = oreg.SIZE_DIV8

    wh = oreg.apply_all(
        lambda r, v: _sccb_write(addr, r, v),
        lambda r: _sccb_read(addr, r),
        size_div=size_div,
    )
    global _width, _height
    _width, _height = wh
    print("[ov7670] resolucion sensor {}x{}".format(_width, _height))

    # 4) Verifica registros clave (lectura)
    com7 = _sccb_read(addr, 0x12)
    com15 = _sccb_read(addr, 0x40)
    com17 = _sccb_read(addr, 0x42)
    print(
        "[ov7670] verificacion COM7=0x{:02x} COM15=0x{:02x} COM17=0x{:02x}".format(
            com7 or 0, com15 or 0, com17 or 0
        )
    )
    if com17 is not None and (com17 & 0x08):
        print("[ov7670] AVISO: COM17 aun tiene color bar")
    return True


_reset_pin = None
_pwdn_pin = None
_data_pins_in = ()
_vsync_in = None
_href_in = None
_pclk_in = None


_pwdn_obj = None
_reset_obj = None


def _power_pwdn(active):
    """active=True -> cámara encendida (PWDN LOW); active=False -> sleep (PWDN HIGH)."""
    if _pwdn_obj is None:
        return
    _pwdn_obj.value(0 if active else 1)


def _pulse_reset():
    if _reset_obj is None:
        return
    _reset_obj.value(1)
    time.sleep_ms(5)
    _reset_obj.value(0)
    time.sleep_ms(10)
    _reset_obj.value(1)
    time.sleep_ms(50)


def _setup_power_pins(reset_pin, pwdn_pin):
    """RST y PWDN deben ir a GPIO o estar fijados (no flotantes)."""
    global _reset_pin, _pwdn_pin, _pwdn_obj, _reset_obj
    if Pin is None:
        return

    _reset_pin = reset_pin
    _pwdn_pin = pwdn_pin

    if pwdn_pin is not None:
        _pwdn_obj = Pin(pwdn_pin, Pin.OUT, value=1)
        print("[ov7670] PWDN GP{} configurado (HIGH=sleep, LOW=on)".format(pwdn_pin))
    else:
        _pwdn_obj = None
        print("[ov7670] PWDN sin GPIO; cablear a GND")

    if reset_pin is not None:
        _reset_obj = Pin(reset_pin, Pin.OUT, value=1)
        print("[ov7670] RESET GP{} configurado".format(reset_pin))
    else:
        _reset_obj = None
        print("[ov7670] RESET sin GPIO; cablear pull-up 10k a 3.3V")


_GPIO_IN_ADDR = 0xD0000004  # RP2040/RP2350 SIO_BASE + GPIO_IN
_PCLK_BIT = 0
_HREF_BIT = 0
_VSYNC_BIT = 0
_DATA_PINS_TUPLE = ()


def _setup_data_gpio(data_pins, vsync, href, pclk):
    """Configura pines como input. La lectura usa GPIO_IN entero (mem32)."""
    global _data_pins_in, _vsync_in, _href_in, _pclk_in
    global _PCLK_BIT, _HREF_BIT, _VSYNC_BIT, _DATA_PINS_TUPLE
    if Pin is None:
        return
    _data_pins_in = tuple(Pin(p, Pin.IN) for p in data_pins)
    _vsync_in = Pin(vsync, Pin.IN)
    _href_in = Pin(href, Pin.IN)
    _pclk_in = Pin(pclk, Pin.IN)
    _DATA_PINS_TUPLE = tuple(data_pins)
    _PCLK_BIT = 1 << pclk
    _HREF_BIT = 1 << href
    _VSYNC_BIT = 1 << vsync


def _gpio_read():
    """Lectura atomica de los 32 GPIO."""
    try:
        from machine import mem32

        return mem32[_GPIO_IN_ADDR]
    except Exception:
        v = 0
        for i, p in enumerate(_data_pins_in):
            if p.value():
                v |= 1 << _DATA_PINS_TUPLE[i]
        if _vsync_in and _vsync_in.value():
            v |= _VSYNC_BIT
        if _href_in and _href_in.value():
            v |= _HREF_BIT
        if _pclk_in and _pclk_in.value():
            v |= _PCLK_BIT
        return v


def _decode_data_byte(gpio_word):
    """D0=GP0, D1=GP1, D2-D7=GP7-GP12. Decodifica desde una palabra GPIO_IN."""
    # bits 0,1 directos; bits 7-12 -> 2-7 del byte (>>5 + mask 0xFC)
    return (gpio_word & 0x03) | ((gpio_word >> 5) & 0xFC)


def _setup_xclk(pin, freq_hz=10_000_000):
    if PWM is None:
        return
    try:
        pwm = PWM(Pin(pin))
        pwm.freq(freq_hz)
        pwm.duty_u16(32768)
        print("[ov7670] XCLK GP{} @ {} Hz".format(pin, freq_hz))
    except Exception as e:
        print("[ov7670] XCLK:", e)


def _capture_parallel_stub(w, h, frame_id=0):
    """Patron RGB565 de prueba (sustituye lectura PIO hasta cableado real)."""
    buf = bytearray(w * h * 2)
    fid = frame_id & 0xFF
    for y in range(h):
        for x in range(w):
            r5 = ((x * 31) // max(w - 1, 1) + fid) & 0x1F
            g6 = ((y * 63) // max(h - 1, 1)) & 0x3F
            b5 = (((x + y + fid) * 17) // 32) & 0x1F
            v = (r5 << 11) | (g6 << 5) | b5
            i = (y * w + x) * 2
            buf[i] = v & 0xFF
            buf[i + 1] = (v >> 8) & 0xFF
    return bytes(buf)


_capture_fail_reason = None
_capture_fail_logged = False


def _set_fail(reason):
    global _capture_fail_reason, _capture_fail_logged
    _capture_fail_reason = reason
    if not _capture_fail_logged:
        print("[ov7670] captura fallo:", reason)
        _capture_fail_logged = True


def _capture_parallel_real(w, h, data_pins, vsync, href, pclk):
    """Captura RGB565 leyendo GPIO_IN completo (mem32) por polling."""
    if Pin is None:
        return None
    if not _data_pins_in or _vsync_in is None:
        _setup_data_gpio(data_pins, vsync, href, pclk)

    try:
        from machine import mem32
    except ImportError:
        _set_fail("sin mem32")
        return None

    pclk_bit = _PCLK_BIT
    href_bit = _HREF_BIT
    vsync_bit = _VSYNC_BIT

    # VSYNC con COM10=VS_NEG (igual que driver GerardoMunoz PIO): wait 0 luego 1
    t_end = time.ticks_add(time.ticks_ms(), 1200)
    while mem32[_GPIO_IN_ADDR] & vsync_bit:
        if time.ticks_diff(time.ticks_ms(), t_end) > 0:
            break
    while not (mem32[_GPIO_IN_ADDR] & vsync_bit):
        if time.ticks_diff(time.ticks_ms(), t_end) > 0:
            _set_fail("VSYNC nunca sube (COM10/reloj XCLK?)")
            return None

    buf = bytearray(w * h * 2)
    idx = 0
    lost_lines = 0

    for _y in range(h):
        t_row = time.ticks_add(time.ticks_ms(), 300)
        while not (mem32[_GPIO_IN_ADDR] & href_bit):
            if time.ticks_diff(time.ticks_ms(), t_row) > 0:
                _set_fail("HREF nunca sube en linea {} (cable HREF GP27?)".format(_y))
                lost_lines += 1
                break
        if lost_lines > 0:
            break

        pixels = 0
        while pixels < w:
            v = mem32[_GPIO_IN_ADDR]
            if not (v & href_bit):
                break

            while not (mem32[_GPIO_IN_ADDR] & pclk_bit):
                if not (mem32[_GPIO_IN_ADDR] & href_bit):
                    break
            v = mem32[_GPIO_IN_ADDR]
            hi = (v & 0x03) | ((v >> 5) & 0xFC)
            while mem32[_GPIO_IN_ADDR] & pclk_bit:
                pass

            while not (mem32[_GPIO_IN_ADDR] & pclk_bit):
                if not (mem32[_GPIO_IN_ADDR] & href_bit):
                    break
            v = mem32[_GPIO_IN_ADDR]
            lo = (v & 0x03) | ((v >> 5) & 0xFC)
            while mem32[_GPIO_IN_ADDR] & pclk_bit:
                pass

            if idx + 1 < len(buf):
                buf[idx] = hi
                buf[idx + 1] = lo
                idx += 2
            pixels += 1

    if idx == 0:
        _set_fail("captura sin pixeles (PCLK no oscila? cable GP28?)")
        return None
    global _capture_fail_logged
    _capture_fail_logged = False
    return bytes(buf[:idx])


def init(cfg, pins_mod):
    """Inicializa SCCB, GPIO paralelo y XCLK."""
    global _ready, _use_stub, _width, _height

    if not getattr(cfg, "CAMERA_ENABLED", False):
        print("[ov7670] deshabilitada en config")
        return False

    _width = int(getattr(cfg, "CAMERA_WIDTH", 160))
    _height = int(getattr(cfg, "CAMERA_HEIGHT", 120))

    force_stub = bool(getattr(cfg, "CAMERA_FORCE_STUB", False))
    sccb_ok = False
    sda = getattr(cfg, "I2C_SDA_PIN", pins_mod.I2C_SDA_PIN)
    scl = getattr(cfg, "I2C_SCL_PIN", pins_mod.I2C_SCL_PIN)
    addr = getattr(cfg, "OV7670_I2C_ADDR", pins_mod.OV7670_I2C_ADDR)
    freq = getattr(cfg, "I2C_FREQ", 100000)

    if not force_stub:
        import i2c_bus

        reset_gpio = getattr(cfg, "CAM_RESET_PIN", pins_mod.CAM_RESET)
        pwdn_gpio = getattr(cfg, "CAM_PWDN_PIN", pins_mod.CAM_PWDN)

        # 1) Configura pines (PWDN arranca HIGH = sleep)
        _setup_power_pins(reset_gpio, pwdn_gpio)
        time.sleep_ms(20)

        # 2) Arranca XCLK ANTES de encender la cámara (necesario para SCCB)
        xclk_hz = int(getattr(cfg, "CAMERA_XCLK_HZ", 8_000_000))
        _setup_xclk(pins_mod.CAM_XCLK, xclk_hz)
        time.sleep_ms(20)

        # 3) Enciende la cámara (PWDN LOW) y haz reset
        _power_pwdn(True)
        time.sleep_ms(50)
        _pulse_reset()
        time.sleep_ms(100)

        bus = i2c_bus.get_bus(sda, scl, freq)

        # 4) Escanea I2C varias veces (la primera puede fallar)
        detected = None
        for attempt in range(5):
            try:
                scan = sorted(bus.scan())
            except Exception as e:
                scan = []
                print("[ov7670] scan I2C error:", e)
            scan_hex = ["0x{:02x}".format(a) for a in scan]
            print("[ov7670] scan I2C intento {}: {}".format(attempt + 1, scan_hex))
            detected = _find_sccb_addr(bus, addr)
            if detected is not None:
                break
            time.sleep_ms(80)

        if detected is not None:
            print("[ov7670] sensor detectado en 0x{:02x}".format(detected))
            _setup_data_gpio(
                pins_mod.CAM_DATA_PINS,
                pins_mod.CAM_VSYNC,
                pins_mod.CAM_HREF,
                pins_mod.CAM_PCLK,
            )
            sccb_ok = _init_sccb(sda, scl, addr, freq)
        else:
            print("[ov7670] OV7670 NO encontrado en I2C")
            print("[ov7670] Revisa: 3.3V, GND comun, pull-ups SDA/SCL,")
            print("[ov7670]         XCLK GP22, PWDN GP19=LOW, RST GP16")
            print("[ov7670]         (OLED en 0x3C indica que el bus si funciona)")

    _use_stub = force_stub or not sccb_ok
    global _pio_ready
    _pio_ready = False
    if sccb_ok and getattr(cfg, "CAMERA_USE_PIO", True):
        try:
            import ov7670_pio

            _pio_ready = ov7670_pio.init(_width, _height)
        except Exception as e:
            print("[ov7670] PIO no disponible:", e)

    if _use_stub and not force_stub:
        print("[ov7670] sin captura (revisa RST pull-up, PWDN GND, SDA/SCL, 3.3V)")

    _ready = True
    mode = "stub" if _use_stub else ("pio+dma" if _pio_ready else "sccb+parallel")
    print("[ov7670] listo {} {}x{}".format(mode, _width, _height))
    try:
        import debug_cam

        debug_cam.log(
            "A",
            "ov7670.py:init",
            "camera init result",
            {
                "mode": mode,
                "stub": _use_stub,
                "sccb_ok": sccb_ok,
                "sccb_addr": _sccb_addr,
                "publish_stub": bool(getattr(cfg, "CAMERA_PUBLISH_STUB", False)),
            },
        )
    except Exception:
        pass
    return True


def capture_frame(frame_id=0):
    """Devuelve (width, height, rgb565_buffer) o None.
    El buffer es un memoryview al buffer preasignado en PIO; se invalida en la
    siguiente captura. NO se guarda copia interna para evitar fugas de RAM.
    """
    global _last_capture_ms
    if not _ready:
        return None

    w, h = _width, _height
    import config as _cfg

    min_iv = int(getattr(_cfg, "CAMERA_MIN_CAPTURE_INTERVAL_MS", 0))
    now_ms = time.ticks_ms()
    if min_iv > 0 and _last_capture_ms:
        if time.ticks_diff(now_ms, _last_capture_ms) < min_iv:
            try:
                import ov7670_pio

                if ov7670_pio.is_ready() and ov7670_pio._out:
                    raw = memoryview(ov7670_pio._out)[: w * h * 2]
                    if len(raw) >= w * h * 2:
                        return w, h, raw
            except Exception:
                pass
            return None

    publish_stub = bool(getattr(_cfg, "CAMERA_PUBLISH_STUB", True))
    reason = "ok"
    if _use_stub:
        if not publish_stub:
            reason = "stub_no_publish"
            try:
                import debug_cam

                debug_cam.log(
                    "A",
                    "ov7670.py:capture_frame",
                    "capture skipped",
                    {"reason": reason, "stub": True, "publish_stub": False},
                )
            except Exception:
                pass
            return None
        raw = _capture_parallel_stub(w, h, frame_id)
        reason = "stub_pattern"
    else:
        raw = None
        if _pio_ready:
            try:
                import ov7670_pio

                raw = ov7670_pio.capture_rgb565(w, h)
                if raw:
                    reason = "pio_dma"
            except Exception as e:
                print("[ov7670] PIO capture:", e)
                raw = None
        # Solo aceptamos frames completos
        if raw is not None and len(raw) < w * h * 2:
            print("[ov7670] PIO frame incompleto:", len(raw), "/", w * h * 2)
            raw = None
        if raw is None and publish_stub:
            raw = _capture_parallel_stub(w, h, frame_id)
            reason = "real_fail_stub_fallback"
        elif raw is None:
            reason = "real_capture_fail"
            try:
                import debug_cam

                debug_cam.log(
                    "E",
                    "ov7670.py:capture_frame",
                    "capture skipped",
                    {
                        "reason": reason,
                        "stub": False,
                        "fail": _capture_fail_reason,
                        "pio": _pio_ready,
                    },
                )
            except Exception:
                pass
            return None

    # NO guardar copia del frame: el frame raw es un memoryview al buffer
    # preasignado en PIO; mantener referencia bloquearia la siguiente captura.
    # Si se necesita reuso, copiar explicitamente en quien lo use.
    try:
        import debug_cam

        debug_cam.log(
            "E",
            "ov7670.py:capture_frame",
            "capture ok",
            {
                "reason": reason,
                "stub": _use_stub,
                "bytes": len(raw) if raw else 0,
                "frame_id": frame_id,
            },
        )
    except Exception:
        pass
    _last_capture_ms = now_ms
    return w, h, raw


def get_last_frame():
    """Devuelve memoryview del ultimo buffer PIO (puede estar sobreescrito)."""
    try:
        import ov7670_pio

        if ov7670_pio.is_ready() and ov7670_pio._out:
            return memoryview(ov7670_pio._out)[: _width * _height * 2]
    except Exception:
        pass
    return None


def is_stub_mode():
    """True si no hay captura paralela real (patron interno o sin sensor)."""
    return _use_stub


def is_ready():
    return _ready


def get_status():
    return {
        "ready": _ready,
        "stub": _use_stub,
        "sccb_addr": _sccb_addr,
        "width": _width,
        "height": _height,
        "reset_gpio": _reset_pin,
        "pwdn_gpio": _pwdn_pin,
        "pio": _pio_ready,
    }
