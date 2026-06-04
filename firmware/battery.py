# Lectura de nivel de bateria via ADC (divisor de tension).

from machine import ADC

_adc = None
_samples = []


def _get_adc(pin):
    global _adc
    if _adc is None:
        _adc = ADC(pin)
    return _adc


def read_raw(pin):
    """Valor ADC 0–65535 (16-bit en Pico)."""
    return _get_adc(pin).read_u16()


def read_voltage(pin, divider_ratio, vref=3.3, calib_scale=1.0):
    """Tension del pack en voltios (tras divisor y calibracion)."""
    raw = read_raw(pin)
    v_adc = (raw / 65535.0) * vref
    return v_adc * divider_ratio * calib_scale


def read_debug(pin, divider_ratio, vref=3.3, calib_scale=1.0):
    """Imprime lectura cruda para calibrar con multimetro."""
    raw = read_raw(pin)
    v_adc = (raw / 65535.0) * vref
    v_raw = v_adc * divider_ratio
    v = v_raw * calib_scale
    print(
        "[battery] raw={} v_adc={:.3f}V v_pack={:.2f}V (ratio={} scale={})".format(
            raw, v_adc, v, divider_ratio, calib_scale
        )
    )
    return raw, v_adc, v


def read_percent(pin, divider_ratio, v_min, v_max, vref=3.3, calib_scale=1.0):
    """Porcentaje 0–100 y voltaje de pack."""
    v = read_voltage(pin, divider_ratio, vref, calib_scale)
    if v_max <= v_min:
        pct = 0
    else:
        pct = (v - v_min) / (v_max - v_min) * 100.0
    pct = max(0.0, min(100.0, pct))
    return int(round(pct)), round(v, 2)


def read_smoothed(pin, divider_ratio, v_min, v_max, n=8, vref=3.3, calib_scale=1.0):
    """Promedia varias lecturas para reducir ruido."""
    global _samples
    if len(_samples) < n:
        _samples.append(read_voltage(pin, divider_ratio, vref, calib_scale))
    else:
        _samples.pop(0)
        _samples.append(read_voltage(pin, divider_ratio, vref, calib_scale))
    v = sum(_samples) / len(_samples)
    if v_max <= v_min:
        pct = 0
    else:
        pct = (v - v_min) / (v_max - v_min) * 100.0
    pct = max(0.0, min(100.0, pct))
    return int(round(pct)), round(v, 2)
