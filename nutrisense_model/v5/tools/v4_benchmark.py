import os, sys, argparse, json, hashlib
from pathlib import Path
import cv2
import numpy as np

V4_WEIGHTS  = Path("C:/projects/majorprj/nutrisense_model/v4/weights/best.pt")
OUT_DIR     = Path("C:/projects/majorprj/nutrisense_model/v5/tools/annotated")
DARK_THRESH = 40.0
ROI_FRAC    = 0.30


def sha256_short(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def load_model(weights):
    from ultralytics import YOLO
    return YOLO(str(weights))


def annotate(frame, dets, label, color=(0, 255, 0)):
    out = frame.copy()
    h, w = out.shape[:2]
    cv2.rectangle(out, (0, 0), (w, 22), (20, 20, 20), -1)
    cv2.putText(out, label, (4, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    for d in dets:
        if "bbox" not in d:
            continue
        x1, y1, x2, y2 = d["bbox"]
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        txt = "{} {:.2f}".format(d["class"], d["conf"])
        cv2.putText(out, txt, (x1, max(14, y1 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    return out


def run_raw_v4(model, frame):
    """Path A: raw V4 — all boxes above YOLO internal nms, no extra threshold."""
    results = model(frame, verbose=False)
    dets = []
    for res in results:
        for box in res.boxes:
            cid = int(box.cls[0])
            cn  = model.names[cid].lower()
            cf  = float(box.conf[0])
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0]]
            dets.append({"cls_id": cid, "class": cn, "conf": round(cf, 4), "bbox": [x1, y1, x2, y2]})
    return sorted(dets, key=lambda d: -d["conf"])


def run_fixed(model, frame, conf_thr, use_roi=False):
    """Path B/C: fixed server.py pipeline (no HSV hack, configurable thr, optional ROI)."""
    frame = frame.copy()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if float(cv2.mean(gray)[0]) < DARK_THRESH:
        return [{"class": "SKIPPED", "reason": "too_dark"}]
    if use_roi:
        roi_y = int(frame.shape[0] * ROI_FRAC)
        frame = frame[roi_y:, :]
        frame = cv2.resize(frame, (640, 640))
    mc = {int(k): v.lower() for k, v in model.names.items()}
    allowed = set(mc.values())
    dets = []
    for res in model(frame, verbose=False):
        for box in res.boxes:
            cid = int(box.cls[0])
            cn  = mc.get(cid, "unk")
            cf  = float(box.conf[0])
            if cn not in allowed or cf < conf_thr:
                continue
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0]]
            dets.append({"cls_id": cid, "class": cn, "conf": round(cf, 4),
                         "bbox": [x1, y1, x2, y2], "roi": use_roi})
    return sorted(dets, key=lambda d: -d["conf"])


def ptable(label, dets):
    print("\n  [{}]  ({} dets)".format(label, len(dets)))
    print("  {:>4}  {:<18}  {:>5}  bbox".format("cid", "class", "conf"))
    print("  {}  {}  {}  {}".format("-"*4, "-"*18, "-"*5, "-"*25))
    for d in dets:
        if "reason" in d:
            print("  SKIP: {}".format(d))
            continue
        print("  {:>4}  {:<18}  {:>5.3f}  {}".format(
            d["cls_id"], d["class"], d["conf"], d["bbox"]))
    if not dets:
        print("  (none)")


def process(path, conf, use_roi, out_dir, model):
    frame = cv2.imread(str(path))
    if frame is None:
        print("Cannot read {}".format(path))
        return None
    h, w = frame.shape[:2]
    br = float(cv2.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))[0])
    print("\n" + "="*60)
    print("  {}  {}x{}  brightness={:.1f}".format(path.name, w, h, br))
    print("  MODEL: {}  CONF={}  ROI={}".format(V4_WEIGHTS, conf, use_roi))
    print("="*60)
    raw   = run_raw_v4(model, frame)
    fixed = run_fixed(model, frame, conf, False)
    roi   = run_fixed(model, frame, conf, True) if use_roi else []
    ptable("A  RAW V4 (no extra threshold)", raw)
    ptable("B  FIXED conf>={}".format(conf), fixed)
    if use_roi:
        ptable("C  FIXED+ROI conf>={}".format(conf), roi)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = path.stem
    cv2.imwrite(str(out_dir / (stem + "_A_raw.jpg")),
                annotate(frame, raw, "A:RAW V4", (0, 200, 80)))
    cv2.imwrite(str(out_dir / (stem + "_B_fixed.jpg")),
                annotate(frame, fixed, "B:FIXED conf={}".format(conf), (0, 120, 255)))
    if roi:
        cv2.imwrite(str(out_dir / (stem + "_C_roi.jpg")),
                    annotate(frame, roi, "C:ROI conf={}".format(conf), (0, 200, 255)))
    result = {
        "image": str(path), "w": w, "h": h, "brightness": round(br, 1),
        "conf": conf, "roi": use_roi,
        "A_raw": raw, "B_fixed": fixed, "C_roi": roi,
    }
    with open(out_dir / (stem + "_result.json"), "w") as f:
        json.dump(result, f, indent=2)
    print("  Saved annotated images to: {}".format(out_dir))
    return result


def main():
    ap = argparse.ArgumentParser(description="NutriSense V4 Live Benchmark Tool")
    ap.add_argument("--image",  default=None, help="Image path or directory")
    ap.add_argument("--webcam", action="store_true", help="Capture from webcam")
    ap.add_argument("--conf",   type=float, default=0.40)
    ap.add_argument("--roi",    action="store_true", help="Enable ROI (top 30% removed)")
    ap.add_argument("--outdir", default=str(OUT_DIR))
    a = ap.parse_args()
    out = Path(a.outdir)
    os.chdir("C:/projects/majorprj")
    print("[V4 Benchmark Tool]  model={}  sha={}  conf={}  roi={}".format(
        V4_WEIGHTS, sha256_short(V4_WEIGHTS), a.conf, a.roi))
    model = load_model(V4_WEIGHTS)
    print("  classes={}: {}".format(len(model.names), sorted(model.names.values())))
    imgs = []
    if a.webcam:
        import time
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        print("Capturing in 2s...")
        time.sleep(2)
        ret, frame = cap.read()
        cap.release()
        if ret:
            p = out / "webcam_capture.jpg"
            p.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(p), frame)
            imgs.append(p)
            print("Saved: {}".format(p))
        else:
            print("Webcam capture failed"); sys.exit(1)
    elif a.image:
        p = Path(a.image)
        imgs = (list(p.glob("*.jpg")) + list(p.glob("*.png"))) if p.is_dir() else [p]
    else:
        ap.print_help(); sys.exit(0)
    results = [r for r in (process(p, a.conf, a.roi, out, model) for p in sorted(imgs)) if r]
    total_raw   = sum(len(r["A_raw"])   for r in results)
    total_fixed = sum(len(r["B_fixed"]) for r in results)
    total_roi   = sum(len(r["C_roi"])   for r in results)
    print("\n" + "="*60)
    print("SUMMARY: {} images".format(len(results)))
    print("  A raw boxes:        {}".format(total_raw))
    print("  B fixed (conf={}): {}".format(a.conf, total_fixed))
    if a.roi:
        print("  C fixed+ROI:        {}".format(total_roi))
    print("Output: {}".format(out))


if __name__ == "__main__":
    main()
