/**
 * SISEMB · ESP32-CAM → simpleBroker
 *
 * Publica frames JPEG en robot/camera de forma independiente de la Pico.
 * Protocolo: TCP 5051, línea JSON {"action":"PUB","topic":"...","data":{...}}
 */

#include <Arduino.h>
#include <WiFi.h>
#include "esp_camera.h"
#include "board_pins.h"
#include "simple_broker_client.h"
#include <ArduinoJson.h>
#include "mbedtls/base64.h"

#if __has_include("config.h")
#include "config.h"
#else
#include "config.example.h"
#warning "Copia include/config.example.h a include/config.h con tus credenciales"
#endif

#ifndef BROKER_TOPIC_CAMERA
#define BROKER_TOPIC_CAMERA "robot/camera"
#endif

#ifndef CAMERA_SOURCE
#define CAMERA_SOURCE "esp32cam"
#endif

SimpleBrokerClient gBroker;
uint32_t gFrameId = 0;
uint32_t gLastPublishMs = 0;
uint32_t gLastBrokerAttemptMs = 0;

static bool initCamera() {
  camera_config_t cfg = {};
  cfg.ledc_channel = LEDC_CHANNEL_0;
  cfg.ledc_timer = LEDC_TIMER_0;
  cfg.pin_d0 = CAM_Y2_GPIO_NUM;
  cfg.pin_d1 = CAM_Y3_GPIO_NUM;
  cfg.pin_d2 = CAM_Y4_GPIO_NUM;
  cfg.pin_d3 = CAM_Y5_GPIO_NUM;
  cfg.pin_d4 = CAM_Y6_GPIO_NUM;
  cfg.pin_d5 = CAM_Y7_GPIO_NUM;
  cfg.pin_d6 = CAM_Y8_GPIO_NUM;
  cfg.pin_d7 = CAM_Y9_GPIO_NUM;
  cfg.pin_xclk = CAM_XCLK_GPIO_NUM;
  cfg.pin_pclk = CAM_PCLK_GPIO_NUM;
  cfg.pin_vsync = CAM_VSYNC_GPIO_NUM;
  cfg.pin_href = CAM_HREF_GPIO_NUM;
  cfg.pin_sccb_sda = CAM_SIOD_GPIO_NUM;
  cfg.pin_sccb_scl = CAM_SIOC_GPIO_NUM;
  cfg.pin_pwdn = CAM_PWDN_GPIO_NUM;
  cfg.pin_reset = CAM_RESET_GPIO_NUM;
  cfg.xclk_freq_hz = 20000000;
  cfg.pixel_format = PIXFORMAT_JPEG;
  cfg.frame_size = CAMERA_FRAME_SIZE;
  cfg.jpeg_quality = CAMERA_JPEG_QUALITY;
  cfg.fb_count = 2;
  cfg.grab_mode = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&cfg);
  if (err != ESP_OK) {
    Serial.printf("[camera] init error 0x%x\n", err);
    return false;
  }

  sensor_t* s = esp_camera_sensor_get();
  if (s) {
    s->set_vflip(s, 1);
    s->set_hmirror(s, 0);
  }

  Serial.println("[camera] OK");
  return true;
}

static bool connectWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.printf("[wifi] conectando %s\n", WIFI_SSID);

  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - t0) < 30000) {
    delay(300);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[wifi] FALLO");
    return false;
  }
  Serial.printf("[wifi] OK %s RSSI %d\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  return true;
}

static bool ensureBroker() {
  uint32_t now = millis();
  if (gBroker.connected()) {
    return true;
  }
  if (now - gLastBrokerAttemptMs < BROKER_RECONNECT_MS) {
    return false;
  }
  gLastBrokerAttemptMs = now;
  return gBroker.connect(BROKER_HOST, BROKER_PORT, CAMERA_CONNECT_TIMEOUT_MS);
}

static bool publishFrame(camera_fb_t* fb) {
  if (!fb || fb->format != PIXFORMAT_JPEG) {
    return false;
  }

  size_t b64Max = 4 * ((fb->len + 2) / 3) + 4;
  char* b64 = (char*)malloc(b64Max);
  if (!b64) {
    Serial.println("[cam] sin RAM base64");
    return false;
  }

  size_t olen = 0;
  int rc = mbedtls_base64_encode(
      (unsigned char*)b64, b64Max, &olen, fb->buf, fb->len);
  if (rc != 0) {
    free(b64);
    Serial.printf("[cam] base64 error %d\n", rc);
    return false;
  }
  b64[olen] = '\0';

  size_t cap = olen + 384;
  DynamicJsonDocument doc(cap);
  doc["format"] = "jpeg";
  doc["width"] = fb->width;
  doc["height"] = fb->height;
  doc["data"] = b64;
  doc["ts"] = millis();
  doc["source"] = CAMERA_SOURCE;
  doc["frame_id"] = gFrameId++;

  String payload;
  serializeJson(doc, payload);
  free(b64);

  bool ok = gBroker.publishJsonLine(BROKER_TOPIC_CAMERA, payload.c_str());
  if (ok) {
    Serial.printf(
        "[cam] PUB %s %ux%u jpeg=%u b64=%u\n",
        BROKER_TOPIC_CAMERA,
        fb->width,
        fb->height,
        (unsigned)fb->len,
        (unsigned)payload.length());
  }
  return ok;
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== SISEMB ESP32-CAM broker client ===");

  if (!initCamera()) {
    Serial.println("[fatal] camara no inicia");
  }
  connectWifi();
  ensureBroker();
}

void loop() {
  if (!connectWifi()) {
    delay(2000);
    return;
  }

  if (!ensureBroker()) {
    delay(500);
    return;
  }

  uint32_t now = millis();
  if (now - gLastPublishMs < CAMERA_PUBLISH_INTERVAL_MS) {
    delay(20);
    return;
  }
  gLastPublishMs = now;

  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[cam] fb_get null");
    delay(500);
    return;
  }

  if (!publishFrame(fb)) {
    gBroker.disconnect();
  }
  esp_camera_fb_return(fb);
}
