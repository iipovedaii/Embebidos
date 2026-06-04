# Control del robot desde el REPL de MicroPython (MicroPico / Thonny / mpremote).
#
#   import robot_repl
#   robot_repl.help()
#   robot_repl.wifi_connect()
#   robot_repl.start()          # runtime en segundo plano (_thread)
#   robot_repl.pause()
#   robot_repl.resume()
#   robot_repl.stop()
#
# Atajos en el REPL (tras import robot_repl):
#   start(), stop(), pause(), resume(), status(), help()

import gc
import time

import robot_ctl

try:
    import _thread
except ImportError:
    _thread = None


def _load_loop():
    """Carga modulo runtime (sisemb_loop en Pico; fallback main legacy)."""
    try:
        import sisemb_loop

        return sisemb_loop
    except ImportError:
        import main

        if hasattr(main, "run_loop"):
            return main
        raise ImportError("Falta sisemb_loop.py en la Pico (sube firmware de nuevo)")


def help():
    print(
        """
SISEMB · control desde REPL
──────────────────────────
  help()            esta ayuda
  status()          Wi-Fi / broker / runtime / pausa
  wifi_connect()    conectar Wi-Fi
  wifi_disconnect() desconectar Wi-Fi
  mqtt_connect()    conectar broker runtime (requiere Wi-Fi)
  mqtt_disconnect() desconectar broker runtime
  hardware_init()   init sensores, motores, I2C, MeArm, camara
  start()           arrancar runtime (segundo plano si _thread OK)
  start(blocking=1) arrancar en primer plano (recomendado / Run)
  run_all()         Wi-Fi + hardware + start(blocking) de una vez
  pause()           pausar telemetria (mantiene conexiones)
  resume()          reanudar tras pause()
  stop()            parar runtime, broker, motores
"""
    )


def banner():
    print("[boot] REPL listo")
    print("[boot] Un clic: abre run_sisemb.py y pulsa Run")
    print("[boot] O escribe: import robot_repl  /  robot_repl.run_all()")


def status():
    import wifi_manager

    s = robot_ctl.state
    wifi = "ON" if wifi_manager.is_connected() else "OFF"
    mqtt = "ON" if s.mqtt_linked and s.mqtt_client else "OFF"
    loop = "RUN" if s.running else "STOP"
    pause = "PAUSED" if s.paused else "ACTIVE"
    hw = "OK" if s.hw_ready else ("OFF" if not s.hw_on else "FAIL")
    print(
        "[status] wifi={} broker={} loop={} {} hw={} frame={}".format(
            wifi, mqtt, loop, pause, hw, s.loop_n
        )
    )
    if wifi_manager.is_connected():
        try:
            mode = wifi_manager.wifi_mode()
            ip = wifi_manager.get_ip()
            if mode == "ap":
                print("         AP", ip, "modo=AP (PC -> broker en BROKER_HOST)")
            else:
                print("         IP", ip, "RSSI", wifi_manager.get_rssi())
        except Exception:
            pass
    return {
        "wifi": wifi,
        "mqtt": mqtt,
        "loop": loop,
        "pause": pause,
        "hw": hw,
    }


def wifi_connect():
    import config
    import wifi_manager

    ok = wifi_manager.connect_from_config(config)
    robot_ctl.state.wifi_linked = ok
    status()
    return ok


def wifi_disconnect(deinit=True):
    import wifi_manager

    wifi_manager.disconnect(deinit=deinit)
    robot_ctl.state.wifi_linked = False
    status()
    return True


def mqtt_connect():
    loop = _load_loop()

    if not loop.connect_mqtt():
        status()
        return False
    status()
    return True


def mqtt_disconnect():
    loop = _load_loop()

    loop.disconnect_mqtt()
    status()
    return True


def hardware_init():
    loop = _load_loop()

    ok = loop.setup_hardware()
    status()
    return ok


def run_all():
    """Wi-Fi + hardware + runtime en primer plano (equivalente a run_sisemb.go)."""
    import run_sisemb

    return run_sisemb.go()


def start(blocking=False, background=True):
    """Arranca runtime principal (telemetria + OLED + camara)."""
    import sys

    try:
        loop = _load_loop()
    except Exception as e:
        print("[robot] error cargando runtime:")
        sys.print_exception(e)
        return False

    s = robot_ctl.state
    if s.running:
        print("[robot] ya en marcha (pause() o stop() primero)")
        return False

    if blocking:
        background = False

    s.running = True
    s.paused = False

    if background:
        if _thread is None:
            print("[robot] sin _thread -> modo blocking")
            background = False
        else:

            def _worker():
                s.thread_active = True
                try:
                    loop.run_loop()
                except Exception as e:
                    sys.print_exception(e)
                finally:
                    s.thread_active = False
                    s.running = False
                    print("[robot] runtime terminado")

            try:
                _thread.start_new_thread(_worker, ())
            except Exception as e:
                print("[robot] _thread fallo, usando blocking:")
                sys.print_exception(e)
                background = False
            else:
                time.sleep_ms(50)
                print("[robot] runtime en segundo plano · stop() para parar")
                status()
                return True

    print("[robot] runtime en primer plano · Ctrl+C = stop()")
    try:
        loop.run_loop()
    except KeyboardInterrupt:
        stop()
    except Exception as e:
        s.running = False
        print("[robot] error en runtime:")
        sys.print_exception(e)
        return False
    return True


def stop():
    loop = _load_loop()

    s = robot_ctl.state
    if not s.running and not s.mqtt_linked and not s.hw_ready:
        loop.disconnect_mqtt()
        loop._stop_motors()
        print("[robot] ya detenido")
        status()
        return True

    s.running = False
    s.paused = False
    for _ in range(30):
        if not s.thread_active:
            break
        time.sleep_ms(50)

    loop.disconnect_mqtt()
    loop._stop_motors()
    s.loop_n = 0
    s.cam_next_ms = 0
    print("[robot] detenido")
    gc.collect()
    status()
    return True


def pause():
    if not robot_ctl.state.running:
        print("[robot] runtime no activo")
        return False
    robot_ctl.state.paused = True
    print("[robot] pausado (mqtt/wifi siguen; resume() para continuar)")
    status()
    return True


def resume():
    s = robot_ctl.state
    if not s.running:
        print("[robot] usa start() primero")
        return False
    s.paused = False
    print("[robot] reanudado")
    status()
    return True


# Atajos REPL: import robot_repl as r  →  r.start()
start = start
stop = stop
pause = pause
resume = resume
