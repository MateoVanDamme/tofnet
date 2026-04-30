// tofnet sensor node WITH real ToF sensor — Seeed XIAO ESP32-C3 + TF-Luna LiDAR
//
// Same BLE behaviour as tofnet_node, but replaces the fake distance generator
// with a real reading from a TF-Luna sensor over I2C.
//
// TF-Luna I2C trigger packet and 9-byte frame parsing adapted from:
//   DroneBot Workshop — "TF-Luna LiDAR" (https://dronebotworkshop.com/tf-luna-lidar/)
// No explicit license stated upstream; see README "Credits" section.

#include <Wire.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// === CHANGE THIS BEFORE FLASHING EACH CHIP ===
#define NODE_ID 1   // 1, 2, or 3 — must be unique per chip

// XIAO ESP32-C3 default I2C pins: SDA = D4 (GPIO 6), SCL = D5 (GPIO 7).
// Wire SDA → D4, SCL → D5, plus 5V and GND on the TF-Luna.
#define I2C_SDA 6
#define I2C_SCL 7

// TF-Luna mode-select pin: LOW at boot = I2C, floating/HIGH = UART (default).
// Drive this LOW from D6 (GPIO 21) and connect it to the TF-Luna's config pin.
#define TFLUNA_MODE_PIN D6

// TF-Luna I2C protocol.
#define TFLUNA_ADDR      0x10
#define TFLUNA_FRAME_LEN 9
// Trigger packet: start, "take one reading", count low, count, checksum.
static const uint8_t TFLUNA_TRIGGER[5] = { 0x5A, 0x05, 0x00, 0x01, 0x60 };

#define SERVICE_UUID        "c91a1000-7bf3-4f6e-9e1a-8d4b6f1c2a01"
#define CHAR_DISTANCE_UUID  "c91a1001-7bf3-4f6e-9e1a-8d4b6f1c2a01"

#define MEASUREMENT_INTERVAL_MS 5000

BLECharacteristic *distanceChar = nullptr;
bool clientConnected = false;

class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer*) override { clientConnected = true; }
  void onDisconnect(BLEServer*) override {
    clientConnected = false;
    BLEDevice::startAdvertising();  // re-advertise so PC can reconnect
  }
};

// Read distance from TF-Luna over I2C. Returns mm, or 0 on read failure.
// The TF-Luna reports distance in cm; we scale to mm to match the BLE protocol.
uint32_t readDistanceMm() {
  Wire.beginTransmission(TFLUNA_ADDR);
  Wire.write(TFLUNA_TRIGGER, sizeof(TFLUNA_TRIGGER));
  Wire.endTransmission();

  Wire.requestFrom(TFLUNA_ADDR, TFLUNA_FRAME_LEN);
  uint8_t data[TFLUNA_FRAME_LEN] = { 0 };
  int n = 0;
  while (Wire.available() > 0 && n < TFLUNA_FRAME_LEN) {
    data[n++] = Wire.read();
  }
  if (n != TFLUNA_FRAME_LEN) return 0;

  uint16_t distance_cm = data[2] | (uint16_t(data[3]) << 8);
  return uint32_t(distance_cm) * 10;
}

void setup() {
  // Force the TF-Luna into I2C mode before anything else — it samples this pin
  // at boot. Must be LOW from the moment the sensor powers up.
  pinMode(TFLUNA_MODE_PIN, OUTPUT);
  digitalWrite(TFLUNA_MODE_PIN, LOW);

  Serial.begin(115200);
  delay(1500);  // give the USB-serial monitor time to attach after reset
  Serial.println("=== tofnet sensor node booting ===");
  Serial.printf("TF-Luna mode pin: GPIO%d held LOW (I2C)\n", TFLUNA_MODE_PIN);

  Wire.begin(I2C_SDA, I2C_SCL);
  Serial.printf("I2C: SDA=GPIO%d SCL=GPIO%d\n", I2C_SDA, I2C_SCL);

  char deviceName[16];
  snprintf(deviceName, sizeof(deviceName), "tofnet-%d", NODE_ID);
  Serial.printf("NODE_ID=%d  name='%s'\n", NODE_ID, deviceName);

  BLEDevice::init(deviceName);
  BLEDevice::setPower(ESP_PWR_LVL_P9);  // max TX power
  Serial.printf("BLEDevice::init OK, MAC=%s\n", BLEDevice::getAddress().toString().c_str());

  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());

  BLEService *service = server->createService(SERVICE_UUID);
  distanceChar = service->createCharacteristic(
    CHAR_DISTANCE_UUID,
    BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
  );
  distanceChar->addDescriptor(new BLE2902());  // required for notifications
  service->start();
  Serial.println("service started");

  // Main advertising packet: flags + name. Service UUID in scan response so
  // the main packet stays well under the 31-byte limit.
  BLEAdvertising *adv = BLEDevice::getAdvertising();

  BLEAdvertisementData advData;
  advData.setFlags(0x06);  // LE general discoverable, BR/EDR not supported
  advData.setName(deviceName);
  adv->setAdvertisementData(advData);

  BLEAdvertisementData scanResp;
  scanResp.setCompleteServices(BLEUUID(SERVICE_UUID));
  adv->setScanResponseData(scanResp);

  adv->setMinInterval(0x20);  // 20 ms
  adv->setMaxInterval(0x40);  // 40 ms

  BLEDevice::startAdvertising();
  Serial.printf("ADVERTISING as '%s' (service %s)\n", deviceName, SERVICE_UUID);
}

void loop() {
  uint32_t distance_mm = readDistanceMm();
  distanceChar->setValue((uint8_t*)&distance_mm, sizeof(distance_mm));
  if (clientConnected) {
    distanceChar->notify();
  }
  Serial.printf("d = %u mm (connected=%d)\n", distance_mm, clientConnected);
  delay(MEASUREMENT_INTERVAL_MS);
}
