# Prueba rapida: captura + pack + un publish MQTT en robot/camera.
# REPL: import repl_test_camera; repl_test_camera.run()

import json
import time


def run():
    import config
    import wifi_manager
    import hardware
    import ov7670
    import camera_stream
    from umqtt.simple import MQTTClient

    print("[test_cam] init hardware...")
    hardware.setup(config)
    st = ov7670.get_status()
    print("[test_cam] ov7670", st)

    if not wifi_manager.connect(config.WIFI_SSID, config.WIFI_PASS, cfg=config):
        print("[test_cam] Wi-Fi fallo")
        return False

    payload = camera_stream.capture_and_pack(0)
    if not payload:
        print("[test_cam] sin frame (stub=", ov7670.is_stub_mode(), " publish_stub=", getattr(config, "CAMERA_PUBLISH_STUB", False), ")")
        return False

    print("[test_cam] frame", payload.get("format"), payload.get("width"), "x", payload.get("height"), "src=", payload.get("source"))

    client = MQTTClient(
        client_id=b"test-cam",
        server=config.MQTT_BROKER,
        port=config.MQTT_PORT,
        keepalive=30,
    )
    client.connect()
    topic = getattr(config, "MQTT_TOPIC_CAMERA", b"robot/camera")
    msg = json.dumps(payload)
    client.publish(topic, msg)
    client.disconnect()
    print("[test_cam] publicado en", topic, "bytes", len(msg))
    return True
