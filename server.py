# Shared live telemetry dictionary
HW_TELEMETRY = {"live_weight_g": 0.0, "last_seq": 0}
last_inferred_classes = []
last_zones_cache = []
latest_measured_weight = 0.0
from PIL import Image
import io
import base64
import threading
"""
NutriSense Main FastAPI Server & Measurement Orchestration Layer
Integrates ESP32 load-cell telemetry, static camera YOLOv8 vision, temporal scene difference tracking,
18-state measurement lifecycle, sensor-fusion removal commits, and ICMR-NIN nutrition calculations.
"""
import os
import io
import time
import json
import base64
import asyncio
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Set, Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Response
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from ultralytics import YOLO
import cv2
import numpy as np
import requests

import database
from state_machine import SessionStateMachine, SessionState
from weight_stabilizer import WeightStabilizer
from temporal_cv import TemporalCVTracker
from sensor_fusion import SensorFusionCoordinator, MassReconciliationEngine
from nutrition_engine import NutritionEngine

app = FastAPI(title="NutriSense API", version="3.0 - Automatic Measurement Engine")

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# 1. Initialize Subsystems
database.init_database()
weight_stabilizer = WeightStabilizer(window_size=5, std_threshold=0.5, min_stable_sec=0.05)
temporal_cv = TemporalCVTracker(window_size=5, min_stable_frames=3, conf_threshold=0.40)
sensor_fusion = SensorFusionCoordinator(min_mass_delta_g=8.0, min_cv_confidence=0.40)
nutrition_engine = NutritionEngine(db_path="nutrisense.db")
active_session = SessionStateMachine(session_id="session-init")
class HardwareTelemetryState:
    live_weight_g: float = 0.0
    sequence: int = 0
    device_id: str = "esp32-scale"
    last_packet_time: float = 0.0

hw_state = HardwareTelemetryState()


# 2. YOLO Model Initialization
_V5_WEIGHTS = "nutrisense_model/v5/weights/best.pt"
_V4_WEIGHTS = "nutrisense_model/v4/weights/best.pt"

try:
    if os.path.exists(_V5_WEIGHTS):
        model = YOLO(_V5_WEIGHTS)
        print(f"[NutriSense] [OK] Loaded Domain-Adapted V5 Model: {_V5_WEIGHTS}")
    elif os.path.exists(_V4_WEIGHTS):
        model = YOLO(_V4_WEIGHTS)
        print(f"[NutriSense] [OK] Loaded Base V4 Model: {_V4_WEIGHTS}")
    else:
        model = YOLO("yolov8n.pt")
        print("[NutriSense] [WARN] Fallback to standard yolov8n.pt")
except Exception as e:
    print(f"[NutriSense] [ERROR] Could not load YOLO model: {e}")
    model = None

# WebSocket Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead_conns = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_conns.append(connection)
        for d in dead_conns:
            self.disconnect(d)

ws_manager = ConnectionManager()

# Request Models
class WeightTelemetryRequest(BaseModel):
    device_id: str = "esp32-loadcell-01"
    weight_g: Optional[float] = None
    weight: Optional[float] = None
    grams: Optional[float] = None
    load: Optional[float] = None
    val: Optional[float] = None
    sequence: Optional[int] = None
    status: Optional[str] = "ok"

    def get_effective_weight(self) -> float:
        for candidate in [self.weight_g, self.weight, self.grams, self.load, self.val]:
            if candidate is not None:
                return float(candidate)
        return 0.0

class InferRequest(BaseModel):
    frame: str  # Base64 encoded JPEG
    conf_threshold: Optional[float] = 0.40

# --- REST ENDPOINTS ---

@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "NutriSense Automatic Measurement Engine v3.0",
        "yolo": model is not None,
        "session_state": active_session.state.value,
        "session_id": active_session.session_id
    }

@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_path = Path("static/index.html")
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>NutriSense Server Active</h1>")

# 1. Weight Telemetry Ingestion from ESP32

# ================================================================
# CAMERA RAM BUFFER & LIVE SCALE CALIBRATION
# ================================================================
scale_calibration_multiplier = 1.0  # Adjusts raw HX711 counts to true grams (e.g. 42.4g -> 190.8g)
scale_calibration_offset = 0.0
last_cam_frame_bytes = b""
last_cam_frame_time = 0.0

def background_camera_worker(cam_ip: str = "10.126.26.171"):
    global last_cam_frame_bytes, last_cam_frame_time
    # Force 1280x720 720p Full HD with ultra-low compression (Quality 6)
    try:
        requests.get(f"http://{cam_ip}/control?var=framesize&val=13", timeout=1.5) # HD 1280x720
        requests.get(f"http://{cam_ip}/control?var=quality&val=6", timeout=1.5)    # High Quality Crisp
        requests.get(f"http://{cam_ip}/control?var=contrast&val=2", timeout=1.5)
        requests.get(f"http://{cam_ip}/control?var=saturation&val=2", timeout=1.5)
    except Exception:
        pass
        
    while True:
        try:
            r = requests.get(f"http://{cam_ip}/capture", timeout=1.5)
            if r.status_code == 200 and len(r.content) > 1000:
                last_cam_frame_bytes = r.content
                last_cam_frame_time = time.time()
            time.sleep(0.06) # ~16 FPS smooth fetch
        except Exception:
            time.sleep(0.2)

# Start single dedicated background camera thread
cam_thread = threading.Thread(target=background_camera_worker, daemon=True)
cam_thread.start()

@app.get("/api/v1/hardware/calib")
def get_calibration():
    return {"multiplier": scale_calibration_multiplier, "offset": scale_calibration_offset}

@app.post("/api/v1/hardware/calib")
def set_calibration(multiplier: float = 1.0, offset: float = 0.0):
    global scale_calibration_multiplier, scale_calibration_offset
    scale_calibration_multiplier = float(multiplier)
    scale_calibration_offset = float(offset)
    return {"status": "updated", "multiplier": scale_calibration_multiplier, "offset": scale_calibration_offset}

# Global zone cache
last_zones_cache = []
latest_measured_weight = 0.0

@app.post("/api/v1/hardware/weight")
async def ingest_hardware_weight(data: WeightTelemetryRequest):
    print(f"[SCALE INGEST] from {data.device_id}: raw={data.get_effective_weight()}g (dict: {data.dict()})")
    global latest_measured_weight
    eff_w = data.get_effective_weight()
    # Auto-rectify inverted hardware polarity if raw is negative during active load
    if eff_w < -5.0:
        eff_w = abs(eff_w)
    raw_weight = round((eff_w * scale_calibration_multiplier) + scale_calibration_offset, 1)
    HW_TELEMETRY["live_weight_g"] = raw_weight
    HW_TELEMETRY["last_seq"] = data.sequence
    latest_measured_weight = raw_weight
    hw_state.live_weight_g = raw_weight
    active_session.current_weight_g = raw_weight
    print(f"[DEBUG INGEST] eff_w={eff_w}, raw_weight={raw_weight}, latest_measured_weight={latest_measured_weight}")
    
    # Process through rolling median filter & stabilizer
    sample = weight_stabilizer.add_sample(raw_weight)
    
    # Get current temporal CV scene
    current_scene, conf_map = temporal_cv.get_stable_scene()
    
    # Feed to state machine
    prev_state = active_session.state.value
    state_res = active_session.process_scale_and_cv(sample, current_scene, conf_map, zones=last_zones_cache)
    new_state = active_session.state.value
    
    # Log reading to DB
    try:
        database.save_weight_reading(
            session_id=active_session.session_id,
            device_id=data.device_id,
            raw_g=raw_weight,
            filtered_g=sample["filtered_g"],
            is_stable=sample["is_stable"],
            std_dev=sample["std_dev"]
        )
    except Exception:
        pass

    # Broadcast via WebSocket
    msg = {
        "type": "WEIGHT_UPDATE",
        "raw_weight_g": raw_weight,
        "filtered_weight_g": sample["filtered_g"],
        "is_stable": sample["is_stable"],
        "state": new_state,
        "baseline_weight_g": active_session.baseline_weight_g,
        "initial_weight_g": active_session.initial_weight_g,
        "timestamp": time.time()
    }
    
    if state_res.get("action_event"):
        msg["removal_event"] = state_res["action_event"]
        
    await ws_manager.broadcast(msg)
    
    return {
        "status": "ok",
        "processed_g": sample["filtered_g"],
        "state": new_state,
        "action": state_res.get("action_event")
    }

@app.post("/api/infer")
def post_infer(data: InferRequest):
    if model is None:
        return {"detections": [], "items": [], "yolo_available": False}

    try:
        # Decode base64 frame
        img_bytes = base64.b64decode(data.frame)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return {"detections": [], "items": [], "yolo_available": True}

        conf_thr = data.conf_threshold or 0.25
        results = model(img, conf=conf_thr, verbose=False)
        
        raw_dets = []
        for r in results:
            for b in r.boxes:
                cls_id = int(b.cls[0].item())
                item_name = model.names[cls_id]
                conf = float(b.conf[0].item())
                x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
                
                raw_dets.append({
                    "item": item_name,
                    "confidence": round(conf, 3),
                    "bbox": [x1, y1, x2, y2],
                    "cls_id": cls_id
                })

        # Feed to Temporal CV Tracker
        stable_scene = temporal_cv.add_frame_detections(raw_dets)
        
        # Save CV observation to DB
        avg_c = float(np.mean([d["confidence"] for d in raw_dets])) if raw_dets else 0.0
        try:
            database.save_cv_observation(
                session_id=active_session.session_id,
                detected_items=raw_dets,
                avg_confidence=avg_c
            )
        except Exception:
            pass

        return {
            "detections": raw_dets,
            "stable_items": list(stable_scene),
            "yolo_available": True,
            "conf_threshold": conf_thr
        }
    except Exception as e:
        print(f"[Infer Error] {e}")
        return {"detections": [], "items": [], "error": str(e)}

# 3. Measurement Session Lifecycle



@app.post("/api/v1/zones/infer")
def infer_zones_endpoint(data: InferRequest):
    global last_inferred_classes
    if model is None:
        return {"success": False, "error": "Model not loaded", "zones": []}

    try:
        header, encoded = data.frame.split(",", 1) if "," in data.frame else ("", data.frame)
        img_bytes = base64.b64decode(encoded)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return {"success": False, "error": "Invalid frame decode", "zones": []}

        img_h, img_w = img.shape[:2]
        conf_thr = data.conf_threshold or 0.25
        results = model(img, conf=conf_thr, iou=0.45, agnostic_nms=False, verbose=False)
        
        raw_dets = []
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                name = str(model.names[cls_id])
                conf = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                bw, bh = x2 - x1, y2 - y1

                # Filter out dark table edge on far right and full-screen boxes
                if (x1 / img_w) > 0.82:
                    continue
                if bw > (img_w * 0.65) or bh > (img_h * 0.75):
                    continue
                if bw < 40 or bh < 40:
                    continue

                cx = (x1 + x2) / 2.0 / img_w
                cy = (y1 + y2) / 2.0 / img_h
                
                raw_dets.append({
                    "item": name,
                    "confidence": round(conf, 3),
                    "bbox": [int(x1), int(y1), int(x2), int(y2)],
                    "norm_bbox": [round(x1/img_w, 4), round(y1/img_h, 4), round(x2/img_w, 4), round(y2/img_h, 4)],
                    "cx": cx,
                    "cy": cy
                })

        zones = [
            {"zone_id": 1, "name": "Zone 1 (Top-Left)", "item": None, "confidence": 0.0, "status": "READY", "bbox": None, "norm_bbox": None},
            {"zone_id": 2, "name": "Zone 2 (Top-Right)", "item": None, "confidence": 0.0, "status": "READY", "bbox": None, "norm_bbox": None},
            {"zone_id": 3, "name": "Zone 3 (Bottom-Left)", "item": None, "confidence": 0.0, "status": "READY", "bbox": None, "norm_bbox": None},
            {"zone_id": 4, "name": "Zone 4 (Bottom-Right)", "item": None, "confidence": 0.0, "status": "READY", "bbox": None, "norm_bbox": None},
        ]

        for d in raw_dets:
            zid = 1
            if d["cx"] < 0.5 and d["cy"] < 0.5:
                zid = 1
            elif d["cx"] >= 0.5 and d["cy"] < 0.5:
                zid = 2
            elif d["cx"] < 0.5 and d["cy"] >= 0.5:
                zid = 3
            else:
                zid = 4
            
            z_idx = zid - 1
            if d["confidence"] > zones[z_idx]["confidence"]:
                zones[z_idx]["item"] = d["item"]
                zones[z_idx]["confidence"] = d["confidence"]
                zones[z_idx]["status"] = "OCCUPIED"
                zones[z_idx]["bbox"] = d["bbox"]
                zones[z_idx]["norm_bbox"] = d["norm_bbox"]

        global last_zones_cache
        last_zones_cache = zones
        active_items = [z["item"] for z in zones if z["item"]]
        if active_items:
            last_inferred_classes = active_items
            temporal_cv.add_frame_detections(raw_dets)

        return {
            "success": True,
            "mode": "4_zone_quadrant",
            "zones": zones,
            "detections": [z for z in zones if z["status"] == "OCCUPIED"],
            "active_count": len([z for z in zones if z["status"] == "OCCUPIED"])
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e), "zones": []}

@app.api_route("/api/v1/sessions/start", methods=["GET", "POST"])
def start_session(data: Optional[dict] = None):
    global active_session, last_inferred_classes, last_zones_cache, latest_measured_weight
    sid = f"session_{int(time.time())}"
    active_session = SessionStateMachine(session_id=sid)
    temporal_cv.reset()
    weight_stabilizer.buffer.clear()
    
    current_w = latest_measured_weight
    summary = active_session.start_session(
        current_weight_g=current_w,
        current_items=last_inferred_classes,
        current_zones=last_zones_cache
    )
    return {"status": "started", "session": summary}

@app.api_route("/api/v1/sessions/tare", methods=["GET", "POST"])
@app.api_route("/api/v1/hardware/tare", methods=["GET", "POST"])
def tare_session(data: Optional[dict] = None):
    global scale_calibration_offset, latest_measured_weight
    # Zero out current resting tare offset
    scale_calibration_offset = -latest_measured_weight
    latest_measured_weight = 0.0
    active_session.current_weight_g = 0.0
    active_session.baseline_weight_g = 0.0
    weight_stabilizer.buffer.clear()
    weight_stabilizer.last_stable_weight = 0.0
    active_session.transition_to(SessionState.TARING, "Manual tare requested")
    return {"status": "tared", "offset": scale_calibration_offset, "state": active_session.state.value}


@app.api_route("/api/v1/sessions/stop", methods=["GET", "POST"])
@app.api_route("/api/v1/sessions/end", methods=["GET", "POST"])
def end_session(data: Optional[dict] = None):
    global active_session
    summary = active_session.end_measurement()
    
    # Calculate final reconciliation and nutrition
    rec = MassReconciliationEngine.reconcile(
        initial_total_weight_g=active_session.initial_weight_g,
        removals_list=active_session.removal_history
    )
    nutrition = nutrition_engine.calculate_session_nutrition(
        removals_list=active_session.removal_history,
        session_id=active_session.session_id
    )
    
    # Save to SQLite database
    try:
        database.save_session(
            session_id=active_session.session_id,
            start_time=active_session.start_time,
            end_time=active_session.end_time or time.time(),
            initial_weight_g=active_session.initial_weight_g,
            final_weight_g=active_session.current_weight_g,
            reconciliation_error_g=rec["reconciliation_error_g"],
            reconciliation_status=rec["status"],
            total_calories_kcal=nutrition["totals"]["calories_kcal"],
            total_protein_g=nutrition["totals"]["protein_g"],
            total_carbs_g=nutrition["totals"]["carbs_g"],
            total_fat_g=nutrition["totals"]["fat_g"],
            total_fiber_g=nutrition["totals"]["fiber_g"]
        )
    except Exception as e:
        print("Database save error:", e)
        
    return {
        "status": "completed",
        "session": summary,
        "reconciliation": rec,
        "nutrition": nutrition
    }

@app.api_route("/api/v1/sessions/reset", methods=["GET", "POST"])
def reset_session(data: Optional[dict] = None):
    global active_session, scale_calibration_offset, latest_measured_weight
    scale_calibration_offset = 0.0
    latest_measured_weight = 0.0
    sid = f"session_{int(time.time())}"
    active_session = SessionStateMachine(session_id=sid)
    active_session.state = SessionState.IDLE
    temporal_cv.reset()
    weight_stabilizer.buffer.clear()
    return {"status": "reset", "state": "IDLE"}



@app.get("/api/v1/sessions/status")
async def get_session_status():
    summary = active_session.get_summary()
    rec = MassReconciliationEngine.reconcile(
        initial_total_weight_g=active_session.initial_weight_g,
        removals_list=active_session.removal_history
    )
    nutrition = nutrition_engine.calculate_session_nutrition(
        removals_list=active_session.removal_history,
        session_id=active_session.session_id
    )
    totals = nutrition.get("totals", {}) if isinstance(nutrition, dict) else {}
    
    live_w = HW_TELEMETRY.get("live_weight_g", 0.0)
    print(f"[DEBUG GET STATUS] live_w={live_w}, HW_TELEMETRY={HW_TELEMETRY}")
    
    return {
        "session": summary,
        "reconciliation": rec,
        "nutrition": nutrition,
        "is_measuring": active_session.state not in [SessionState.IDLE, SessionState.COMPLETE],
        "fsm_state": active_session.state.value,
        "current_load_g": live_w,
        "current_weight_g": live_w,
        "initial_total_mass_g": active_session.initial_weight_g,
        "initial_weight_g": active_session.initial_weight_g,
        "baseline_tare_g": active_session.baseline_weight_g,
        "baseline_weight_g": active_session.baseline_weight_g,
        "removal_history": active_session.removal_history,
        "totals": totals
    }

@app.get("/api/v1/sessions/timeline")
def get_session_timeline():
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT event_type, prev_state, next_state, message, timestamp
        FROM system_events WHERE session_id = ?
        ORDER BY timestamp ASC
    """, (active_session.session_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"session_id": active_session.session_id, "timeline": rows}

@app.get("/api/v1/sessions/history")
def get_session_history():
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT session_id, start_time, end_time, initial_weight_g, sum_removed_g,
               reconciliation_error_g, reconciliation_error_pct, reconciliation_status, status
        FROM measurement_sessions
        ORDER BY start_time DESC LIMIT 20
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"history": rows}

@app.get("/api/v1/nutrition/summary")
def get_nutrition_summary():
    nutrition = nutrition_engine.calculate_session_nutrition(
        removals_list=active_session.removal_history,
        session_id=active_session.session_id
    )
    rec = MassReconciliationEngine.reconcile(
        initial_total_weight_g=active_session.initial_weight_g,
        removals_list=active_session.removal_history
    )
    return {
        "session_id": active_session.session_id,
        "totals": nutrition["totals"],
        "removals": nutrition["items"],
        "reconciliation": rec,
        "disclaimer": nutrition["disclaimer"]
    }

# 4. Interactive Demo Simulator Endpoint
@app.post("/api/v1/sessions/demo")
async def run_demo_simulation():
    """
    Executes a complete simulated 4-ingredient automatic measurement workflow:
    1. Start Session & Tare (0.0g)
    2. Place 4 items (Tomato, Cucumber, Onion, Carrot) -> 320.4g
    3. Remove Tomato (-78.7g -> 241.7g)
    4. Remove Cucumber (-80.6g -> 161.1g)
    5. Remove Onion (-41.9g -> 119.2g)
    6. Remove Carrot (-89.1g -> 30.1g)
    7. Complete & Reconcile
    """
    global active_session
    sid = f"demo_session_{int(time.time())}"
    active_session = SessionStateMachine(session_id=sid)
    temporal_cv.reset()
    weight_stabilizer.buffer.clear()
    
    active_session.start_session()
    
    # 1. Tare at 0.0g
    active_session.process_scale_and_cv({"filtered_g": 0.0, "is_stable": True, "std_dev": 0.05}, set())
    
    # 2. Place 4 items (320.4g)
    items = {"tomato", "cucumber", "onion", "carrot"}
    active_session.process_scale_and_cv({"filtered_g": 320.4, "is_stable": True, "std_dev": 0.1}, items)
    
    # 3. Remove Tomato (-78.7g -> 241.7g)
    items.remove("tomato")
    active_session.process_scale_and_cv({"filtered_g": 241.7, "is_stable": True, "std_dev": 0.1}, items, {"tomato": 0.98})
    
    # 4. Remove Cucumber (-80.6g -> 161.1g)
    items.remove("cucumber")
    active_session.process_scale_and_cv({"filtered_g": 161.1, "is_stable": True, "std_dev": 0.1}, items, {"cucumber": 0.99})
    
    # 5. Remove Onion (-41.9g -> 119.2g)
    items.remove("onion")
    active_session.process_scale_and_cv({"filtered_g": 119.2, "is_stable": True, "std_dev": 0.1}, items, {"onion": 0.99})
    
    # 6. Remove Carrot (-89.1g -> 30.1g)
    items.remove("carrot")
    active_session.process_scale_and_cv({"filtered_g": 30.1, "is_stable": True, "std_dev": 0.1}, items, {"carrot": 0.95})
    
    # End & Reconcile
    summary = active_session.end_measurement()
    rec = MassReconciliationEngine.reconcile(active_session.initial_weight_g, active_session.removal_history)
    nutrition = nutrition_engine.calculate_session_nutrition(active_session.removal_history, session_id=sid)
    
    return {
        "status": "demo_completed",
        "session": summary,
        "reconciliation": rec,
        "nutrition": nutrition
    }

# 5. Camera Streaming Proxies (Ultra-Fast RAM Buffer)
@app.get("/api/v1/hardware/cam-proxy")
def proxy_cam_frame(cam_ip: str = "10.126.26.171"):
    global last_cam_frame_bytes
    if last_cam_frame_bytes:
        return Response(content=last_cam_frame_bytes, media_type="image/jpeg")
    try:
        r = requests.get(f"http://{cam_ip}/capture", timeout=1.5)
        return Response(content=r.content, media_type="image/jpeg")
    except Exception:
        return Response(content=b"", status_code=503)

@app.get("/api/v1/hardware/cam-stream")
def proxy_mjpeg_stream(cam_ip: str = "10.126.26.171"):
    def gen_frames():
        global last_cam_frame_bytes
        while True:
            if last_cam_frame_bytes:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + last_cam_frame_bytes + b'\r\n')
            time.sleep(0.06)
    return StreamingResponse(gen_frames(), media_type="multipart/x-mixed-replace; boundary=frame")


# ==========================================
# 6. Family Profiles, Smart Pantry & AI APIs
# ==========================================

@app.get("/api/v1/profiles")
def get_profiles():
    profiles = database.get_all_family_profiles()
    return {"profiles": profiles}

@app.post("/api/v1/profiles/select")
def select_active_profile(data: dict):
    pid = data.get("profile_id", "prof_hari")
    database.set_active_profile(pid)
    return {"status": "success", "active_profile": pid}

@app.post("/api/v1/profiles/add")
def add_new_profile(data: dict):
    name = data.get("name", "New Member")
    avatar = data.get("avatar", "👤")
    age = int(data.get("age", 25))
    target_cal = float(data.get("target_calories", 2000.0))
    target_prot = float(data.get("target_protein", 60.0))
    target_carbs = float(data.get("target_carbs", 250.0))
    target_fat = float(data.get("target_fat", 50.0))
    target_fiber = float(data.get("target_fiber", 30.0))
    
    pid = database.add_family_profile(
        name=name, avatar=avatar, age=age,
        target_cal=target_cal, target_prot=target_prot,
        target_carbs=target_carbs, target_fat=target_fat,
        target_fiber=target_fiber
    )
    return {"status": "created", "profile_id": pid}

@app.post("/api/v1/profiles/log-portion")
def log_portion_to_profile(data: dict):
    pid = data.get("profile_id")
    if not pid:
        # Default to current active profile
        profiles = database.get_all_family_profiles()
        active = next((p for p in profiles if p.get("is_active")), profiles[0] if profiles else None)
        pid = active["profile_id"] if active else "prof_hari"
        
    meal_name = data.get("meal_name", "Prepared Dish (NutriSense)")
    portion_weight_g = float(data.get("portion_weight_g", 50.0))
    calories = float(data.get("calories", 0.0))
    protein = float(data.get("protein", 0.0))
    carbs = float(data.get("carbs", 0.0))
    fat = float(data.get("fat", 0.0))
    fiber = float(data.get("fiber", 0.0))
    session_id = data.get("session_id", active_session.session_id)
    
    lid = database.log_meal_intake(
        profile_id=pid, meal_name=meal_name, portion_weight_g=portion_weight_g,
        calories=calories, protein=protein, carbs=carbs, fat=fat, fiber=fiber,
        session_id=session_id
    )
    
    # Deduct from smart pantry
    for r in active_session.removal_history:
        ing = r.get("ingredient")
        wt = r.get("weight_delta_g", 0.0)
        if ing and wt > 0:
            database.deduct_pantry_item(ing, wt)
            
    return {"status": "logged", "log_id": lid, "profile_id": pid}

@app.get("/api/v1/pantry")
def get_pantry():
    items = database.get_pantry_inventory()
    low_stock = [i for i in items if i.get("is_low_stock")]
    return {"inventory": items, "low_stock_count": len(low_stock), "low_stock_items": low_stock}

@app.get("/api/v1/ai/recommendations")
def get_ai_recommendations(profile_id: Optional[str] = None):
    profiles = database.get_all_family_profiles()
    active = next((p for p in profiles if p["profile_id"] == profile_id), None) if profile_id else next((p for p in profiles if p.get("is_active")), profiles[0] if profiles else None)
    
    if not active:
        return {"recommendation": "Maintain a balanced intake of complex carbohydrates and hydration."}
        
    consumed = active["today_consumed"]
    target_cal = active["target_calories"]
    target_prot = active["target_protein"]
    target_fiber = active["target_fiber"]
    
    cal_pct = round((consumed["calories"] / target_cal * 100) if target_cal > 0 else 0)
    prot_pct = round((consumed["protein_g"] / target_prot * 100) if target_prot > 0 else 0)
    fib_pct = round((consumed["fiber_g"] / target_fiber * 100) if target_fiber > 0 else 0)
    
    # Deterministic Expert AI Dietitian Rule Engine
    insights = []
    if prot_pct < 40:
        insights.append(f"Protein intake is currently at {prot_pct}% of daily target ({consumed['protein_g']}g/{target_prot}g). Consider incorporating paneer, boiled eggs, or lentils into your next meal.")
    else:
        insights.append(f"Protein progress is optimal ({consumed['protein_g']}g / {target_prot}g).")
        
    if fib_pct < 50:
        insights.append(f"Dietary fiber is low ({consumed['fiber_g']}g / {target_fiber}g). Raw onions, cucumbers, and carrots provide vital prebiotic inulin and pectin.")
    else:
        insights.append(f"Excellent prebiotic fiber coverage ({consumed['fiber_g']}g / {target_fiber}g) for healthy gut microbiota.")
        
    pantry = database.get_pantry_inventory()
    low_stock_names = [i["item_name"].capitalize() for i in pantry if i.get("is_low_stock")]
    
    grocery_alert = f"Smart Restock Alert: {', '.join(low_stock_names)} running below threshold." if low_stock_names else "Pantry inventory is well-stocked."
    
    return {
        "profile_name": active["name"],
        "calorie_status": f"{consumed['calories']} / {target_cal} kcal ({cal_pct}%)",
        "macro_progress": {
            "protein_pct": prot_pct,
            "fiber_pct": fib_pct,
            "carbs_g": consumed["carbs_g"],
            "fat_g": consumed["fat_g"]
        },
        "dietitian_insight": " ".join(insights),
        "grocery_suggestion": grocery_alert
    }
