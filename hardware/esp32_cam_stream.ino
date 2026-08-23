/*
 * NutriSense — ESP32-CAM Bulletproof Wi-Fi & Streamer Firmware
 * 
 * Hardware: AI Thinker ESP32-CAM module (OV2640 camera)
 * In Arduino IDE:
 *   - Board: "AI Thinker ESP32-CAM"
 *   - Upload Speed: 115200 (or 921600)
 *   - Flash Frequency: 80MHz
 *   - Flash Mode: QIO
 *   - Partition Scheme: Huge APP (3MB No OTA/1MB SPIFFS)
 */

#include "esp_camera.h"
#include <WiFi.h>
#include "esp_timer.h"
#include "img_converters.h"
#include "Arduino.h"
#include "fb_gfx.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include "esp_http_server.h"

// ================================================================
// 1. CONFIGURATION
// ================================================================
const char* WIFI_SSID     = "v";
const char* WIFI_PASSWORD = "erenhari";

// AI Thinker ESP32-CAM Pin Definitions
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

httpd_handle_t stream_httpd = NULL;

static esp_err_t capture_handler(httpd_req_t *req) {
  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) {
    httpd_resp_send_500(req);
    return ESP_FAIL;
  }
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=capture.jpg");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return res;
}

static esp_err_t stream_handler(httpd_req_t *req) {
  camera_fb_t * fb = NULL;
  esp_err_t res = ESP_OK;
  size_t _jpg_buf_len = 0;
  uint8_t * _jpg_buf = NULL;
  char * part_buf[64];

  res = httpd_resp_set_type(req, "multipart/x-mixed-replace; boundary=123456789000000000000987654321");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  if (res != ESP_OK) return res;

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      res = ESP_FAIL;
    } else {
      if (fb->format != PIXFORMAT_JPEG) {
        bool jpeg_converted = frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len);
        esp_camera_fb_return(fb);
        fb = NULL;
        if (!jpeg_converted) res = ESP_FAIL;
      } else {
        _jpg_buf_len = fb->len;
        _jpg_buf = fb->buf;
      }
    }
    if (res == ESP_OK) {
      size_t hlen = snprintf((char *)part_buf, 64, "\r\n--123456789000000000000987654321\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", _jpg_buf_len);
      res = httpd_resp_send_chunk(req, (const char *)part_buf, hlen);
    }
    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
    }
    if (fb) {
      esp_camera_fb_return(fb);
      fb = NULL;
      _jpg_buf = NULL;
    } else if (_jpg_buf) {
      free(_jpg_buf);
      _jpg_buf = NULL;
    }
    if (res != ESP_OK) break;
    delay(20);
  }
  return res;
}

void startCameraServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 81; // Standard stream port

  httpd_uri_t stream_uri = {
    .uri       = "/stream",
    .method    = HTTP_GET,
    .handler   = stream_handler,
    .user_ctx  = NULL
  };

  httpd_uri_t capture_uri = {
    .uri       = "/capture",
    .method    = HTTP_GET,
    .handler   = capture_handler,
    .user_ctx  = NULL
  };

  if (httpd_start(&stream_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &stream_uri);
    httpd_register_uri_handler(stream_httpd, &capture_uri);
    Serial.println("[ESP32-CAM] HTTP Streamer running on port 81!");
  }
}

void setup() {
  WRITE_PERI_REG(RTC_CNTL_BROWNINT_MOD_REG, 0); // Disable brownout detector
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n==========================================");
  Serial.println("     ESP32-CAM Video Streamer             ");
  Serial.println("==========================================");

  // 1. CONNECT TO WI-FI FIRST (Ensures Wi-Fi connects even if camera is finicky)
  Serial.printf("[WiFi] Connecting to: %s\n", WIFI_SSID);
  WiFi.disconnect(true);
  delay(100);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 35) {
    delay(400);
    Serial.print(".");
    tries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] [OK] CONNECTED SUCCESSFULLY!");
    Serial.print("[WiFi] IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.println("------------------------------------------");
    Serial.print("Stream URL:   http://");
    Serial.print(WiFi.localIP());
    Serial.println(":81/stream");
    Serial.print("Snapshot URL: http://");
    Serial.print(WiFi.localIP());
    Serial.println(":81/capture");
    Serial.println("------------------------------------------");
  } else {
    Serial.println("\n[WiFi] [FAIL] Could not connect to hotspot!");
    Serial.println("Check: 1) AP Band is 2.4 GHz, 2) Hotspot SSID is 'v', 3) Password is 'erenhari'");
  }

  // 2. INITIALIZE CAMERA SENSOR
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_siod = SIOD_GPIO_NUM;
  config.pin_sioc = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size = FRAMESIZE_SVGA; // 800x600 HD // 640x480
    config.jpeg_quality = 8; // High Quality Crisp HD
    config.fb_count = 2;
    Serial.println("[Camera] PSRAM found! High quality mode enabled.");
  } else {
    config.frame_size = FRAMESIZE_QVGA; // 320x240 for reliability
    config.jpeg_quality = 12;
    config.fb_count = 1;
    Serial.println("[Camera] PSRAM not detected, standard mode enabled.");
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[Camera] [ERROR] Camera init failed: 0x%x\n", err);
    Serial.println("Check camera ribbon cable connection!");
    return;
  }
  Serial.println("[Camera] [OK] Camera sensor initialized!");

  // 3. START HTTP SERVER
  startCameraServer();
}

void loop() {
  // Auto-reconnect Wi-Fi if dropped
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Lost connection, reconnecting...");
    WiFi.reconnect();
    delay(5000);
  }
  delay(1000);
}
