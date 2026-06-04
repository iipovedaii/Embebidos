# SISEMB - Capa de compatibilidad de runtime.
# Mantiene API usada por robot_repl/run_sisemb, ahora sobre simpleBroker.

import robot_ctl
from runtime_simplebroker import MainApp

_APP = None


def _get_app():
    global _APP
    if _APP is None:
        _APP = MainApp()
    return _APP


def _stop_motors():
    _get_app()._stop_motors()


def setup_hardware():
    return _get_app().setup_hardware()


def setup_wifi():
    return _get_app().setup_wifi()


def connect_mqtt():
    return _get_app().connect_mqtt()


def disconnect_mqtt():
    return _get_app().disconnect_mqtt()


def run_loop():
    return _get_app().run_loop()


def main():
    s = robot_ctl.state
    s.running = True
    s.paused = False
    run_loop()
