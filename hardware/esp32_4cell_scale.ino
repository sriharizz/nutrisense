#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <Update.h>
#include "HX711.h"

// ================================================================
// 1. CONFIGURATION
// ================================================================
const char* ssid        = "vivo27";
const char* password    = "erenhari";
const char* SERVER_IP   = "10.126.26.230"; // THIS LAPTOP'S IP
const int   SERVER_PORT = 8000;
float BASE_FACTOR       = -900.774; 

// ================================================================
// 2. PIN MAPPINGS FOR 4 LOAD CELLS
// ================================================================
const int DT1_PIN  = 13; const int SCK1_PIN = 12; // Scale 1
const int DT2_PIN  = 15; const int SCK2_PIN = 16; // Scale 2
const int DT3_PIN  = 4;  const int SCK3_PIN = 5;  // Scale 3
const int DT4_PIN  = 19; const int SCK4_PIN = 21; // Scale 4

HX711 scale1, scale2, scale3, scale4;
WebServer server(80);

float smoothedWeight = 0.0;
const float ZERO_DEADBAND = 1.0;
const float EMA_ALPHA     = 0.40;
unsigned long seqNumber   = 0;
String endpointUrl;

// Function to zero out all available scales (Non-blocking)
void zeroAllScales() {
  Serial.println("\n[TARE] Zeroing available load cells... Please do not touch platform.");
  if (scale1.is_ready()) scale1.tare(10);
  if (scale2.is_ready()) scale2.tare(10);
  if (scale3.is_ready()) scale3.tare(10);
  if (scale4.is_ready()) scale4.tare(10);
  smoothedWeight = 0.0;
  Serial.println("[TARE] Complete! Platform is set to 0.0g.\n");
}

// OTA Update Page HTML
const char* updateIndex = 
  "<form method='POST' action='/update' enctype='multipart/form-data'>"
  "<h2>ESP32 Wireless Code Flasher</h2>"
  "<input type='file' name='update'>"
  "<input type='submit' value='Flash Code Wirelessly'>"
  "</form>";

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println("\n==========================================");
  Serial.println("     ESP32 Scale (Non-Blocking Mode)      ");
  Serial.println("==========================================");

  endpointUrl = "http://" + String(SERVER_IP) + ":" + String(SERVER_PORT) + "/api/v1/hardware/weight";
  Serial.println("[NutriSense] Target: " + endpointUrl);

  // Initialize HX711s
  scale1.begin(DT1_PIN, SCK1_PIN);
  scale2.begin(DT2_PIN, SCK2_PIN);
  scale3.begin(DT3_PIN, SCK3_PIN);
  scale4.begin(DT4_PIN, SCK4_PIN);

  scale1.set_scale(BASE_FACTOR);
  scale2.set_scale(BASE_FACTOR);
  scale3.set_scale(BASE_FACTOR);
  scale4.set_scale(BASE_FACTOR);

  // Connect to Hotspot
  Serial.print("Connecting to Hotspot");
  WiFi.begin(ssid, password);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(300);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Connected! IP: " + WiFi.localIP().toString());
  } else {
    Serial.println("\n[WiFi] Not connected. Running offline mode.");
  }

  // Non-blocking quick tare
  delay(400);
  zeroAllScales();

  // Setup OTA Server
  server.on("/update", HTTP_GET, []() {
    server.sendHeader("Connection", "close");
    server.send(200, "text/html", updateIndex);
  });

  server.on("/update", HTTP_POST, []() {
    server.sendHeader("Connection", "close");
    server.send(200, "text/plain", (Update.hasError()) ? "UPDATE FAILED" : "SUCCESS! Rebooting...");
    ESP.restart();
  }, []() {
    HTTPUpload& upload = server.upload();
    if (upload.status == UPLOAD_FILE_START) {
      Update.begin(UPDATE_SIZE_UNKNOWN);
    } else if (upload.status == UPLOAD_FILE_WRITE) {
      Update.write(upload.buf, upload.currentSize);
    } else if (upload.status == UPLOAD_FILE_END) {
      Update.end(true);
    }
  });

  server.begin();
  Serial.println("Tip: Type 't' in the Serial Monitor anytime to re-tare/zero.");
  Serial.println("------------------------------------------------------------\n");
}

void loop() {
  server.handleClient();

  // Check if user sent 't' or 'T' in Serial Monitor to re-tare
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    if (cmd == 't' || cmd == 'T') {
      zeroAllScales();
    }
  }

  // Read each cell individually without blocking
  float w1 = scale1.is_ready() ? scale1.get_units(2) : 0.0;
  float w2 = scale2.is_ready() ? scale2.get_units(2) : 0.0;
  float w3 = scale3.is_ready() ? scale3.get_units(2) : 0.0;
  float w4 = scale4.is_ready() ? scale4.get_units(2) : 0.0;

  float rawTotal = w1 + w2 + w3 + w4;

  if (abs(rawTotal) < 20000.0) {
    smoothedWeight = (EMA_ALPHA * rawTotal) + ((1.0 - EMA_ALPHA) * smoothedWeight);
  }

  float displayWeight = smoothedWeight;
  if (abs(displayWeight) < ZERO_DEADBAND) displayWeight = 0.0;

  // Print individual corner breakdown + total
  Serial.printf("C1: %5.1fg | C2: %5.1fg | C3: %5.1fg | C4: %5.1fg  ==>  TOTAL: %5.1fg\n",
                w1, w2, w3, w4, displayWeight);

  // ================================================================
  // TRANSMIT TO NUTRISENSE BACKEND (Always runs)
  // ================================================================
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(endpointUrl);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(400);

    String payload = "{\"device_id\":\"esp32-scale\",\"weight_g\":" + String(displayWeight, 1) + ",\"sequence\":" + String(++seqNumber) + "}";
    int httpCode = http.POST(payload);
    http.end();
  }

  delay(200);
}
