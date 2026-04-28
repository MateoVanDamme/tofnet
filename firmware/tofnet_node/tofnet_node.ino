// tofnet sensor node — Seeed XIAO ESP32-C3
//
// Advertises as "tofnet-N" over BLE, exposes a single distance characteristic
// with NOTIFY. The PC-side receiver subscribes and aggregates the streams.

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// === CHANGE THIS BEFORE FLASHING EACH CHIP ===
#define NODE_ID 2   // 1, 2, or 3 — must be unique per chip

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

uint32_t readDistanceMm() {
  // TODO: replace with real ToF sensor read.
  // VL53L1X example (using Pololu's library):
  //   VL53L1X sensor; sensor.read(); return sensor.ranging_data.range_mm;
  // For now, return a fake sweeping value so the BLE pipeline can be tested
  // end-to-end before the sensor is wired up.
  return 500 + (millis() / 50) % 4500;
}

void setup() {
  Serial.begin(115200);
  delay(1500);  // give the USB-serial monitor time to attach after reset
  Serial.println("=== tofnet node booting ===");

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

  // Put the name + service UUID in the MAIN advertising packet (not just the
  // scan response). Some BLE stacks (Windows in particular) won't surface the
  // name reliably if it's only in the scan response.
  BLEAdvertising *adv = BLEDevice::getAdvertising();

  // Main advertising packet: flags + name only (well under 31 bytes).
  // Service UUID goes in the scan response so the main packet stays compact.
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
