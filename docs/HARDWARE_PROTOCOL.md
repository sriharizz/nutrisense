# NutriSense — ESP32 Hardware Telemetry Protocol

## 1. Overview
The ESP32 load-cell scale acts as an autonomous HTTP client transmitting raw weight telemetry over Wi-Fi.

## 2. Telemetry Ingestion API
- **Endpoint:** `POST /api/v1/hardware/weight`
- **Content-Type:** `application/json`

## 3. JSON Payload Schema
```json
{
  "device_id": "weight-platform-01",
  "sensor": "hx711",
  "weight_g": 320.4,
  "sequence": 1842,
  "timestamp": "2026-08-12T10:30:15.123Z",
  "status": "ok"
}
```

## 4. Stability Requirements
- Backend applies moving median filter over $N=5$ samples.
- Stability criteria: $	ext{std\_dev} < 0.2	ext{ g}$ over a $1.0	ext{ sec}$ window.
- Outliers or negative values below $-2.0	ext{ g}$ trigger tare warning events.
