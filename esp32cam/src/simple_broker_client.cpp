#include "simple_broker_client.h"

SimpleBrokerClient::SimpleBrokerClient() {}

bool SimpleBrokerClient::connect(const char* host, uint16_t port, uint32_t timeoutMs) {
  disconnect();
  Serial.printf("[broker] conectando %s:%u\n", host, port);
  if (!_client.connect(host, port)) {
    Serial.println("[broker] connect fallo");
    return false;
  }
  _client.setNoDelay(true);
  Serial.println("[broker] conectado");
  return true;
}

void SimpleBrokerClient::disconnect() {
  if (_client.connected()) {
    _client.stop();
  }
}

bool SimpleBrokerClient::connected() const {
  return const_cast<WiFiClient&>(_client).connected();
}

bool SimpleBrokerClient::ensureConnected(const char* host, uint16_t port, uint32_t timeoutMs) {
  if (connected()) {
    return true;
  }
  return connect(host, port, timeoutMs);
}

bool SimpleBrokerClient::publishJsonLine(const char* topic, const char* jsonDataObject) {
  if (!connected() || topic == nullptr || jsonDataObject == nullptr) {
    return false;
  }

  _client.print("{\"action\":\"PUB\",\"topic\":\"");
  _client.print(topic);
  _client.print("\",\"data\":");
  _client.print(jsonDataObject);
  _client.print("}\n");

  if (!_client.connected()) {
    Serial.println("[broker] enlace perdido tras PUB");
    return false;
  }
  return true;
}
