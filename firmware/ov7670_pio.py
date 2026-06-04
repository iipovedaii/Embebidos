# Captura OV7670 con PIO + DMA · pines no consecutivos (D0,D1,D7..D12).
# Buffer DMA preasignado en init() para evitar fallos de memoria.
# Decodificacion bit-shuffle con @viper -> ~10x mas rapido que Python puro.

import time

try:
    import rp2
    import struct
    import micropython
    from machine import Pin
except ImportError:
    rp2 = Pin = struct = micropython = None

VSYNC_PIN = 13
HREF_PIN = 27
PCLK_PIN = 28

# D0..D7 -> GP0, GP1, GP7..GP12
_DATA_MAP = ((0, 0), (1, 1), (7, 2), (8, 3), (9, 4), (10, 5), (11, 6), (12, 7))

_sm = None
_dma = None
_ready = False
_buf_words = None        # buffer DMA preasignado
_buf_capacity = 0        # samples
_out = None              # buffer salida bytes


def _decode_byte(gpio_word):
    b = 0
    for gp, bit in _DATA_MAP:
        if gpio_word & (1 << gp):
            b |= 1 << bit
    return b


@micropython.viper
def _decode_and_swap(src, dst, n: int):
    """Por cada palabra de 32-bit GPIO_IN, calcula el byte de pixel D0..D7
    y guarda en dst. Tambien swap byte alto/bajo por pareja (big->little endian)
    en una sola pasada. n = bytes de salida; src tiene n*4 bytes.

    D0=GP0, D1=GP1, D2..D7=GP7..GP12
       -> byte = (gpio & 0x03) | ((gpio >> 5) & 0xFC)
    """
    s = ptr32(src)
    d = ptr8(dst)
    i: int = 0
    while i < n - 1:
        g0: int = int(s[i])
        b0: int = (g0 & 3) | ((g0 >> 5) & 0xFC)
        g1: int = int(s[i + 1])
        b1: int = (g1 & 3) | ((g1 >> 5) & 0xFC)
        # swap big-endian wire -> little-endian (b1 antes que b0)
        d[i] = b1
        d[i + 1] = b0
        i = i + 2


# PIO: solo guarda muestras cuando HREF=1. 1 word por byte de pixel.
@rp2.asm_pio(in_shiftdir=rp2.PIO.SHIFT_RIGHT, push_thresh=32, autopush=True)
def pio_cap_sisemb():
    wait(0, gpio, 13)
    wait(1, gpio, 13)
    wrap_target()
    wait(1, gpio, 27)
    wait(1, gpio, 28)
    in_(pins, 32)
    wait(0, gpio, 28)
    wrap()


def init(max_width=80, max_height=60):
    """Inicializa PIO + DMA y preasigna el buffer maximo."""
    global _sm, _dma, _ready, _buf_words, _buf_capacity, _out
    if rp2 is None:
        return False
    for gp, _ in _DATA_MAP:
        Pin(gp, Pin.IN)
    Pin(VSYNC_PIN, Pin.IN)
    Pin(HREF_PIN, Pin.IN)
    Pin(PCLK_PIN, Pin.IN)

    need = max_width * max_height * 2
    margin = max(64, max_width)
    capacity = need + margin
    try:
        _buf_words = bytearray(capacity * 4)
        _out = bytearray(need)
    except MemoryError as e:
        print("[ov7670-pio] memoria insuficiente para", max_width, "x", max_height, ":", e)
        return False

    _buf_capacity = capacity
    try:
        _sm = rp2.StateMachine(0, pio_cap_sisemb, freq=15_000_000, in_base=Pin(0))
        _dma = rp2.DMA()
        _ready = True
        print("[ov7670-pio] SM0 listo, buffer", capacity * 4, "bytes (max", max_width, "x", max_height, ")")
        return True
    except Exception as e:
        print("[ov7670-pio] init fallo:", e)
        _ready = False
        return False


def is_ready():
    return _ready


def capture_rgb565(width, height):
    """Captura un frame RGB565. Devuelve memoryview del buffer preasignado
    (sin asignar memoria nueva). Quien recibe debe consumirlo antes de la
    siguiente captura.
    """
    global _sm, _dma, _buf_words, _out
    if not _ready or _sm is None:
        return None

    need = width * height * 2
    if need + max(64, width) > _buf_capacity:
        print("[ov7670-pio] frame mayor que buffer preasignado")
        return None
    if len(_out) < need:
        # solo crece si la resolucion aumenta entre llamadas
        try:
            _out = bytearray(need)
        except MemoryError:
            return None

    count = need + max(64, width)
    ctrl = _dma.pack_ctrl(inc_read=False, treq_sel=4)

    _sm.active(0)
    _sm.restart()
    _dma.config(read=_sm, write=_buf_words, count=count, ctrl=ctrl)
    _sm.active(1)
    _dma.active(1)

    t_end = time.ticks_add(time.ticks_ms(), 4000)
    while _dma.active():
        if time.ticks_diff(time.ticks_ms(), t_end) > 0:
            _sm.active(0)
            print("[ov7670-pio] DMA timeout")
            return None
    _sm.active(0)

    _decode_and_swap(_buf_words, _out, need)
    return memoryview(_out)[:need]
