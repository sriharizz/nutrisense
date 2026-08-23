# NutriSense — Physical Hardware & ESP32 Integration Guide

This guide walks you through connecting your physical **ESP32 Load-Cell Scale** and **ESP32-CAM Camera** to the running NutriSense backend.

---

## STEP 1: ESP32 + HX711 Load-Cell Scale Setup

### 1. Hardware Wiring Diagram

```text
  HX711 Module               ESP32 Microcontroller
+--------------+           +------------------------+
|     VCC      | --------> |  5V / 3.3V             |
|     GND      | --------> |  GND                   |
|  DT (DOUT)   | --------> |  GPIO 16               |
|  SCK (CLK)   | --------> |  GPIO 4                |
+--------------+           +------------------------+
```

### 2. Flashing the Scale Firmware
1. Open `hardware/esp32_scale_hx711.ino` in **Arduino IDE**.
2. Install libraries via **Sketch -> Include Library -> Manage Libraries**:
   - Search & install **`HX711 Arduino Library`** (by Bogde)
   - Search & install **`ArduinoJson`** (by Benoit Blanchon)
3. Edit credentials in `esp32_scale_hx711.ino`:
   ```cpp
   const char* WIFI_SSID     = "Your_WiFi_Name";
   const char* WIFI_PASSWORD = "Your_WiFi_Password";
   const char* SERVER_IP     = "192.168.x.x"; // Your PC's Local IP Address!
   ```
4. Find your PC's IP address in PowerShell:
   ```powershell
   ipconfig
   # Look for "IPv4 Address" (e.g., 192.168.1.105)
   ```
5. Select Board **ESP32 Dev Module**, select your COM port, and click **Upload**.

---

## STEP 2: ESP32-CAM Camera Setup

### 1. Flashing the Camera Firmware
1. Open `hardware/esp32_cam_stream.ino` in **Arduino IDE**.
2. Select Board **AI Thinker ESP32-CAM**.
3. Edit credentials in `esp32_cam_stream.ino`:
   ```cpp
   const char* WIFI_SSID     = "Your_WiFi_Name";
   const char* WIFI_PASSWORD = "Your_WiFi_Password";
   ```
4. Flash the code, open Serial Monitor at `115200` baud, and press the Reset button on the ESP32-CAM.
5. Note down the MJPEG Stream URL printed in Serial Monitor:
   ```text
   [ESP32-CAM] MJPEG Stream URL: http://192.168.1.50/stream
   ```

---

## STEP 3: Connecting Both Hardware Units to NutriSense

1. **Start Backend Server:**
   Make sure server.py is running on port 8000:
   ```powershell
   python -m uvicorn server:app --host 0.0.0.0 --port 8000
   ```

2. **Power On ESP32 Scale:**
   - As soon as the ESP32 scale powers on and connects to Wi-Fi, it will automatically start sending HTTP POST requests to `http://<SERVER_IP>:8000/api/v1/hardware/weight`.
   - The backend terminal will output:
     ```text
     [StateMachine] Transition: TARING -> WAITING_FOR_INITIAL_LOAD
     ```

3. **Connect ESP32-CAM to Browser UI:**
   - Open [http://localhost:8000/](http://localhost:8000/) in Chrome/Edge.
   - In the **Live Prep Board** camera selection dropdown, select **"IP Camera / ESP32-CAM"** or enter `http://192.168.1.50/stream`.
   - Click **Start Feed**.

4. **Run Live Removal Session:**
   - Place all ingredients (Tomato, Onion, Cucumber) on the load-cell scale platform.
   - The system establishes the total initial mass (e.g. 320.4g).
   - Remove one ingredient (e.g., Tomato).
   - ESP32 scale transmits new weight (241.7g); ESP32-CAM observes Tomato disappearance.
   - Backend automatically commits: **Tomato = 78.7 g** and calculates ICMR nutrition!

---

## STEP 4: HX711 Load Cell Calibration (Optional)

If your scale readings are inaccurate:
1. Place a known calibration weight (e.g., 100.0g) on the load cell.
2. In `esp32_scale_hx711.ino`, adjust `CALIBRATION_FACTOR`:
   - If scale reads TOO HIGH: Increase `CALIBRATION_FACTOR`
   - If scale reads TOO LOW: Decrease `CALIBRATION_FACTOR`
3. Re-upload the sketch.
