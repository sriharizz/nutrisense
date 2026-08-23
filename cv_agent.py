import math
from pathlib import Path
import requests
import cv2
import numpy as np

API_BASE   = "http://localhost:8000"
API_DETECT = f"{API_BASE}/api/detect"
API_RESET  = f"{API_BASE}/api/reset"

import os
UNIT_WEIGHTS = {"onion": 110.0, "tomato": 90.0, "apple": 150.0, "banana": 120.0, "carrot": 100.0, "cucumber": 150.0}
TARGET       = {"onion", "tomato", "apple", "banana", "carrot", "cucumber"}

# Fallback COCO proxy map — only used when Roboflow weights are absent
COCO_PROXY = {"apple": "apple", "banana": "banana", "bowl": "onion"}

# Model path priority: V4 trained local model -> V3 -> fallback generic
V4_WEIGHTS  = Path("nutrisense_model/v4/weights/best.pt")
V3_WEIGHTS  = Path("nutrisense_model/v3/weights/best.pt")
FALLBACK_PT = "yolov8n.pt"

_default_rf = V4_WEIGHTS if V4_WEIGHTS.exists() else (V3_WEIGHTS if V3_WEIGHTS.exists() else Path(FALLBACK_PT))
RF_WEIGHTS  = Path(os.environ.get("CV_MODEL_PATH", str(_default_rf)))

# Adaptive clustering threshold (pixels) and stabilisation frames
CLUSTER_PX = 130
STABLE_N   = 30

ITEM_COLOR = {
    "apple":  (50,  220, 80),
    "banana": (0,   210, 255),
    "tomato": (55,  55,  230),
    "onion":  (210, 80,  210),
}
ZONES = [1, 2, 3]


def build_map(names: dict) -> dict:
    """Map model class names → NutriSense items for whichever model is loaded."""
    native = {v.lower() for v in names.values()}
    mapping = {}
    for t in TARGET:
        if t in native:
            mapping[t] = t          # Roboflow: direct match
    for src, dst in COCO_PROXY.items():
        if src not in mapping and dst not in mapping.values():
            mapping[src] = dst      # yolov8n fallback proxy
    return mapping


def cluster(detections: list) -> list:
    """
    Group raw detections by proximity, sort left→right, assign zone IDs 1-3.
    Input:  [{"item": str, "cx": int, "cy": int}, ...]
    Output: [{"zone": int, "item": str, "count": int, "cx": float, "cy": float, "pts": list}]
    """
    groups = []
    for d in detections:
        placed = False
        for g in groups:
            if any(math.hypot(d["cx"]-e["cx"], d["cy"]-e["cy"]) < CLUSTER_PX for e in g):
                g.append(d); placed = True; break
        if not placed:
            groups.append([d])

    groups.sort(key=lambda g: sum(x["cx"] for x in g) / len(g))

    result = []
    for z, g in enumerate(groups[:3], 1):
        counts = {}
        for d in g:
            counts[d["item"]] = counts.get(d["item"], 0) + 1
        dom = max(counts, key=counts.get)
        result.append({
            "zone":  z,
            "item":  dom,
            "count": counts[dom],
            "cx":    sum(d["cx"] for d in g) / len(g),
            "cy":    sum(d["cy"] for d in g) / len(g),
            "pts":   [(d["cx"], d["cy"]) for d in g],
        })
    return result


def fresh():
    return {z: {"item": "", "count": 0} for z in ZONES}


def main():
    print("=" * 52)
    print("  PROJECT NUTRISENSE — ADAPTIVE VISION TRACKER")
    print("=" * 52)

    # Load model — prefer Roboflow weights, fall back to yolov8n
    model_path = RF_WEIGHTS if RF_WEIGHTS.exists() else FALLBACK_PT
    if RF_WEIGHTS.exists():
        print(f"Trained NutriSense model found: {RF_WEIGHTS}")
    else:
        print(f"Trained model not ready yet. Fallback: {FALLBACK_PT}")
        print("  Training in background — run cv_agent.py again once training completes.")

    model, class_map, yolo_ok = None, {}, False
    try:
        from ultralytics import YOLO
        model     = YOLO(str(model_path))
        class_map = build_map(model.names)
        yolo_ok   = True
        print(f"Model loaded. Class map: {class_map}")
    except Exception as e:
        print(f"YOLO unavailable: {e}\nKeyboard simulator mode active.")

    # Webcam
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cam_ok = cap.isOpened()
    print(f"{'Webcam ready.' if cam_ok else 'No webcam — keyboard simulator active.'}\n")

    # State
    stab     = {z: 0 for z in ZONES}
    last     = fresh()
    reported = fresh()
    sim_dets = []   # keyboard-injected raw detections

    print("=== KEYBOARD CONTROLS ===")
    print("[A] Apple  left    [B] Banana x2 center")
    print("[T] Tomato x3 left [O] Onion  x2 right (cradle)")
    print("[C] Clear zones    [R] API Reset    [Q] Quit")
    print("=========================\n")

    while True:
        # Grab frame
        if cam_ok:
            ret, frame = cap.read()
            frame = frame if ret else np.zeros((480, 640, 3), np.uint8)
            frame = cv2.flip(frame, 1)
        else:
            frame = np.zeros((480, 640, 3), np.uint8)

        overlay = frame.copy()

        # YOLO detections
        raw = list(sim_dets)
        if cam_ok and yolo_ok and model:
            gray_chk   = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness = float(cv2.mean(gray_chk)[0])
            if brightness < 40:
                print(f"[CV SKIP] Frame too dark (brightness={brightness:.1f}), skipping inference")
            else:
                h_f, w_f = frame.shape[:2]
                for res in model(frame, verbose=False):
                    for box in res.boxes:
                        name = model.names[int(box.cls[0])].lower()
                        if name in class_map:
                            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0]]
                            cx, cy = (x1+x2)//2, (y1+y2)//2
                            item   = class_map[name]
                            # Human face/body filter — 3-signal check (any 2 of 3 → reject)
                            if item == "apple":
                                bh, bw   = y2-y1, x2-x1
                                aspect   = bh/bw if bw > 0 else 0
                                area_pct = (bh*bw)/(h_f*w_f)
                                crop     = frame[max(0,y1):min(h_f,y2), max(0,x1):min(w_f,x2)]
                                hsv_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV) if crop.size > 0 else None
                                skin = False
                                if hsv_crop is not None:
                                    smask = cv2.inRange(hsv_crop, np.array([0,30,80]), np.array([25,200,255]))
                                    skin  = (np.sum(smask>0)/smask.size) > 0.38
                                if sum([area_pct > 0.08, aspect > 1.3, skin]) >= 2:
                                    print(f"[CV REJECT] Apple face signals: area={area_pct:.2f} ar={aspect:.2f} skin={skin}")
                                    continue
                            raw.append({"item": item, "cx": cx, "cy": cy})
                            col = ITEM_COLOR.get(item, (200, 200, 200))
                            cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2)
                            cv2.putText(frame, item, (x1, y1-6),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)

        # Cluster into adaptive zones
        zones_now = cluster(raw)
        cur = fresh()
        for cl in zones_now:
            cur[cl["zone"]] = {"item": cl["item"], "count": cl["count"]}

        # Reset reported state for zones that cleared
        for z in ZONES:
            if last[z]["item"] and not cur[z]["item"]:
                reported[z] = {"item": "", "count": 0}

        # Stabilisation + POST
        for z in ZONES:
            if cur[z] == last[z]:
                stab[z] = min(stab[z] + 1, STABLE_N)
            else:
                stab[z] = 0
                last[z] = dict(cur[z])

            if stab[z] == STABLE_N and cur[z] != reported[z]:
                item  = cur[z]["item"]
                count = cur[z]["count"]
                wt    = UNIT_WEIGHTS.get(item, 0.0) * count
                try:
                    r = requests.post(API_DETECT,
                                      json={"zone": z, "item": item, "count": count, "weight": wt},
                                      timeout=2)
                    if r.status_code == 200:
                        print(f"[STABLE] Zone {z}: {item.upper()} x{count} ({wt}g) → DB")
                        reported[z] = dict(cur[z])
                except Exception as e:
                    print(f"[NET] {e}")
                    reported[z] = dict(cur[z])

        # Draw cluster overlays
        for cl in zones_now:
            z      = cl["zone"]
            col    = ITEM_COLOR.get(cl["item"], (200, 200, 200))
            sf     = stab[z]
            stable = sf >= STABLE_N
            fill   = (0, 130, 0) if stable else (0, 80, 130)

            pts_arr = np.array(cl["pts"], np.int32)
            if len(pts_arr) >= 3:
                hull = cv2.convexHull(pts_arr)
                cv2.fillConvexPoly(overlay, hull, fill)
                cv2.polylines(frame, [hull], True, col, 2, cv2.LINE_AA)
            else:
                cx_i, cy_i = int(cl["cx"]), int(cl["cy"])
                cv2.circle(overlay, (cx_i, cy_i), 80, fill, -1)
                cv2.circle(frame,   (cx_i, cy_i), 80, col,   2)

            lx = max(8,  int(cl["cx"]) - 55)
            ly = max(22, int(cl["cy"]) - 85)
            lc = (0, 255, 80) if stable else col
            cv2.putText(frame, f"ZONE {z}", (lx, ly),
                        cv2.FONT_HERSHEY_DUPLEX, 0.65, lc, 2, cv2.LINE_AA)
            cv2.putText(frame, f"{cl['item'].upper()} x{cl['count']}", (lx, ly+22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
            wt = UNIT_WEIGHTS.get(cl["item"], 0) * cl["count"]
            cv2.putText(frame, f"{wt}g", (lx, ly+40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)
            bar = int((sf / STABLE_N) * 100)
            cv2.rectangle(frame, (lx, ly+50), (lx+100, ly+58), (40, 40, 40), -1)
            cv2.rectangle(frame, (lx, ly+50), (lx+bar,  ly+58), lc, -1)
            cv2.putText(frame, "SYNCED" if stable else f"{bar}%", (lx, ly+72),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, lc, 1, cv2.LINE_AA)

        cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)

        if not cam_ok:
            cv2.putText(frame, "KEYBOARD SIMULATOR MODE", (125, 240),
                        cv2.FONT_HERSHEY_DUPLEX, 0.75, (0, 255, 255), 2, cv2.LINE_AA)

        # Help bar
        cv2.rectangle(frame, (0, 453), (640, 480), (10, 10, 10), -1)
        cv2.putText(frame,
                    "[A]pple  [B]anana  [T]omato  [O]nion  [C]lear  [R]eset  [Q]uit",
                    (8, 471), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (170, 170, 170), 1, cv2.LINE_AA)

        cv2.imshow("NutriSense — Adaptive Spatial Tracker", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('a'):
            sim_dets = [d for d in sim_dets if d["cx"] >= 213]
            sim_dets.append({"item": "apple", "cx": 106, "cy": 240})
            print("[SIM] Apple x1 → left")
        elif key == ord('b'):
            sim_dets = [d for d in sim_dets if not (213 <= d["cx"] < 426)]
            sim_dets += [{"item": "banana", "cx": 310, "cy": 200},
                         {"item": "banana", "cx": 340, "cy": 290}]
            print("[SIM] Banana x2 → center")
        elif key == ord('t'):
            sim_dets = [d for d in sim_dets if d["cx"] >= 213]
            sim_dets += [{"item": "tomato", "cx": 80,  "cy": 160},
                         {"item": "tomato", "cx": 130, "cy": 240},
                         {"item": "tomato", "cx": 100, "cy": 320}]
            print("[SIM] Tomato x3 → left")
        elif key == ord('o'):
            sim_dets = [d for d in sim_dets if d["cx"] < 426]
            sim_dets += [{"item": "onion", "cx": 490, "cy": 200},
                         {"item": "onion", "cx": 550, "cy": 290}]
            print("[SIM] Onion x2 → right (cradle)")
        elif key == ord('c'):
            sim_dets = []
            stab = {z: 0 for z in ZONES}
            last = fresh(); reported = fresh()
            print("[SIM] All zones cleared")
        elif key == ord('r'):
            try:
                r = requests.post(API_RESET, timeout=2)
                print("[RESET] DB cleared." if r.status_code == 200 else f"[RESET] {r.status_code}")
            except Exception as e:
                print(f"[RESET ERR] {e}")
            sim_dets = []
            stab = {z: 0 for z in ZONES}
            last = fresh(); reported = fresh()

    cap.release()
    cv2.destroyAllWindows()
    print("Tracker stopped.")


if __name__ == "__main__":
    main()
