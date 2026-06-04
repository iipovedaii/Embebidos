# Arranque al encender la Pico.
# Por defecto NO arranca el robot: REPL libre + robot_repl.* para control.
# RUN_MAIN_ON_BOOT=True: arranque autonomo (main en primer plano).

import config

if getattr(config, "RUN_MAIN_ON_BOOT", False):
    try:
        import robot_ctl
        import sisemb_loop

        robot_ctl.state.running = True
        sisemb_loop.main()
    except KeyboardInterrupt:
        print("[boot] detenido (Ctrl+C)")
        try:
            import robot_repl

            robot_repl.stop()
        except Exception:
            pass
    except Exception as e:
        import sys

        sys.print_exception(e)
else:
    try:
        import robot_repl

        robot_repl.banner()
    except Exception as e:
        print("[boot] REPL listo · import robot_repl:", e)
