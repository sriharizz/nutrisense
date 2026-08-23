# NutriSense - System Audit & Architecture Strategy (Phase 0)

**Date:** 2026-08-12  
**Document Path:** [docs/SYSTEM_AUDIT.md](file:///c:/projects/majorprj/docs/SYSTEM_AUDIT.md)  
**Authoritative Reference:** [NutriSense Backend + Hardware Integration Master Engineering Prompt.md](file:///c:/projects/majorprj/NutriSense%20Backend%20+%20Hardware%20Integration%20Master%20Engineering%20Prompt.md)

---

## EXECUTIVE SUMMARY

This audit establishes the technical foundation for the **NutriSense Automatic Removal Measurement Architecture**. The canonical workflow requires:
1. All candidate ingredients placed on the platform.
2. Scale establishes stable starting total mass (e.g., 320.4 g).
3. User removes one ingredient at a time.
4. Computer Vision determines **WHICH** ingredient disappeared.
5. Load-cell hardware determines **HOW MUCH** mass disappeared.
6. Sensor Fusion pairs identity + weight delta -> commits immutable ingredient mass event.
7. Nutrition Engine converts measured mass -> calories and macronutrients based on ICMR-NIN / USDA reference data.

---

## 1. EXISTING ARCHITECTURE INVENTORY

| Subsystem | File Location | Current State & Assessment | Reuse Strategy |
|---|---|---|---|
| **Backend API** | server.py | FastAPI app (v2.1). Loads YOLOv8, manages SQLite nutrisense.db, provides /api/infer, /api/detect, /api/dashboard, /api/model-info. | Reusable core. Must add /api/v1/ routes, WebSocket support, and removal state machine. |
| **CV Agent** | cv_agent.py | OpenCV + YOLO stream agent with spatial clustering (CLUSTER_PX=130), stabilization (STABLE_N=30), and zone tracking. | Reusable clustering & spatial tracking logic. Adapt into clean CV observation producer. |
| **YOLO Model** | nutrisense_model/v4/weights/best.pt | YOLOv8n 26-class baseline model. mAP@50=85.5%. Native support for tomato, onion, carrot, cucumber, egg. | Keep as primary CV engine. Preserved untouched. |
| **Frontend** | static/index.html | React single-page app with live webcam canvas, spatial zone HUD, pantry inventory, and macronutrient pot summary. | Reusable layout. Add WebSocket client for real-time removal events & scale telemetry. |
| **Database** | nutrisense.db | SQLite database with icmr_database, pantry_inventory, live_session, consumption_log. | Expand schema to support devices, measurement_sessions, weight_readings, cv_observations, removal_events. |

---

## 2. PROPOSED MASTER ARCHITECTURE

```
+------------------------+      +------------------------+
|  ESP32 Scale Hardware  |      |  Static Camera / CV    |
|  (Telemetry Producer)  |      | (Observation Producer) |
+-----------+------------+      +-----------+------------+
            | HTTP POST / Telemetry         | Frame Detections
            v                               v
+--------------------------------------------------------+
|                   FastAPI Backend                      |
|  +------------------+        +----------------------+  |
|  | Weight Stabilizer|        | Temporal CV Difference| |
|  +--------+---------+        +----------+-----------+  |
|           |                             |              |
|           +--------------+--------------+              |
|                          v                             |
|              +----------------------+                  |
|              | Sensor Fusion Engine |                  |
|              +----------+-----------+                  |
|                         |                              |
|                         v                              |
|              +----------------------+                  |
|              | Session State Machine|                  |
|              +----------+-----------+                  |
|                         |                              |
|                         v                              |
|              +----------------------+                  |
|              |   Nutrition Engine   |                  |
|              +----------+-----------+                  |
+-------------------------+------------------------------+
                          | WebSocket / JSON
                          v
              +----------------------+
              |  Browser Frontend UI |
              +----------------------+
```

---

## 3. REUSABLE VS. NEW COMPONENTS

### Reusable Components:
- **YOLOv8 V4 Weights:** nutrisense_model/v4/weights/best.pt
- **FastAPI Core App & Static Assets:** server.py, static/index.html
- **Spatial Clustering Logic:** cluster() function from cv_agent.py
- **ICMR Nutritional Base Data:** Seeds in server.py (icmr_database)

### Components Needing Modification:
- **server.py:** Add versioned /api/v1/ routes, WebSocket connection manager, and session orchestrator.
- **static/index.html:** Connect WebSocket feed for live weight updates and automatic removal prompts.

### New Components to Build:
1. **docs/ Markdown Architecture Suite:** (Phase 1 deliverables)
2. **hardware_simulator.py:** Mock ESP32 HTTP telemetry producer (MockWeightDevice).
3. **weight_stabilizer.py:** Moving window + median noise filter & threshold-based stability detector.
4. **temporal_cv_tracker.py:** Before/after frame set-difference calculator with temporal windowing.
5. **sensor_fusion.py:** Multi-signal coordinator pairing stable weight deltas with CV disappearance events.
6. **state_machine.py:** Explicit finite state machine managing session lifecycle.
7. **nutrition_engine.py:** Decoupled calculator for calories & nutrients with data provenance tracking.

---

## 4. DATABASE & HARDWARE COMMUNICATION RECOMMENDATIONS

### Database Recommendation: **Local SQLite**
- Zero-configuration, serverless, transactional ACID compliance.
- Perfect for local/demo deployment with single-device low-concurrency writes.
- Expanded relational schema with foreign key constraints.

### Hardware Communication Contract (ESP32 -> Backend)
- **Protocol:** HTTP POST to /api/v1/hardware/weight
- **Payload Format:** JSON
```json
{
  "device_id": "weight-platform-01",
  "sensor": "hx711",
  "weight_g": 320.4,
  "sequence": 1842,
  "timestamp": "2026-08-12T10:30:15.123Z"
}
```
- **Stability Handling:** Raw weight stream is sent continuously (~10 Hz); backend performs noise filtering and stability detection.

---

## 5. MEASUREMENT STATE MACHINE DESIGN

```
               +----------+
               |   IDLE   |
               +----+-----+
                    | User clicks "Start Session"
                    v
               +----------+
               | TARING   |
               +----+-----+
                    | Scale reads 0.0g stable
                    v
       +------------------------+
       |WAITING_FOR_INITIAL_LOAD|
       +------------+-----------+
                    | Weight > min_threshold (e.g. 50g)
                    v
       +------------------------+
       |INITIAL_WEIGHT_STABLE   | <-- Camera captures "BEFORE" set
       +------------+-----------+
                    | User begins removing ingredient
                    v
       +------------------------+
       |   MEASUREMENT_ACTIVE   |
       +------------+-----------+
                    | Weight drops & CV registers disappearance
                    v
       +------------------------+
       |    REMOVAL_DETECTED    |
       +------------+-----------+
                    | Scale reading stabilizes at new weight
                    v
       +------------------------+
       |   REMOVAL_COMMITTED    | --> Compute delta & assign nutrition
       +------------+-----------+
                    |
           +--------+--------+
           | Remaining items?|
           +───────+-+───────+
          Yes      | | No (Scale near 0g / all items removed)
          +--------+ +--------+
          v                   v
+------------------+  +--------------+
|MEASUREMENT_ACTIVE|  +--------------+
```

---

## 6. PHASED IMPLEMENTATION ROADMAP

| Phase | Description | Deliverable | Status |
|---|---|---|---|
| **Phase 0** | Repository Audit & Strategic Planning | docs/SYSTEM_AUDIT.md | **COMPLETE** |
| **Phase 1** | Architecture & Contract Documents | docs/*.md suite (13 Markdown files) | **NEXT** |
| **Phase 2** | Backend Core & SQLite Schema + Mock Hardware | hardware_simulator.py, state_machine.py | Pending |
| **Phase 3** | CV Interface & Temporal Tracking | temporal_cv_tracker.py | Pending |
| **Phase 4** | Sensor Fusion Engine | sensor_fusion.py | Pending |
| **Phase 5** | Decoupled Nutrition Engine | nutrition_engine.py | Pending |
| **Phase 6** | ESP32 Telemetry Integration | Endpoints & validation | Pending |
| **Phase 7** | Frontend WebSockets & UI Sync | static/index.html WebSocket client | Pending |

---

## 7. DECISIONS REQUIRING HUMAN APPROVAL

```text
DECISION REQUIRED #1:
Option A: Generate all 13 Phase 1 Markdown architecture files in docs/ before writing Python implementation.
Option B: Skip directly to Phase 2 backend coding using an inline architecture plan.
Recommendation: Option A (Follows the Master Engineering Prompt Section 31 to establish long-term project memory).
```
