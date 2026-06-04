#pragma once

#include <Arduino.h>
#include <WiFiClient.h>

/** Cliente TCP simpleBroker: una línea JSON por mensaje (PUB/SUB). */
class SimpleBrokerClient {
 public:
  SimpleBrokerClient();

  bool connect(const char* host, uint16_t port, uint32_t timeoutMs = 8000);
  void disconnect();
  bool connected() const;
  bool ensureConnected(const char* host, uint16_t port, uint32_t timeoutMs = 8000);

  /** Publica payload JSON en topic (objeto anidado en "data"). */
  bool publishJsonLine(const char* topic, const char* jsonDataObject);

 private:
  WiFiClient _client;
};
