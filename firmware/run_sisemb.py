# SISEMB · arranque con un solo clic (MicroPico: abre ESTE archivo y pulsa Run).
#
# Secuencia: Wi-Fi → hardware → runtime simpleBroker (primer plano; Ctrl+C para parar).

import gc

gc.collect()


def go():
    import sys

    import robot_repl

    print("=== SISEMB arranque automatico ===")
    gc.collect()

    if not robot_repl.wifi_connect():
        print("[run] Wi-Fi fallo. Revisa SSID/password en config.py")
        return False

    if not robot_repl.hardware_init():
        print("[run] hardware_init fallo (MQTT puede seguir sin sensores)")
    else:
        print("[run] hardware OK")

    gc.collect()
    print("[run] iniciando runtime simpleBroker (Ctrl+C = parar)...")
    try:
        return robot_repl.start(blocking=True, background=False)
    except Exception as e:
        print("[run] error al arrancar:")
        sys.print_exception(e)
        return False


if __name__ == "__main__":
    go()
