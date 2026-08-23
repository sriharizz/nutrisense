# NutriSense — Comprehensive Verification & Architecture Report

**Date:** 2026-08-12  
**Scope:** Backend & Frontend Regression Audit, Simulation vs. Real CV Boundary, and Physical Hardware Prerequisites  
**Target Model:** YOLOv8 V4 (`nutrisense_model/v4/weights/best.pt` — **Preserved Untouched**)  
**Active Service:** `http://localhost:8000/`  

---

## 1. COMPONENT CLASSIFICATION: SIMULATED VS. REAL CV

| System Component | Execution Status | Provenance & Operational Details |
|---|---|---|
| **YOLOv8 V4 Object Detector** | **REAL / PROVEN** | Runs live inside `server.py` (`yolo_model`). Evaluates 26 native ingredient classes directly on camera frames via `POST /api/infer`. Model weights (`nutrisense_model/v4/weights/best.pt`) are 100% untouched. |
| **CV Inference Preprocessing** | **REAL / PROVEN** | High-quality JPEG stream (`0.92` quality) + configurable confidence threshold (`CV_CONFIDENCE_THRESHOLD = 0.40`). Legacy `apple->onion` HSV hack completely removed. |
| **Frontend UI & Spatial HUD** | **REAL / PROVEN** | React single-page app (`static/index.html`) streaming webcam frames, spatial clustering (`CLUSTER_PX=130`), Smart Pantry inventory sync, and Nutrient Ledger. |
| **Nutrient Database Engine** | **REAL / PROVEN** | `nutrition_engine.py` calculating exact calories, protein, carbs, and fats using ICMR-NIN IFCT 2017 & USDA reference data. |
| **Weight Telemetry Producer** | **SIMULATED** | `hardware_simulator.py` generates synthetic scale readings (e.g., 320.4g -> 241.7g) over HTTP `POST /api/v1/hardware/weight` to test the state machine without physical scale hardware. |
| **Weight Stabilizer Filter** | **REAL (Logic)** | `weight_stabilizer.py` applies a rolling median noise filter (N=5) and variance thresholding (std_dev <= 0.5g) on incoming weight samples. Tested with mock scale data. |
| **Measurement State Machine** | **REAL (Logic)** | `state_machine.py` governs session states (`TARING` -> `ACTIVE` -> `REMOVAL_COMMITTED`). Fully implemented in backend logic, currently fed simulated weight deltas. |

---

## 2. BACKEND NON-REGRESSION VERIFICATION

All core NutriSense endpoints were verified and confirmed non-broken:

- `GET /api/health` -> `{"status": "ok", "service": "NutriSense API v2.1 (V4 fixes)", "yolo": true}` ✅
- `GET /api/dashboard` -> Returns live pantry inventory, today's log, virtual pot state, and daily totals. ✅
- `GET /api/model-info` -> Confirms 26 native V4 classes loaded, `conf_threshold: 0.40`, `roi_active: false`. ✅
- `POST /api/infer` -> Live frame inference producing bounding boxes and class counts for V4 ingredients. ✅
- `POST /api/detect` -> Fractional pot consumption & pantry deduction logging intact. ✅

---

## 3. FRONTEND UI INTEGRATION VERIFICATION

An automated headless browser subagent inspected `http://localhost:8000/`:

1. **Dashboard Header:** *"NutriSense — CPS Dietary Drift Engine · IEEE Capstone"* loaded.
2. **Live Prep Board:** Camera dropdown, feed toggle, and YOLOv8 status indicators online.
3. **Smart Pantry:** Live stock levels displayed (Onion, Tomato, Carrot, Cucumber, Egg, etc.) with Live Sync indicator.
4. **Nutrient Ledger & Pot Allocation:** Macronutrient ring display (kCal, Protein, Carbs, Fat) and portion controls (1/4, 1/2, Full Pot) operational.

---

## 4. EXACT CHECKLIST REMAINING BEFORE PHYSICAL ESP32 / HARDWARE CONNECTION

Before connecting physical ESP32 + HX711 load cell + ESP32-CAM hardware:

1. **HX711 Load Cell Calibration:**  
   - Determine the physical `CALIBRATION_FACTOR` (raw ADC counts per gram) using a known calibration weight (e.g., 100.0g).
2. **Flash ESP32 Wi-Fi Telemetry Firmware:**  
   - Flash the ESP32 Wi-Fi sketch to POST raw scale weight to `http://<server-ip>:8000/api/v1/hardware/weight` following the `HARDWARE_PROTOCOL.md` specification.
3. **ESP32-CAM Video Stream Integration:**  
   - Configure ESP32-CAM MJPEG stream endpoint or HTTP frame capture handler to feed frames directly to `cv_agent.py` / `server.py`.
4. **Physical Platform Alignment & ROI Setup:**  
   - Mount camera 30-45 cm above cutting board.
   - Set fixed lighting and background to establish baseline spatial coordinates.

---

## 5. SYSTEM ARCHITECTURE DOCUMENTS

All permanent architecture memory documents remain preserved in `docs/`:

- [SYSTEM_AUDIT.md](file:///c:/projects/majorprj/docs/SYSTEM_AUDIT.md)
- [SYSTEM_ARCHITECTURE.md](file:///c:/projects/majorprj/docs/SYSTEM_ARCHITECTURE.md)
- [HARDWARE_PROTOCOL.md](file:///c:/projects/majorprj/docs/HARDWARE_PROTOCOL.md)
- [MEASUREMENT_STATE_MACHINE.md](file:///c:/projects/majorprj/docs/MEASUREMENT_STATE_MACHINE.md)
- [CV_INTEGRATION.md](file:///c:/projects/majorprj/docs/CV_INTEGRATION.md)
- [NUTRITION_ENGINE.md](file:///c:/projects/majorprj/docs/NUTRITION_ENGINE.md)
- [DATABASE_SCHEMA.md](file:///c:/projects/majorprj/docs/DATABASE_SCHEMA.md)
- [API_CONTRACT.md](file:///c:/projects/majorprj/docs/API_CONTRACT.md)
- [FRONTEND_CONTRACT.md](file:///c:/projects/majorprj/docs/FRONTEND_CONTRACT.md)

---

*Report generated on 2026-08-12. No model retraining or architectural modifications will take place without your explicit approval.*
