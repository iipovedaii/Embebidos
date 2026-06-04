# Estado compartido del robot (bucle principal + REPL).


class State:
    __slots__ = (
        "running",
        "paused",
        "thread_active",
        "mqtt_client",
        "hw_on",
        "hw_ready",
        "oled_display",
        "loop_n",
        "cam_next_ms",
        "wifi_linked",
        "mqtt_linked",
    )

    def __init__(self):
        self.running = False
        self.paused = False
        self.thread_active = False
        self.mqtt_client = None
        self.hw_on = False
        self.hw_ready = False
        self.oled_display = None
        self.loop_n = 0
        self.cam_next_ms = 0
        self.wifi_linked = False
        self.mqtt_linked = False


state = State()
