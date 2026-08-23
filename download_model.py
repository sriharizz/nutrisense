"""
One-shot script to download the NutriSense food-detection model.

Setup (PowerShell):
    $env:ROBOFLOW_API_KEY = "your_key_here"
    python download_model.py

Get your free API key: https://app.roboflow.com -> Settings -> Roboflow API
"""
import os, sys
from pathlib import Path

WORKSPACE = "orkhan-aliyev-8nktf"
PROJECT   = "fruits-and-vegetables-2vf7u"
VERSION   = 1

def main():
    api_key = os.environ.get("ROBOFLOW_API_KEY", "").strip()
    if not api_key:
        print("ERROR: ROBOFLOW_API_KEY not set.\n")
        print("Run this in PowerShell first:")
        print('  $env:ROBOFLOW_API_KEY = "paste_your_key_here"')
        print("\nGet key: https://app.roboflow.com -> Settings -> Roboflow API")
        sys.exit(1)

    try:
        from roboflow import Roboflow
    except ImportError:
        print("Run: pip install roboflow")
        sys.exit(1)

    print(f"Connecting to Roboflow: {WORKSPACE}/{PROJECT} v{VERSION}")
    rf      = Roboflow(api_key=api_key)
    project = rf.workspace(WORKSPACE).project(PROJECT)
    version = project.version(VERSION)

    print("Downloading YOLOv8 weights...")
    version.download("yolov8")

    weights = Path(f"{PROJECT}-{VERSION}") / "weights" / "best.pt"
    if not weights.exists():
        print(f"WARNING: expected weights at {weights} — check the download folder manually.")
        sys.exit(1)

    print(f"\nWeights saved: {weights}")

    # Verify the 4 required classes
    try:
        from ultralytics import YOLO
        model   = YOLO(str(weights))
        classes = {v.lower() for v in model.names.values()}
        needed  = {"onion", "tomato", "apple", "banana"}
        missing = needed - classes
        if missing:
            print(f"WARNING: missing classes {missing} — COCO proxies will cover them.")
        else:
            print(f"All 4 classes confirmed: {needed}")
        print(f"Full class list ({len(classes)}): {sorted(classes)}")
    except Exception as e:
        print(f"Class verification skipped: {e}")

    print("\nDone. Run: python cv_agent.py")

if __name__ == "__main__":
    main()
