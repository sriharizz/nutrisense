# NutriSense — System Architecture Specification

## 1. Overview
The NutriSense System Architecture defines the real-time Cyber-Physical integration between:
- ESP32 Load-Cell Telemetry Scale (Mass Measurement)
- Static Camera / YOLOv8 CV Agent (Ingredient Identity)
- FastAPI Sensor Fusion & Measurement State Machine
- ICMR-NIN / USDA Nutrition Engine
- Real-Time Browser WebSocket & REST Frontend

## 2. Structural Layer Diagram
```text
+-----------------------------------------------------------------------+
|                           CLIENT LAYER                                |
|  React 18 + Tailwind Single-Page Frontend (WebSocket + REST API)       |
+-----------------------------------▲-----------------------------------+
                                    │ WebSockets / HTTP REST
+-----------------------------------▼-----------------------------------+
|                           APPLICATION LAYER                           |
|  FastAPI App (v2.1)                                                   |
|  ├── Session Orchestrator & State Machine                              |
|  ├── Weight Noise Filter & Stability Detector                         |
|  ├── Temporal CV Difference Engine                                    |
|  ├── Sensor Fusion Coordinator                                         |
|  └── Nutrition Calculation Engine                                     |
+-----------------------------------▲-----------------------------------+
                                    │ Internal In-Memory Event Bus
+-----------------------------------▼-----------------------------------+
|                            DATA LAYER                                 |
|  Local SQLite DB (nutrisense.db) - Normalized relational schema        |
+-----------------------------------▲-----------------------------------+
                                    │ HTTP Telemetry / Camera Frames
+-----------------------------------┴-----------------------------------+
|                          HARDWARE & SENSORS                           |
|  1. ESP32 + HX711 Load Cell Platform (Weight stream @ 10 Hz)          |
|  2. Static Camera / YOLOv8 CV Inference Engine                        |
+-----------------------------------------------------------------------+
```

## 3. Core Component Responsibilities
- **CV Subsystem:** Answers *"WHICH ingredient was removed?"* via temporal set-difference.
- **Load-Cell Subsystem:** Answers *"HOW MUCH mass changed?"* via stable delta calculation.
- **Sensor Fusion:** Coordinates event synchronization between identity and weight.
- **State Machine:** Governs session state transitions safely without false commits.
