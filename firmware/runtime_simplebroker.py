"""Runtime SISEMB por clases con transporte simpleBroker (JSON por linea)."""

import gc
import json
import time

try:
    import usocket as socket
except ImportError:
    import socket

import command_handler
import config
import robot_ctl
import telemetry
import wifi_manager


def _ms_now():
    return time.ticks_ms()


def _ms_diff(a, b):
    return time.ticks_diff(a, b)


def _ms_add(a, b):
    return time.ticks_add(a, b)


def _topic_text(topic):
    if isinstance(topic, bytes):
        try:
            return topic.decode("utf-8")
        except Exception:
            return str(topic)
    return str(topic)


def _os_errno(exc):
    try:
        return exc.args[0]
    except Exception:
        return -1


def _os_would_block(exc):
    # MicroPython/CYW43: 11=EAGAIN, 115=EINPROGRESS (Linux)
    return _os_errno(exc) in (11, 115)


class Task:
    def __init__(self, scheduler, period_ms, priority=10):
        self.scheduler = scheduler
        self.period_ms = max(1, int(period_ms))
        self.priority = int(priority)
        self.next_run_ms = _ms_now()
        scheduler.add(self)

    def update(self, now_ms):
        del now_ms


class Scheduler:
    def __init__(self):
        self.tasks = []

    def add(self, task):
        self.tasks.append(task)
        self.tasks.sort(key=lambda t: t.priority)

    def run_once(self, now_ms=None):
        now_ms = _ms_now() if now_ms is None else now_ms
        for task in self.tasks:
            if _ms_diff(now_ms, task.next_run_ms) >= 0:
                try:
                    task.update(now_ms)
                finally:
                    task.next_run_ms = _ms_add(now_ms, task.period_ms)

    def next_sleep_ms(self, now_ms=None, fallback=3):
        now_ms = _ms_now() if now_ms is None else now_ms
        if not self.tasks:
            return fallback
        waits = []
        for task in self.tasks:
            delta = _ms_diff(task.next_run_ms, now_ms)
            waits.append(0 if delta < 0 else delta)
        wait_ms = min(waits) if waits else fallback
        if wait_ms < 0:
            return 0
        return min(wait_ms, max(1, int(fallback)))


class SocketClientTask(Task):
    def __init__(self, scheduler, host, port, period_ms=20, priority=2):
        super().__init__(scheduler, period_ms, priority=priority)
        self.host = host
        self.port = int(port)
        self.sock = None
        self.connected = False
        self._rx_buffer = b""
        self._tx_queue = []
        self._tx_max_items = int(getattr(config, "SOCKET_TX_MAX_ITEMS", 3))
        self._tx_max_bytes = int(getattr(config, "SOCKET_TX_MAX_BYTES", 8192))
        self._tx_drop_camera = bool(getattr(config, "SOCKET_DROP_CAMERA_ON_PRESSURE", True))
        self.actions = {}
        self._next_retry_ms = _ms_now()
        self._backoff_ms = 500
        self._max_backoff_ms = 8000
        self._tx_stuck_since_ms = None
        self._last_tx_progress_ms = _ms_now()
        self.on_connected = None
        self.on_disconnected = None

    def add_action(self, action, callback):
        self.actions[action] = callback

    def tx_backlog(self):
        return len(self._tx_queue)

    def tx_bytes_queued(self):
        n = 0
        for item in self._tx_queue:
            n += len(item)
        return n

    def _topic_is_camera(self, obj):
        try:
            topic = _topic_text(obj.get("topic", ""))
        except Exception:
            return False
        cam = _topic_text(getattr(config, "MQTT_TOPIC_CAMERA", b"robot/camera"))
        return topic == cam or topic.endswith("/camera")

    def _drop_one_pending(self, prefer_camera=False):
        if not self._tx_queue:
            return False
        if prefer_camera and self._tx_drop_camera:
            cam = _topic_text(getattr(config, "MQTT_TOPIC_CAMERA", b"robot/camera"))
            for i, item in enumerate(self._tx_queue):
                if cam.encode() in item:
                    self._tx_queue.pop(i)
                    return True
        self._tx_queue.pop(0)
        return True

    def queue_json(self, obj):
        if self._topic_is_camera(obj) and self._tx_drop_camera:
            if self.tx_backlog() > 0 or self.tx_bytes_queued() > (self._tx_max_bytes // 2):
                return False

        while self.tx_backlog() >= self._tx_max_items:
            if not self._drop_one_pending(prefer_camera=True):
                return False

        try:
            payload = (json.dumps(obj) + "\n").encode("utf-8")
        except MemoryError:
            gc.collect()
            try:
                payload = (json.dumps(obj) + "\n").encode("utf-8")
            except Exception as e:
                print("[broker] json encode OOM:", e)
                return False
        except Exception as e:
            print("[broker] json encode error:", e)
            return False

        if len(payload) > self._tx_max_bytes:
            if self._topic_is_camera(obj):
                return False
            print("[broker] mensaje grande descartado:", len(payload))

        while self.tx_bytes_queued() + len(payload) > self._tx_max_bytes:
            if not self._drop_one_pending(prefer_camera=True):
                return False

        self._tx_queue.append(payload)
        return True

    def ensure(self, now_ms=None):
        now_ms = _ms_now() if now_ms is None else now_ms
        if self.connected:
            return True
        if _ms_diff(now_ms, self._next_retry_ms) < 0:
            return False
        print("[broker] reintentando conexion a", self.host, self.port)
        return self._connect()

    def close(self, reason="closed"):
        was_connected = self.connected
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass
        self.sock = None
        self.connected = False
        self._rx_buffer = b""
        self._tx_queue = []
        self._tx_stuck_since_ms = None
        self._last_tx_progress_ms = _ms_now()
        if was_connected and self.on_disconnected:
            try:
                self.on_disconnected(reason)
            except Exception:
                pass
        self._next_retry_ms = _ms_add(_ms_now(), self._backoff_ms)
        self._backoff_ms = min(self._max_backoff_ms, self._backoff_ms * 2)

    def _connect(self):
        sock = None
        try:
            addr = socket.getaddrinfo(self.host, self.port)[0][-1]
            sock = socket.socket()
            sock.settimeout(2)
            sock.connect(addr)
            sock.setblocking(False)
        except Exception as e:
            print("[broker] connect fallo:", e)
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
            self.sock = None
            self.connected = False
            self._next_retry_ms = _ms_add(_ms_now(), self._backoff_ms)
            self._backoff_ms = min(self._max_backoff_ms, self._backoff_ms * 2)
            return False

        self.sock = sock
        self.connected = True
        self._rx_buffer = b""
        self._backoff_ms = 500
        self._next_retry_ms = _ms_now()
        self._tx_stuck_since_ms = None
        self._last_tx_progress_ms = _ms_now()
        print("[broker] conectado a", self.host, self.port)
        if self.on_connected:
            try:
                self.on_connected()
            except Exception:
                pass
        return True

    def _flush_tx(self):
        tx_stuck_ms = int(getattr(config, "SOCKET_TX_STUCK_MS", 15000))
        sock = self.sock
        if sock is None:
            return
        while self._tx_queue and self.connected:
            data = self._tx_queue[0]
            try:
                sent = sock.send(data)
                if sent is None:
                    sent = 0
            except OSError as e:
                if _os_would_block(e):
                    now_ms = _ms_now()
                    if self._tx_stuck_since_ms is None:
                        self._tx_stuck_since_ms = now_ms
                    elif _ms_diff(now_ms, self._tx_stuck_since_ms) >= tx_stuck_ms:
                        print("[broker] TX bloqueada >{} ms, reconectando".format(tx_stuck_ms))
                        self.close("tx stuck")
                    return
                print("[broker] send OSError:", e)
                self.close("send OSError")
                return
            except Exception as e:
                print("[broker] send error:", e)
                self.close("send error")
                return

            # En socket no bloqueante, sent==0 suele ser buffer lleno (no cierre).
            if sent <= 0:
                now_ms = _ms_now()
                if self._tx_stuck_since_ms is None:
                    self._tx_stuck_since_ms = now_ms
                elif _ms_diff(now_ms, self._tx_stuck_since_ms) >= tx_stuck_ms:
                    print("[broker] TX sin progreso >{} ms, reconectando".format(tx_stuck_ms))
                    self.close("tx no progress")
                return

            self._tx_stuck_since_ms = None
            self._last_tx_progress_ms = _ms_now()

            if sent < len(data):
                self._tx_queue[0] = data[sent:]
                return
            self._tx_queue.pop(0)

        if not self._tx_queue:
            self._tx_stuck_since_ms = None

    def _drain_rx(self):
        sock = self.sock
        if sock is None:
            return
        while self.connected:
            try:
                chunk = sock.recv(1024)
            except OSError as e:
                if _os_would_block(e):
                    return
                print("[broker] recv OSError:", e)
                self.close("recv OSError")
                return
            except Exception as e:
                print("[broker] recv error:", e)
                self.close("recv error")
                return
            if not chunk:
                self.close("peer closed")
                return
            self._rx_buffer += chunk
            if len(chunk) < 1024:
                break

        while b"\n" in self._rx_buffer:
            raw, self._rx_buffer = self._rx_buffer.split(b"\n", 1)
            if not raw:
                continue
            try:
                msg = json.loads(raw.decode("utf-8"))
            except Exception as e:
                print("[broker] linea JSON invalida:", e)
                continue
            action = msg.get("action")
            cb = self.actions.get(action)
            if cb:
                try:
                    cb(msg)
                except Exception as e:
                    print("[broker] action fallo:", action, e)

    def update(self, now_ms):
        if not self.connected:
            self.ensure(now_ms)
            return
        self._flush_tx()
        self._drain_rx()


class NodePubSub:
    def __init__(self, socket_task, prefix=""):
        self.socket_task = socket_task
        self.prefix = prefix or ""
        self.subscriptions = {}
        self.remote_topics = set()
        socket_task.add_action("PUB", self._handle_pub)
        socket_task.add_action("SUB", self._handle_sub)
        socket_task.on_connected = self._on_connected

    def _full_topic(self, topic):
        return "{}{}".format(self.prefix, topic)

    def _strip_prefix(self, topic):
        if not self.prefix:
            return topic
        if not topic.startswith(self.prefix):
            return None
        return topic[len(self.prefix) :]

    def _on_connected(self):
        for topic in self.remote_topics:
            self.socket_task.queue_json(
                {"action": "SUB", "topic": self._full_topic(topic)}
            )

    def subscribe(self, topic, callback):
        topic = _topic_text(topic)
        callbacks = self.subscriptions.setdefault(topic, [])
        if callback not in callbacks:
            callbacks.append(callback)
        if topic not in self.remote_topics:
            self.remote_topics.add(topic)
            self.socket_task.queue_json(
                {"action": "SUB", "topic": self._full_topic(topic)}
            )
        return True

    def publish(self, topic, data, local=False):
        topic = _topic_text(topic)
        ok = self.socket_task.queue_json(
            {"action": "PUB", "topic": self._full_topic(topic), "data": data}
        )
        if local:
            self._local_publish(topic, data)
        return ok

    def _local_publish(self, topic, data):
        callbacks = self.subscriptions.get(topic, [])
        for callback in callbacks:
            try:
                callback(data)
            except Exception:
                pass

    def _handle_pub(self, msg):
        broker_topic = _topic_text(msg.get("topic", ""))
        local_topic = self._strip_prefix(broker_topic)
        if local_topic is None:
            return
        self._local_publish(local_topic, msg.get("data"))

    def _handle_sub(self, msg):
        del msg


class MeArmHoldTask(Task):
    def __init__(self, scheduler, period_ms=300, priority=5):
        super().__init__(scheduler, period_ms, priority=priority)

    def update(self, now_ms):
        try:
            import mearm_controller

            mearm_controller.maintain_hold(now_ms)
        except Exception:
            pass


class DriveWatchdogTask(Task):
    def __init__(self, scheduler, period_ms=50, priority=4):
        super().__init__(scheduler, period_ms, priority=priority)

    def update(self, now_ms):
        command_handler.tick_drive(now_ms)


class CommandTask(Task):
    def __init__(self, scheduler, node, cmd_topic, priority=3):
        super().__init__(scheduler, period_ms=200, priority=priority)
        self.node = node
        self.cmd_topic = _topic_text(cmd_topic)
        node.subscribe(self.cmd_topic, self._on_command)

    def _on_command(self, data):
        if isinstance(data, dict):
            command_handler.apply_mqtt_payload(data)
            return
        if isinstance(data, (bytes, str)):
            try:
                obj = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
                if isinstance(obj, dict):
                    command_handler.apply_mqtt_payload(obj)
                    return
            except Exception:
                pass
        try:
            import mqtt_commands

            mqtt_commands.handle_message(data)
        except Exception as e:
            print("[cmd] payload invalido:", e)

    def update(self, now_ms):
        del now_ms


class TelemetryTask(Task):
    def __init__(self, scheduler, app, node, topic, period_ms, priority=6):
        super().__init__(scheduler, period_ms, priority=priority)
        self.app = app
        self.node = node
        self.topic = _topic_text(topic)

    def update(self, now_ms):
        payload = telemetry.build_payload(now_ms)
        self.app.last_payload = payload
        self.node.publish(self.topic, payload)
        self.app.state.loop_n += 1


class CameraTask(Task):
    def __init__(self, scheduler, node, topic, period_ms, priority=7):
        super().__init__(scheduler, period_ms, priority=priority)
        self.node = node
        self.topic = _topic_text(topic)
        self._skip_streak = 0

    def update(self, now_ms):
        del now_ms
        sock = self.node.socket_task
        if not sock.connected:
            return
        if sock.tx_backlog() > 0:
            self._skip_streak += 1
            if self._skip_streak % 5 == 1:
                print("[camera] esperando TX (cola={})".format(sock.tx_backlog()))
            return
        self._skip_streak = 0
        try:
            import camera_stream

            gc.collect()
            frame = camera_stream.capture_and_pack(robot_ctl.state.loop_n)
            if frame:
                ok = self.node.publish(self.topic, frame)
                if not ok:
                    print("[camera] publish omitido (RAM/cola)")
                del frame
            gc.collect()
        except MemoryError:
            print("[camera] MemoryError - omitiendo frame")
            gc.collect()
        except Exception as e:
            print("[camera]", e)


class OledTask(Task):
    def __init__(self, scheduler, app, period_ms=600, priority=9):
        super().__init__(scheduler, period_ms, priority=priority)
        self.app = app

    def update(self, now_ms):
        del now_ms
        payload = self.app.last_payload
        if not payload:
            return
        s = self.app.state
        if not (s.hw_on and s.oled_display):
            return
        try:
            sys = payload.get("system", {})
            drv = payload.get("drive", {})
            us = payload.get("ultrasonic", {})
            s.oled_display.update(
                sys.get("battery_pct", 0),
                sys.get("battery_v", 0.0),
                drv.get("direction", "STOP"),
                us.get("distance_cm", 0),
                us.get("zone", ""),
                frame=s.loop_n,
                mearm=payload.get("mearm"),
                broker_ok=s.mqtt_linked,
            )
        except Exception as e:
            print("[oled]", e)


class HeartbeatTask(Task):
    def __init__(self, scheduler, node, topic, period_ms, priority=8):
        super().__init__(scheduler, period_ms, priority=priority)
        self.node = node
        self.topic = _topic_text(topic)

    def update(self, now_ms):
        self.node.publish(
            self.topic,
            {"alive": True, "ts_ms": now_ms, "loop_n": robot_ctl.state.loop_n},
        )


class MainApp:
    def __init__(self):
        self.state = robot_ctl.state
        self.scheduler = Scheduler()
        self.last_payload = None
        self.socket_task = SocketClientTask(
            self.scheduler,
            host=getattr(config, "BROKER_HOST", getattr(config, "MQTT_BROKER", "127.0.0.1")),
            port=getattr(config, "BROKER_PORT", getattr(config, "MQTT_PORT", 5051)),
            period_ms=getattr(config, "SOCKET_POLL_INTERVAL_MS", 20),
            priority=2,
        )
        self.socket_task.on_disconnected = self._on_transport_down
        self.node = NodePubSub(
            self.socket_task, prefix=getattr(config, "TOPIC_PREFIX", "")
        )
        _node_on_connected = self.socket_task.on_connected

        def _on_transport_up():
            self.state.mqtt_linked = True
            self.state.mqtt_client = self.socket_task
            if _node_on_connected:
                _node_on_connected()

        self.socket_task.on_connected = _on_transport_up

        command_handler.bind_config(config)
        CommandTask(
            self.scheduler, self.node, getattr(config, "MQTT_TOPIC_CMD", b"robot/commands")
        )
        DriveWatchdogTask(self.scheduler, period_ms=50)
        MeArmHoldTask(self.scheduler, period_ms=300)
        TelemetryTask(
            self.scheduler,
            self,
            self.node,
            getattr(config, "MQTT_TOPIC", b"robot/telemetry"),
            getattr(config, "PUBLISH_INTERVAL_MS", 1000),
        )

        if getattr(config, "CAMERA_ENABLED", False):
            CameraTask(
                self.scheduler,
                self.node,
                getattr(config, "MQTT_TOPIC_CAMERA", b"robot/camera"),
                getattr(config, "CAMERA_PUBLISH_INTERVAL_MS", 15000),
            )

        OledTask(
            self.scheduler,
            self,
            period_ms=getattr(config, "OLED_UPDATE_INTERVAL_MS", 600),
        )
        HeartbeatTask(
            self.scheduler,
            self.node,
            getattr(config, "TOPIC_HEARTBEAT", b"robot/heartbeat"),
            getattr(config, "HEARTBEAT_INTERVAL_MS", 2000),
        )

    def _on_transport_down(self, reason):
        self.state.mqtt_linked = False
        self.state.mqtt_client = None
        print("[broker] enlace perdido:", reason)

    def _stop_motors(self):
        try:
            import motors_l298n

            motors_l298n.stop()
        except Exception:
            pass

    def setup_hardware(self):
        s = self.state
        if s.hw_ready:
            print("[hw] ya inicializado")
            return True

        hw_on = getattr(config, "HARDWARE_ENABLED", True)
        s.hw_on = hw_on
        telemetry.bind_hardware(hw_on, config if hw_on else None)
        s.oled_display = None

        if hw_on:
            try:
                import hardware
                import oled_display as _oled

                hardware.setup(config)
                s.oled_display = _oled
                s.hw_ready = True
            except Exception as e:
                print("[hw] setup fallo (broker sigue):", e)
                s.hw_on = False
                s.hw_ready = False
                telemetry.bind_hardware(False, None)
        else:
            s.hw_ready = True

        gc.collect()
        return s.hw_ready or not getattr(config, "HARDWARE_ENABLED", True)

    def setup_wifi(self):
        if wifi_manager.is_connected():
            self.state.wifi_linked = True
            return True
        ok = wifi_manager.connect_from_config(config)
        if (
            not ok
            and getattr(config, "WIFI_RECOVER_AFTER_HW", True)
            and self.state.hw_ready
        ):
            ok = wifi_manager.recover_after_peripherals(
                config.WIFI_SSID, config.WIFI_PASS, cfg=config
            )
        if not ok:
            ok = wifi_manager.ensure_from_config(config)
        self.state.wifi_linked = ok
        return ok

    def connect_mqtt(self):
        """Compat: conserva API usada por robot_repl."""
        if not self.setup_wifi():
            print("[broker] sin Wi-Fi")
            return False

        timeout_ms = int(getattr(config, "BROKER_CONNECT_TIMEOUT_MS", 9000))
        t0 = _ms_now()
        while _ms_diff(_ms_now(), t0) < timeout_ms:
            self.socket_task.ensure()
            if self.socket_task.connected:
                self.state.mqtt_linked = True
                self.state.mqtt_client = self.socket_task
                return True
            time.sleep_ms(120)
        print("[broker] timeout conectando")
        self.state.mqtt_linked = False
        self.state.mqtt_client = None
        return False

    def disconnect_mqtt(self):
        self.socket_task.close("manual")
        self.state.mqtt_linked = False
        self.state.mqtt_client = None
        print("[broker] desconectado")

    def run_loop(self):
        s = self.state
        if not s.hw_ready:
            self.setup_hardware()
        if not self.connect_mqtt():
            s.running = False
            return

        gc_every = max(1, int(getattr(config, "GC_INTERVAL", 25)))
        poll_sleep_ms = max(1, int(getattr(config, "SCHEDULER_IDLE_MS", 3)))
        print(
            "[main] simpleBroker runtime host={} port={} topic={}".format(
                getattr(config, "BROKER_HOST", "127.0.0.1"),
                getattr(config, "BROKER_PORT", 5051),
                _topic_text(getattr(config, "MQTT_TOPIC", b"robot/telemetry")),
            )
        )

        while s.running:
            try:
                if s.paused:
                    time.sleep_ms(120)
                    continue
                now_ms = _ms_now()
                if not wifi_manager.is_connected():
                    wifi_manager.ensure_from_config(config)
                self.scheduler.run_once(now_ms)
                if s.loop_n % gc_every == 0:
                    gc.collect()
                time.sleep_ms(self.scheduler.next_sleep_ms(now_ms, poll_sleep_ms))
            except MemoryError:
                print("[main] MemoryError - gc.collect()")
                gc.collect()
            except Exception as e:
                print("[main] loop error:", e)
                self.socket_task.close("loop exception")
                time.sleep_ms(250)

        self.disconnect_mqtt()
        self._stop_motors()
        print("[main] bucle finalizado")
