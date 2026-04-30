/*
  TF-Luna LiDAR Test Script
  tf-luna-esp32-i2c.ino
  Demonstrates operation of TF-Luna LiDAR ToF Sensor
  Displays distance, signal strength and chip temperature
  Uses TF-Luna in I2C mode
  DroneBot Workshop 2025
  https://dronebotworkshop.com
*/

// Include Wire Library for I2C operations
#include <Wire.h>

// Define I2C Connections (edit as required)
#define I2C_SDA 17
#define I2C_SCL 16

// Define communications parameters
#define I2C_ADDRESS 0x10  // TF-Luna I2C address
#define COMMAND 0x00      // Order
#define DATA_LENGTH 9     // Data length

// Command packet sent to TF-Luna to trigger a single measurement.
// 0x5A = Start byte
// 0x05 = Command ID: “take one reading”
// 0x00 = Low byte of register/count address (unused here, set to 0)
// 0x01 = Number of measurements requested (1)
// 0x60 = Checksum (0x5A + 0x05 + 0x00 + 0x01 = 0x60)
unsigned char buf1[] = { 0x5A, 0x05, 0x00, 0x01, 0x60 };

void setup() {

  // Initialize I2C
  Wire.begin(I2C_SDA, I2C_SCL);

  // Initialize Serial port
  Serial.begin(115200);
  Serial.print("TF-Luna Ready");
}

void loop() {

  // Start I2C Data Transmission
  Wire.beginTransmission(I2C_ADDRESS);
  // Send Instructions
  Wire.write(buf1, 5);
  // End I2C Data Transmission
  Wire.endTransmission();

  // Request data from TF-Luna
  Wire.requestFrom(I2C_ADDRESS, DATA_LENGTH);
  // Create array to hold data
  uint8_t data[DATA_LENGTH] = { 0 };
  // Variables for distance, signal strength and chip temperature
  uint16_t distance = 0;
  uint16_t strength = 0;
  int16_t temperature = 0;
  // Checksum and index variables
  int checksum = 0;
  int index = 0;

  // Read data into array
  while (Wire.available() > 0 && index < DATA_LENGTH) {
    data[index++] = Wire.read();
  }
  // If data is complete then extract values
  if (index == DATA_LENGTH) {
    distance = data[2] + data[3] * 256;     //  Distance
    strength = data[4] + data[5] * 256;     // Signal strength
    temperature = data[6] + data[7] * 256;  // Chip temperature

    // Print values to Serial Monitor
    Serial.print("Distance: ");
    Serial.print(distance);
    Serial.print(" cm, Signal Strength: ");
    Serial.print(strength);
    Serial.print(", Chip Temperature: ");
    Serial.print(temperature / 8.0 - 256.0);
    Serial.println(" C");
  }
  // Short delay for TF-Luna
  delay(10);
}