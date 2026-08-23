"""
NutriSense Hardware & Telemetry Simulator
Simulates the ESP32 load-cell scale transmitting real-time 10 Hz telemetry
for an automated 4-ingredient removal session (Tomato -> Cucumber -> Onion -> Carrot).
"""
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import time
import requests

API_BASE = "http://localhost:8000"

def run_simulation():
    print("================================================================")
    print("  NUTRISENSE — AUTOMATIC MEASUREMENT SIMULATOR (10 Hz STREAM)   ")
    print("================================================================")
    
    # 0. Health check
    try:
        r = requests.get(f"{API_BASE}/api/health", timeout=3).json()
        print(f"[Sim] 0. Server Connected: {r.get('service')}")
    except Exception as e:
        print(f"[Sim] [ERROR] Could not connect to {API_BASE}: {e}")
        return

    # 1. Start Session
    r = requests.post(f"{API_BASE}/api/v1/sessions/start").json()
    sid = r.get("session", {}).get("session_id", "sim-session")
    print(f"[Sim] 1. Session Started: ID={sid} | State={r.get('session', {}).get('state')}")

    # 2. Tare Platform (0.0g @ 10 Hz for 1.0s)
    print("[Sim] 2. Taring platform at 0.0g...")
    for i in range(10):
        requests.post(f"{API_BASE}/api/v1/hardware/weight", json={"device_id": "sim-scale-01", "weight_g": 0.0, "sequence": i})
        time.sleep(0.05)

    s1 = requests.get(f"{API_BASE}/api/v1/sessions/status").json()["session"]
    print(f"       State after tare: {s1['state']}")

    # 3. Place 4 Ingredients: Tomato, Cucumber, Onion, Carrot (Total: 320.4g)
    print("[Sim] 3. Placing 4 ingredients on board (320.4g)...")
    for i in range(15):
        requests.post(f"{API_BASE}/api/v1/hardware/weight", json={"device_id": "sim-scale-01", "weight_g": 320.4, "sequence": 10+i})
        time.sleep(0.05)

    s2 = requests.get(f"{API_BASE}/api/v1/sessions/status").json()["session"]
    print(f"       State: {s2['state']} | Baseline: {s2['baseline_weight_g']}g")

    # Run complete interactive demo via session API
    print("[Sim] 4. Executing synchronized multi-ingredient removal & mass reconciliation...")
    demo_res = requests.post(f"{API_BASE}/api/v1/sessions/demo").json()
    summary = demo_res.get("session", {})
    rec = demo_res.get("reconciliation", {})
    nut = demo_res.get("nutrition", {})

    print("\n================================================================")
    print("  SIMULATION COMPLETE — AUDIT & RECONCILIATION SUMMARY          ")
    print("================================================================")
    print(f"  Session ID            : {summary.get('session_id')}")
    print(f"  Final State           : {summary.get('state')}")
    print(f"  Initial Total Weight  : {summary.get('initial_weight_g')} g")
    print(f"  Sum Removed Weights   : {summary.get('sum_removed_g')} g")
    print(f"  Reconciliation Error  : {rec.get('reconciliation_error_g')} g ({rec.get('reconciliation_error_percent')}%) -> [{rec.get('status')}]")
    print(f"  Confirmed Removals    : {len(summary.get('removal_history', []))} items")
    print("\n  --- NUTRITIONAL BREAKDOWN ---")
    totals = nut.get("totals", {})
    print(f"  Total Measured Mass   : {totals.get('measured_food_mass_g')} g")
    print(f"  Total Calories        : {totals.get('calories_kcal')} kcal")
    print(f"  Total Protein         : {totals.get('protein_g')} g")
    print(f"  Total Carbohydrates   : {totals.get('carbs_g')} g")
    print(f"  Total Fat             : {totals.get('fat_g')} g")
    print(f"  Total Fiber           : {totals.get('fiber_g')} g")
    print(f"\n  Provenance Disclaimer : {nut.get('disclaimer')}")
    print("================================================================\n")

if __name__ == "__main__":
    run_simulation()
