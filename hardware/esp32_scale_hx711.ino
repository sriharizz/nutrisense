/*
 * NutriSense — ESP32 + Single HX711 Ultra-Smooth & Non-Fluctuating Firmware
 * 
 * Hardware Wiring:
 *   HX711 VCC -> 5V or 3.3V
 *   HX711 GND -> GND
 *   HX711 DT  -> GPIO 16 (DOUT)
 *   HX711 SCK -> GPIO 4  (CLK)
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "HX711.h"

// ================= CONFIGURATION =================
const char* WIFI_SSID     = "vivo27";
const char* WIFI_PASSWORD = "erenhari";

// Laptop IP running server.py
const char* SERVER_IP     = "10.126.26.230";
const int   SERVER_PORT   = 8000;

// Pins
const int DOUT_PIN = 16;
const int SCK_PIN  = 4;

// Calibration factor
float CALIBRATION_FACTOR = 93.3; 

HX711 scale;
unsigned long sequenceNumber = 0;
String endpointUrl;

float lastValidWeight = 0.0;
int zeroCount = 0;

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n==========================================");
  Serial.println("[NutriSense] Single HX711 Scale Starting...");
  Serial.println("==========================================");

  endpointUrl = "http://" + String(SERVER_IP) + ":" + String(SERVER_PORT) + "/api/v1/hardware/weight";

  scale.begin(DOUT_PIN, SCK_PIN);
  
  if (scale.wait_ready_timeout(1500)) {
    scale.set_scale(CALIBRATION_FACTOR);
    scale.tare(10);
    Serial.println("[NutriSense] [OK] Scale ready and tared!");
  } else {
    Serial.println("[NutriSense] [WARNING] HX711 not responding! Check DT (GPIO 16) and SCK (GPIO 4) wiring.");
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[NutriSense] [OK] Wi-Fi Connected! IP: " + WiFi.localIP().toString());
  }
}

void loop() {
  if (Serial.available() > 0) {
    char c = Serial.read();
    if (c == 't' || c == 'T') {
      Serial.println("[TARE] Re-taring scale...");
      scale.tare(10);
      lastValidWeight = 0.0;
    }
  }

  if (scale.wait_ready_timeout(100)) {
    float raw = scale.get_units(3);
    
    if (raw < 0.5) {
      zeroCount++;
      if (zeroCount > 3) {
        lastValidWeight = 0.0;
      }
    } else {
      zeroCount = 0;
      lastValidWeight = raw;
    }
    
    float displayWeight = round(lastValidWeight * 10.0) / 10.0;

    Serial.printf("Live Weight: %.1f g\n", displayWeight);

    if (WiFi.status() == WL_CONNECTED) {
      HTTPClient http;
      http.begin(endpointUrl);
      http.addHeader("Content-Type", "application/json");
      http.setTimeout(500);

      String payload = "{\"device_id\":\"esp32-scale\",\"weight_g\":" + String(displayWeight, 1) + ",\"sequence\":" + String(++sequenceNumber) + "}";
      int code = http.POST(payload);
      http.end();
    }
  }

  delay(200);
}
