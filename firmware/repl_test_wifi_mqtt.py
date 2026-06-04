# Prueba rapida desde REPL (sin esperar boot.py):
#   >>> import repl_test_wifi_mqtt
#   >>> repl_test_wifi_mqtt.run()

import gc
import json
import time

import config
import wifi_manager


def run(publish_once=True):
    gc.collect()
    print("[test] SSID:", config.WIFI_SSID)
    if not wifi_manager.connect(config.WIFI_SSID, config.WIFI_PASS, cfg=config):
        print("[test] Wi-Fi FALLO")
        return False
    print("[test] Wi-Fi OK", wifi_manager.get_rssi())

    try:
        import socket

        ai = socket.getaddrinfo(config.MQTT_BROKER, config.MQTT_PORT)[0][-1]
        s = socket.socket()
        s.settimeout(8)
        s.connect(ai)
        s.close()
        print("[test] TCP", config.MQTT_BROKER, config.MQTT_PORT, "OK")
    except Exception as e:
        print("[test] TCP FALLO:", e)
        return False

    from umqtt.simple import MQTTClient

    import telemetry

    telemetry.bind_hardware(False, None)
    client = MQTTClient(
        client_id=config.MQTT_CLIENT_ID,
        server=config.MQTT_BROKER,
        port=config.MQTT_PORT,
        keepalive=config.MQTT_KEEPALIVE,
    )
    try:
        client.connect()
        print("[test] MQTT conectado")
        if publish_once:
            payload = telemetry.build_payload(time.ticks_ms())
            client.publish(config.MQTT_TOPIC, json.dumps(payload))
            print("[test] publicado en", config.MQTT_TOPIC)
        client.disconnect()
        print("[test] OK — abre el dashboard y busca PICO ONLINE")
        return True
    except OSError as e:
        print("[test] MQTT FALLO:", e)
        return False
