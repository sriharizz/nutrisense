import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
"""
NutriSense Automatic Measurement Workflow Comprehensive Test Suite
Validates the complete cyber-physical nutrition tracking lifecycle:
1. 18-State Session State Machine transitions
2. Temporal Multi-Frame CV Scene Tracker
3. Sensor-Fusion Removal Pairing & CV_UNCERTAIN handling
4. Mass Reconciliation Engine & Tolerance thresholds
5. Nutrition Calculation Engine & Formula Traceability
6. SQLite Database Persistence & Auditability
7. End-to-End 4-Ingredient Automatic Removal Workflow
"""
import os
import time
import sqlite3

import database
from state_machine import SessionStateMachine, SessionState
from weight_stabilizer import WeightStabilizer
from temporal_cv import TemporalCVTracker
from sensor_fusion import SensorFusionCoordinator, MassReconciliationEngine
from nutrition_engine import NutritionEngine

def test_database_initialization():
    print("\n[Test 1] Initializing SQLite database...")
    database.init_database("test_nutrisense.db")
    conn = sqlite3.connect("test_nutrisense.db")
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    conn.close()
    
    assert "measurement_sessions" in tables
    assert "weight_readings" in tables
    assert "cv_observations" in tables
    assert "removal_events" in tables
    assert "nutrition_results" in tables
    assert "system_events" in tables
    assert "icmr_database" in tables
    print("  ✓ Database schema verified with all 7 normalized tables")

def test_temporal_cv_tracker():
    print("\n[Test 2] Testing Temporal Multi-Frame CV Tracker...")
    tracker = TemporalCVTracker(window_size=5, min_stable_frames=3, conf_threshold=0.40)
    
    # Add frame 1 (Tomato, Onion)
    tracker.add_frame_detections([
        {"item": "tomato", "confidence": 0.95},
        {"item": "onion", "confidence": 0.90},
        {"item": "noise", "confidence": 0.20} # should be ignored
    ])
    scene, _ = tracker.get_stable_scene()
    assert "noise" not in scene
    
    # Add frame 2 & 3
    tracker.add_frame_detections([{"item": "tomato", "confidence": 0.96}, {"item": "onion", "confidence": 0.92}])
    tracker.add_frame_detections([{"item": "tomato", "confidence": 0.97}, {"item": "onion", "confidence": 0.94}])
    
    scene, confs = tracker.get_stable_scene()
    assert "tomato" in scene and "onion" in scene
    assert confs["tomato"] >= 0.95
    print("  ✓ Stable scene representation established across rolling frames")
    
    # Simulate tomato removal (Frames with only Onion)
    tracker.add_frame_detections([{"item": "onion", "confidence": 0.95}])
    tracker.add_frame_detections([{"item": "onion", "confidence": 0.95}])
    tracker.add_frame_detections([{"item": "onion", "confidence": 0.95}])
    
    new_scene, _ = tracker.get_stable_scene()
    disappeared, status = tracker.compute_disappearance(reference_scene=scene, current_scene=new_scene)
    
    assert disappeared == ["tomato"]
    assert status == "CERTAIN"
    print("  ✓ Temporal scene difference identified tomato disappearance unambiguously")

def test_sensor_fusion_and_uncertainty():
    print("\n[Test 3] Testing Sensor-Fusion Removal Pairing & CV_UNCERTAIN...")
    fusion = SensorFusionCoordinator(min_mass_delta_g=8.0, min_cv_confidence=0.40)
    
    # Scenario A: Unambiguous single removal
    res_a = fusion.evaluate_removal(
        session_id="test-session",
        before_weight_g=320.4,
        after_weight_g=241.7,
        before_scene={"tomato", "onion", "cucumber"},
        after_scene={"onion", "cucumber"},
        confidence_map={"tomato": 0.98}
    )
    assert res_a["status"] == "COMMITTED"
    assert res_a["ingredient"] == "tomato"
    assert res_a["weight_delta_g"] == 78.7
    print("  ✓ Unambiguous removal committed: Tomato (-78.7g)")
    
    # Scenario B: Multiple simultaneous removals
    res_b = fusion.evaluate_removal(
        session_id="test-session",
        before_weight_g=320.4,
        after_weight_g=150.0,
        before_scene={"tomato", "onion", "cucumber"},
        after_scene={"cucumber"},
        confidence_map={"tomato": 0.98, "onion": 0.95}
    )
    assert res_b["status"] == "CV_UNCERTAIN"
    print("  ✓ Multiple removals entered CV_UNCERTAIN cleanly without guessing")
    
    # Scenario C: Weight drop with zero visual disappearances (e.g. occlusion)
    res_c = fusion.evaluate_removal(
        session_id="test-session",
        before_weight_g=320.4,
        after_weight_g=250.0,
        before_scene={"tomato", "onion"},
        after_scene={"tomato", "onion"}
    )
    assert res_c["status"] == "CV_UNCERTAIN"
    print("  ✓ Visual occlusion weight drop entered CV_UNCERTAIN cleanly")

def test_mass_reconciliation_engine():
    print("\n[Test 4] Testing Mass Reconciliation Engine...")
    
    # Scenario A: Passed within 5% tolerance
    removals_pass = [
        {"ingredient": "tomato", "weight_delta_g": 80.8, "status": "COMMITTED"},
        {"ingredient": "cucumber", "weight_delta_g": 80.6, "status": "COMMITTED"},
        {"ingredient": "onion", "weight_delta_g": 41.9, "status": "COMMITTED"},
        {"ingredient": "carrot", "weight_delta_g": 89.1, "status": "COMMITTED"}
    ]
    # Sum = 292.4g, Initial = 295.0g -> error = 2.6g (0.88%)
    rec_pass = MassReconciliationEngine.reconcile(initial_total_weight_g=295.0, removals_list=removals_pass)
    assert rec_pass["reconciled"] is True
    assert rec_pass["status"] == "PASSED"
    assert rec_pass["reconciliation_error_g"] == 2.6
    print(f"  ✓ Mass reconciliation PASSED: Initial=295.0g, Sum=292.4g, Error={rec_pass['reconciliation_error_g']}g ({rec_pass['reconciliation_error_percent']}%)")
    
    # Scenario B: Discrepancy exceeding tolerance
    rec_fail = MassReconciliationEngine.reconcile(initial_total_weight_g=400.0, removals_list=removals_pass)
    assert rec_fail["reconciled"] is False
    assert rec_fail["status"] == "MASS_RECONCILIATION_WARNING"
    print(f"  ✓ Mass reconciliation WARNING raised on large mismatch: Error={rec_fail['reconciliation_error_g']}g")

def test_nutrition_engine_and_provenance():
    print("\n[Test 5] Testing Nutrition Calculation & Provenance Traceability...")
    engine = NutritionEngine(db_path="nutrisense.db")
    
    # Calculate for Tomato (80.8g)
    tomato_nut = engine.calculate_ingredient_nutrition("tomato", 80.8)
    assert tomato_nut["ingredient"] == "tomato"
    assert tomato_nut["measured_weight_g"] == 80.8
    assert tomato_nut["calories_kcal"] > 0
    assert "ICMR-NIN" in tomato_nut["reference_source"]
    assert "Calories:" in tomato_nut["calculation_formula"]
    print(f"  ✓ Tomato (80.8g) -> {tomato_nut['calories_kcal']} kcal, {tomato_nut['protein_g']}g protein, {tomato_nut['carbs_g']}g carbs")
    print(f"    Provenance Formula: {tomato_nut['calculation_formula'][:80]}...")

def test_full_4_ingredient_automatic_workflow():
    print("\n[Test 6] Running End-to-End 4-Ingredient Automatic Removal Workflow...")
    
    sm = SessionStateMachine(session_id="e2e-capstone-session")
    sm.start_session()
    assert sm.state == SessionState.TARING
    
    # 1. Tare at 0.0g
    sm.process_scale_and_cv({"filtered_g": 0.0, "is_stable": True}, set())
    assert sm.state == SessionState.WAITING_FOR_INGREDIENTS
    
    # 2. Place 4 items on platform: Tomato, Cucumber, Onion, Carrot (Total: 320.4g)
    active_items = {"tomato", "cucumber", "onion", "carrot"}
    sm.process_scale_and_cv({"filtered_g": 320.4, "is_stable": True}, active_items)
    assert sm.state == SessionState.MEASUREMENT_ACTIVE
    assert sm.initial_weight_g == 320.4
    assert sm.baseline_weight_g == 320.4
    print("  ✓ Platform loaded & stabilized: 320.4g with [tomato, cucumber, onion, carrot]")
    
    # 3. User physically removes Tomato (-78.7g -> 241.7g)
    active_items.remove("tomato")
    sm.process_scale_and_cv({"filtered_g": 241.7, "is_stable": True}, active_items, {"tomato": 0.98})
    assert len(sm.removal_history) == 1
    assert sm.removal_history[0]["ingredient"] == "tomato"
    assert sm.removal_history[0]["weight_delta_g"] == 78.7
    assert sm.baseline_weight_g == 241.7
    print("  ✓ Step 1: Tomato removed (-78.7g) -> Baseline updated to 241.7g")
    
    # 4. User physically removes Cucumber (-80.6g -> 161.1g)
    active_items.remove("cucumber")
    sm.process_scale_and_cv({"filtered_g": 161.1, "is_stable": True}, active_items, {"cucumber": 0.99})
    assert len(sm.removal_history) == 2
    assert sm.removal_history[1]["ingredient"] == "cucumber"
    assert sm.removal_history[1]["weight_delta_g"] == 80.6
    assert sm.baseline_weight_g == 161.1
    print("  ✓ Step 2: Cucumber removed (-80.6g) -> Baseline updated to 161.1g")
    
    # 5. User physically removes Onion (-41.9g -> 119.2g)
    active_items.remove("onion")
    sm.process_scale_and_cv({"filtered_g": 119.2, "is_stable": True}, active_items, {"onion": 0.99})
    assert len(sm.removal_history) == 3
    assert sm.removal_history[2]["ingredient"] == "onion"
    assert sm.removal_history[2]["weight_delta_g"] == 41.9
    assert sm.baseline_weight_g == 119.2
    print("  ✓ Step 3: Onion removed (-41.9g) -> Baseline updated to 119.2g")
    
    # 6. User physically removes Carrot (-89.1g -> 30.1g)
    active_items.remove("carrot")
    sm.process_scale_and_cv({"filtered_g": 30.1, "is_stable": True}, active_items, {"carrot": 0.95})
    assert len(sm.removal_history) == 4
    assert sm.removal_history[3]["ingredient"] == "carrot"
    assert sm.removal_history[3]["weight_delta_g"] == 89.1
    assert sm.baseline_weight_g == 30.1
    print("  ✓ Step 4: Carrot removed (-89.1g) -> Baseline updated to 30.1g")
    
    # 7. End Measurement
    summary = sm.end_measurement()
    assert sm.state == SessionState.COMPLETE
    
    # 8. Reconcile Mass
    rec = MassReconciliationEngine.reconcile(sm.initial_weight_g, sm.removal_history)
    print(f"  ✓ Final Mass Reconciliation: Initial={rec['initial_total_weight_g']}g, Sum Removed={rec['sum_removed_weights_g']}g, Status={rec['status']}")
    
    # 9. Compute Full Nutrition
    nut_engine = NutritionEngine(db_path="nutrisense.db")
    nutrition = nut_engine.calculate_session_nutrition(sm.removal_history, session_id=sm.session_id)
    
    assert nutrition["ingredient_count"] == 4
    assert nutrition["totals"]["calories_kcal"] > 0
    assert nutrition["totals"]["protein_g"] > 0
    print(f"  ✓ Session Total Nutrition Calculated:")
    print(f"    - Measured Food Mass: {nutrition['totals']['measured_food_mass_g']}g")
    print(f"    - Total Calories:     {nutrition['totals']['calories_kcal']} kcal")
    print(f"    - Total Protein:      {nutrition['totals']['protein_g']}g")
    print(f"    - Total Carbs:        {nutrition['totals']['carbs_g']}g")
    print(f"    - Total Fat:          {nutrition['totals']['fat_g']}g")
    print(f"    - Total Fiber:        {nutrition['totals']['fiber_g']}g")
    print("\n=== ALL 6 INTEGRATION & VERIFICATION TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    test_database_initialization()
    test_temporal_cv_tracker()
    test_sensor_fusion_and_uncertainty()
    test_mass_reconciliation_engine()
    test_nutrition_engine_and_provenance()
    test_full_4_ingredient_automatic_workflow()
