# MicroPython ejecuta este archivo tras boot.py en cada reinicio suave.
#
# RUN_ALL_ON_MAIN=True  → arranque completo (Wi-Fi + HW + MQTT) al conectar/Run.
# RUN_ALL_ON_MAIN=False → REPL libre; usa run_sisemb.py + Run o robot_repl.* .

import config

if getattr(config, "RUN_ALL_ON_MAIN", False):
    try:
        import run_sisemb

        run_sisemb.go()
    except KeyboardInterrupt:
        print("[main] detenido (Ctrl+C)")
        try:
            import robot_repl

            robot_repl.stop()
        except Exception:
            pass
    except Exception as e:
        import sys

        print("[main] arranque automatico fallo:")
        sys.print_exception(e)
else:
    pass
