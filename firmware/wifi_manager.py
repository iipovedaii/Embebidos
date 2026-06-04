# SISEMB - Wi-Fi robusto (Pico 2 W / CYW43). Hotspots moviles: desconectar + deinit + reintentos.

import network
import time
from machine import Pin

_LED = Pin("LED", Pin.OUT)
_WLAN = network.WLAN(network.STA_IF)
_AP = network.WLAN(network.AP_IF)
_MODE = "sta"  # "sta" | "ap"

# network.STATUS_* (MicroPython / CYW43)
_STATUS_NAMES = {
    -3: "WRONG_PASSWORD",
    -2: "NO_AP_FOUND",
    -1: "CONNECT_FAIL",
    0: "IDLE",
    1: "CONNECTING",
    2: "GOT_IP",
    3: "CONNECTED",
}


def _blink(times=3, ms=80):
    for _ in range(times):
        _LED.on()
        time.sleep_ms(ms)
        _LED.off()
        time.sleep_ms(ms)


def _status_label():
    try:
        s = _WLAN.status()
        return _STATUS_NAMES.get(s, str(s))
    except Exception:
        return "?"


def wifi_mode():
    return _MODE


def is_connected():
    if _MODE == "ap":
        try:
            return _AP.active()
        except Exception:
            return False
    return _WLAN.isconnected()


def get_rssi(default=-99):
    if _MODE == "ap":
        return default
    try:
        return _WLAN.status("rssi")
    except Exception:
        return default


def get_ip():
    try:
        if _MODE == "ap":
            return _AP.ifconfig()[0]
        if _WLAN.isconnected():
            return _WLAN.ifconfig()[0]
    except Exception:
        pass
    return "0.0.0.0"


def _wifi_reset():
    """Reinicia el chip CYW43 (critico tras desconectar USB o fallos previos)."""
    global _WLAN
    try:
        _WLAN.disconnect()
    except Exception:
        pass
    try:
        _WLAN.active(False)
    except Exception:
        pass
    if hasattr(_WLAN, "deinit"):
        try:
            _WLAN.deinit()
        except Exception:
            pass
    time.sleep_ms(400)
    try:
        _WLAN.active(True)
    except Exception:
        # Si CYW43 queda en mal estado, recrear interfaz STA y reactivar.
        _WLAN = network.WLAN(network.STA_IF)
        _WLAN.active(True)
    time.sleep_ms(400)


def _apply_wlan_config(cfg=None):
    country = "MX"
    if cfg is not None:
        country = getattr(cfg, "WIFI_COUNTRY", country)
    for code in (country, "US", "ES", "XX"):
        try:
            _WLAN.config(country=code)
            break
        except Exception:
            continue


def _scan_ssid(target):
    """Comprueba si el SSID es visible (2.4 GHz)."""
    try:
        nets = _WLAN.scan()
    except Exception as e:
        print("[wifi] scan error:", e)
        return False
    found = []
    for ap in nets:
        try:
            name = ap[0].decode() if isinstance(ap[0], bytes) else str(ap[0])
        except Exception:
            continue
        if name == target:
            print("[wifi] AP visible:", name, "RSSI", ap[3])
            return True
        found.append(name)
    print("[wifi] SSID", repr(target), "no en scan. Redes:", found[:8])
    return False


def _ap_config(ssid, password):
    """CYW43/Pico W: solo essid+password (authmode no existe -> ValueError)."""
    try:
        _AP.config(essid=ssid, password=password)
        return True
    except ValueError:
        pass
    try:
        _AP.config(ssid=ssid, key=password)
        return True
    except Exception as e:
        print("[wifi-ap] config error:", e)
        return False


def start_ap(ssid, password, ip="192.168.4.1", cfg=None):
    """Punto de acceso en la Pico: el PC se conecta aqui (evita aislamiento de hotspot movil)."""
    global _MODE

    _MODE = "ap"
    if cfg is not None:
        ip = getattr(cfg, "WIFI_AP_IP", ip)

    try:
        _WLAN.disconnect()
    except Exception:
        pass
    try:
        _WLAN.active(False)
    except Exception:
        pass
    try:
        _AP.active(False)
    except Exception:
        pass
    time.sleep_ms(300)

    if not _ap_config(ssid, password):
        return False

    # En Pico W: config ANTES de active(True); sin authmode.
    try:
        _AP.active(True)
    except Exception as e:
        print("[wifi-ap] active error:", e)
        return False

    t0 = time.ticks_ms()
    while not _AP.active():
        if time.ticks_diff(time.ticks_ms(), t0) > 8000:
            print("[wifi-ap] timeout esperando AP activo")
            return False
        time.sleep_ms(100)

    mask = "255.255.255.0"
    try:
        _AP.ifconfig((ip, mask, ip, "8.8.8.8"))
    except Exception:
        pass

    _LED.on()
    print("[wifi-ap] AP listo ->", _AP.ifconfig())
    print("[wifi-ap] Conecta el PC a SSID", repr(ssid))
    print("[wifi-ap] BROKER_HOST en config.py = IP del PC (ej. 192.168.4.2)")
    return True


def connect_from_config(cfg):
    mode = "sta"
    if cfg is not None:
        mode = str(getattr(cfg, "WIFI_MODE", "sta")).lower()
    if mode == "ap":
        ssid = getattr(cfg, "WIFI_AP_SSID", "SISEMB-G3")
        password = getattr(cfg, "WIFI_AP_PASS", "")
        return start_ap(ssid, password, cfg=cfg)
    return connect(cfg.WIFI_SSID, cfg.WIFI_PASS, cfg=cfg)


def ensure_from_config(cfg):
    if is_connected():
        return True
    return connect_from_config(cfg)


def connect(ssid, password, timeout=45, cfg=None):
    """Conecta a Wi-Fi con reinicio CYW43 y varios intentos."""
    global _MODE
    _MODE = "sta"
    try:
        _AP.active(False)
    except Exception:
        pass
    timeout = int(timeout)
    retries = 3
    scan_first = True
    if cfg is not None:
        timeout = int(getattr(cfg, "WIFI_TIMEOUT_SEC", timeout))
        retries = int(getattr(cfg, "WIFI_CONNECT_RETRIES", retries))
        scan_first = bool(getattr(cfg, "WIFI_SCAN_BEFORE_CONNECT", True))

    saw_eperm = False
    for attempt in range(1, retries + 1):
        # Recovery agresivo: recrear STA en cada intento para limpiar estado CYW43.
        global _WLAN
        try:
            _WLAN = network.WLAN(network.STA_IF)
        except Exception:
            pass
        try:
            _wifi_reset()
        except Exception as e:
            print("[wifi] reset error:", e)
            time.sleep_ms(600)
            continue
        _apply_wlan_config(cfg)

        if _WLAN.isconnected():
            _LED.on()
            print("[wifi] ya conectado ->", _WLAN.ifconfig())
            return True

        if scan_first and attempt == 1 and not saw_eperm:
            if not _scan_ssid(ssid):
                time.sleep_ms(120)

        print("[wifi] intento", attempt, "/", retries, "->", ssid)
        try:
            _WLAN.connect(ssid, password)
        except OSError as e:
            print("[wifi] connect error:", e, "status:", _status_label())
            if "EPERM" in str(e):
                saw_eperm = True
                # Si el driver esta inestable, evitar scan en siguientes intentos.
                scan_first = False
            time.sleep_ms(500)
            continue

        t0 = time.ticks_ms()
        while not _WLAN.isconnected():
            st = _status_label()
            if time.ticks_diff(time.ticks_ms(), t0) > timeout * 1000:
                print("[wifi] timeout status:", st)
                _LED.off()
                break
            _LED.toggle()
            time.sleep_ms(200)
        else:
            _LED.on()
            print("[wifi] OK ->", _WLAN.ifconfig())
            return True

        time.sleep_ms(800)

    print("[wifi] FALLO tras", retries, "intentos. Revisa:")
    print("  - SSID/password en config.py")
    print("  - Hotspot 2.4 GHz activo (Pico no usa 5 GHz)")
    print("  - Datos moviles + compartir internet en el movil")
    return False


def recover_after_peripherals(ssid, password, cfg=None):
    """Reinicia CYW43 tras init I2C/servos (evita send_ethernet -5 / STALL)."""
    if cfg is not None and str(getattr(cfg, "WIFI_MODE", "sta")).lower() == "ap":
        return connect_from_config(cfg)

    import gc

    gc.collect()
    time.sleep_ms(350)
    if _WLAN.isconnected():
        try:
            _WLAN.disconnect()
        except Exception:
            pass
        time.sleep_ms(200)
    return connect(ssid, password, cfg=cfg)


def ensure_connected(ssid, password, max_backoff=30, cfg=None):
    """Reconexion con backoff hasta tener IP."""
    if cfg is not None and str(getattr(cfg, "WIFI_MODE", "sta")).lower() == "ap":
        if is_connected():
            return True
        return connect_from_config(cfg)

    if _WLAN.isconnected():
        return True

    backoff = 1
    while not _WLAN.isconnected():
        print("[wifi] reconectando en", backoff, "s")
        _blink(times=2, ms=80)
        time.sleep(backoff)
        if connect(ssid, password, cfg=cfg):
            return True
        backoff = min(max_backoff, backoff * 2)

    return False


def disconnect(deinit=True):
    """Desconecta Wi-Fi y apaga LED. deinit=True reinicia CYW43."""
    global _MODE
    try:
        _WLAN.disconnect()
    except Exception:
        pass
    try:
        _AP.active(False)
    except Exception:
        pass
    _LED.off()
    _MODE = "sta"
    if deinit:
        try:
            _WLAN.active(False)
        except Exception:
            pass
        if hasattr(_WLAN, "deinit"):
            try:
                _WLAN.deinit()
            except Exception:
                pass
    print("[wifi] desconectado")
    return True
