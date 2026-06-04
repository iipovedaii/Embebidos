# Bus I2C compartido (OLED SSD1306 + OV7670 SCCB).

from machine import I2C, Pin

_bus = None
_lock = None


def get_bus(sda_pin, scl_pin, freq=100000):
    global _bus, _lock
    if _bus is None:
        _bus = I2C(0, sda=Pin(sda_pin), scl=Pin(scl_pin), freq=freq)
    if _lock is None:
        try:
            import _thread

            _lock = _thread.allocate_lock()
        except ImportError:
            _lock = None
    return _bus


def lock():
    if _lock is not None:
        _lock.acquire()


def unlock():
    if _lock is not None:
        try:
            _lock.release()
        except RuntimeError:
            pass


def scan(bus=None):
    """Lista direcciones 7-bit detectadas."""
    if bus is None:
        return []
    lock()
    try:
        return sorted(bus.scan())
    except Exception:
        return []
    finally:
        unlock()
