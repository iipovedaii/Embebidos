# Diagnostico OV7670 desde REPL: bus I2C + power + reset + scan.
#
#   >>> import diag_camera
#   >>> diag_camera.run()
#
# Imprime exactamente que pasa al inicializar la camara, paso a paso.

import time

from machine import I2C, Pin, PWM

import hardware_pins as pins


def _scan(bus, label):
    try:
        addrs = sorted(bus.scan())
    except Exception as e:
        print("[diag]", label, "scan error:", e)
        return []
    hexes = ["0x{:02x}".format(a) for a in addrs]
    print("[diag]", label, "I2C:", hexes)
    return addrs


def _sccb_write(bus, addr, reg, val):
    try:
        bus.writeto(addr, bytes((reg, val)))
        return True
    except OSError:
        return False


def _sccb_read(bus, addr, reg):
    """OV7670 no soporta repeated-START: 2 transacciones separadas."""
    try:
        bus.writeto(addr, bytes((reg,)))
    except OSError:
        return None
    time.sleep_us(100)
    try:
        return bus.readfrom(addr, 1)[0]
    except OSError:
        return None


def _pin_label(value):
    return "GP{}".format(value) if value is not None else "None"


def signals_check(bus, addr, pwm):
    """Verifica que VSYNC/HREF/PCLK oscilen tras configurar el sensor."""
    from machine import mem32

    print("[diag] Configurando sensor (Adafruit + COM10 VS_NEG + 80x60)...")
    import ov7670_registers as oreg

    oreg.apply_all(
        lambda r, v: _sccb_write(bus, addr, r, v),
        lambda r: _sccb_read(bus, r),
        size_div=oreg.SIZE_DIV8,
    )
    time.sleep_ms(200)

    print("[diag] Leyendo VSYNC (GP13), HREF (GP27), PCLK (GP28) durante 2 s...")
    Pin(13, Pin.IN)
    Pin(27, Pin.IN)
    Pin(28, Pin.IN)
    vsync_bit = 1 << 13
    href_bit = 1 << 27
    pclk_bit = 1 << 28
    GPIO_IN = 0xD0000004

    last = mem32[GPIO_IN]
    v_changes = h_changes = p_changes = 0
    t_end = time.ticks_add(time.ticks_ms(), 2000)
    while time.ticks_diff(time.ticks_ms(), t_end) < 0:
        cur = mem32[GPIO_IN]
        d = cur ^ last
        if d & vsync_bit:
            v_changes += 1
        if d & href_bit:
            h_changes += 1
        if d & pclk_bit:
            p_changes += 1
        last = cur

    print("[diag] transiciones en 2 s:")
    print("  VSYNC (GP13):", v_changes)
    print("  HREF  (GP27):", h_changes)
    print("  PCLK  (GP28):", p_changes)

    if v_changes < 2:
        print("[diag] PROBLEMA: VSYNC no oscila.")
        print("       - Revisa cable de VSYNC en GP13")
        print("       - Confirma que XCLK GP22 llega al pin XCLK del modulo")
    elif h_changes < 50:
        print("[diag] PROBLEMA: HREF apenas oscila.")
        print("       - Revisa cable de HREF en GP27")
    elif p_changes < 1000:
        print("[diag] PROBLEMA: PCLK no llega.")
        print("       - Revisa cable de PCLK en GP28")
    else:
        print("[diag] Señales OK: la cámara está produciendo frames.")
        print("       Vuelve a ejecutar run_sisemb.py")


def run():
    print("=" * 50)
    print("DIAG OV7670  -  SISEMB")
    print("=" * 50)

    sda = pins.I2C_SDA_PIN
    scl = pins.I2C_SCL_PIN
    rst = pins.CAM_RESET
    pwd = pins.CAM_PWDN
    xclk_pin = pins.CAM_XCLK
    print("Pines:")
    print("  SDA={} SCL={}".format(_pin_label(sda), _pin_label(scl)))
    print("  RST={} PWDN={} XCLK={}".format(_pin_label(rst), _pin_label(pwd), _pin_label(xclk_pin)))

    bus = I2C(0, sda=Pin(sda), scl=Pin(scl), freq=100000)
    addrs_pre = _scan(bus, "previo (sin XCLK, sin power)")

    print("[diag] Configurando PWDN HIGH (sleep)...")
    pwdn = Pin(pwd, Pin.OUT, value=1)
    time.sleep_ms(50)

    print("[diag] Arrancando XCLK @ 8 MHz...")
    pwm = PWM(Pin(xclk_pin))
    pwm.freq(8_000_000)
    pwm.duty_u16(32768)
    time.sleep_ms(50)

    print("[diag] PWDN LOW (encender camara)...")
    pwdn.value(0)
    time.sleep_ms(100)

    print("[diag] Pulso RESET...")
    rst_obj = Pin(rst, Pin.OUT, value=1)
    rst_obj.value(0)
    time.sleep_ms(10)
    rst_obj.value(1)
    time.sleep_ms(100)

    found = None
    for i in range(5):
        addrs = _scan(bus, "intento {}".format(i + 1))
        for cand in (0x21, 0x42, 0x60):
            if cand in addrs:
                found = cand
                break
        if found is not None:
            break
        time.sleep_ms(120)

    if found is None:
        print()
        print("RESULTADO: OV7670 NO RESPONDE en I2C")
        print("Causas tipicas:")
        print("  - SDA/SCL invertidos, mal cableados o sin pull-ups (4.7k a 3.3V)")
        print("  - VCC en 5V (debe ser 3.3V) o sin GND comun")
        print("  - XCLK no llega al pin XCLK de la camara (revisa cable GP22)")
        print("  - PWDN flotante o cableado mal (LOW = encendida)")
        print("  - Modulo OV7670 dañado")
        if 0x27 in addrs_pre:
            print("[diag] OLED u otro dispositivo I2C detectado -> el bus funciona; revisa OV7670 @ 0x21.")
        return False

    print()
    print("RESULTADO: OV7670 detectado en 0x{:02x}".format(found))

    print("[diag] soft reset SCCB (COM7=0x80)...")
    _sccb_write(bus, found, 0x12, 0x80)
    time.sleep_ms(150)

    print("[diag] lectura SCCB (write+STOP / read+STOP) - 4 intentos:")
    ok = False
    for i in range(4):
        pid = _sccb_read(bus, found, 0x0A)
        ver = _sccb_read(bus, found, 0x0B)
        midh = _sccb_read(bus, found, 0x1C)
        midl = _sccb_read(bus, found, 0x1D)
        print(
            "  intento {} PID=0x{:02x} VER=0x{:02x} MIDH=0x{:02x} MIDL=0x{:02x}".format(
                i + 1,
                pid if pid is not None else 0,
                ver if ver is not None else 0,
                midh if midh is not None else 0,
                midl if midl is not None else 0,
            )
        )
        if pid == 0x76:
            ok = True
            break
        time.sleep_ms(60)

    if ok:
        print()
        print("OK: OV7670 (PID=0x76) responde correctamente por SCCB.")
        print()
        signals_check(bus, found, pwm)
        return True

    print()
    print("PROBLEMA: la camara ACK la direccion pero las lecturas son 0.")
    print("Posibles causas:")
    print("  - Falta pulse RESET firme (cable RST GP16 suelto / sin tierra)")
    print("  - XCLK no llega al sensor: confirma que GP22 va a XCLK del modulo")
    print("  - Sin pull-ups I2C externas (4.7k a 3.3V en SDA y SCL)")
    print("  - Cable SDA/SCL muy largo o ruidoso (probar < 10 cm)")
    print("  - Modulo OV7670 falsificado / chip dañado")
    return False
