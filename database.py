"""
NutriSense Database & Telemetry Persistence Layer
Manages normalized SQLite relational schema for auditable session storage,
weight readings, CV observations, removal events, and nutritional data provenance.
"""
import sqlite3
import json
import time
from typing import Optional, List, Dict, Any

DB_PATH = "nutrisense.db"

def get_db_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_database(db_path: str = DB_PATH) -> None:
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    # 1. Devices table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            device_id TEXT PRIMARY KEY,
            sensor_type TEXT NOT NULL,
            firmware_ver TEXT,
            ip_address TEXT,
            last_seen REAL NOT NULL
        )
    """)

    # 2. Measurement sessions table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS measurement_sessions (
            session_id TEXT PRIMARY KEY,
            start_time REAL NOT NULL,
            end_time REAL,
            initial_weight_g REAL DEFAULT 0.0,
            final_weight_g REAL DEFAULT 0.0,
            sum_removed_g REAL DEFAULT 0.0,
            reconciliation_error_g REAL DEFAULT 0.0,
            reconciliation_error_pct REAL DEFAULT 0.0,
            reconciliation_status TEXT DEFAULT 'PENDING',
            state TEXT NOT NULL,
            status TEXT DEFAULT 'IN_PROGRESS'
        )
    """)

    # 3. Raw & filtered weight readings table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS weight_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            device_id TEXT,
            raw_weight_g REAL NOT NULL,
            filtered_weight_g REAL NOT NULL,
            is_stable INTEGER NOT NULL,
            std_dev REAL,
            timestamp REAL NOT NULL,
            FOREIGN KEY (session_id) REFERENCES measurement_sessions(session_id)
        )
    """)

    # 4. CV observations table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cv_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            frame_timestamp REAL NOT NULL,
            detected_items_json TEXT NOT NULL,
            box_count INTEGER NOT NULL,
            avg_confidence REAL,
            timestamp REAL NOT NULL,
            FOREIGN KEY (session_id) REFERENCES measurement_sessions(session_id)
        )
    """)

    # 5. Removal events table (immutable audit records)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS removal_events (
            event_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            ingredient TEXT NOT NULL,
            weight_before_g REAL NOT NULL,
            weight_after_g REAL NOT NULL,
            weight_delta_g REAL NOT NULL,
            cv_confidence REAL NOT NULL,
            sync_latency_ms REAL DEFAULT 0.0,
            status TEXT NOT NULL,
            timestamp REAL NOT NULL,
            FOREIGN KEY (session_id) REFERENCES measurement_sessions(session_id)
        )
    """)

    # 6. Nutrition results table with exact provenance formulas
    cur.execute("""
        CREATE TABLE IF NOT EXISTS nutrition_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            event_id TEXT,
            ingredient TEXT NOT NULL,
            measured_weight_g REAL NOT NULL,
            edible_mass_g REAL NOT NULL,
            calories_kcal REAL NOT NULL,
            protein_g REAL NOT NULL,
            carbs_g REAL NOT NULL,
            fat_g REAL NOT NULL,
            fiber_g REAL NOT NULL,
            reference_source TEXT NOT NULL,
            calculation_formula TEXT NOT NULL,
            timestamp REAL NOT NULL,
            FOREIGN KEY (session_id) REFERENCES measurement_sessions(session_id),
            FOREIGN KEY (event_id) REFERENCES removal_events(event_id)
        )
    """)

    # 7. System & State Machine Transition Events
    cur.execute("""
        CREATE TABLE IF NOT EXISTS system_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            event_type TEXT NOT NULL,
            prev_state TEXT,
            next_state TEXT,
            message TEXT NOT NULL,
            details_json TEXT,
            timestamp REAL NOT NULL
        )
    """)

    # 8. ICMR-NIN Food Composition Reference Database
    cur.execute("PRAGMA table_info(icmr_database)")
    existing_cols = [c[1] for c in cur.fetchall()]
    
    if not existing_cols:
        cur.execute("""
            CREATE TABLE icmr_database (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT UNIQUE NOT NULL,
                calories_per_100g REAL DEFAULT 0.0,
                protein REAL DEFAULT 0.0,
                carbs REAL DEFAULT 0.0,
                fat REAL DEFAULT 0.0,
                fiber REAL DEFAULT 0.0,
                edible_yield REAL DEFAULT 1.0,
                unit_weight REAL DEFAULT 100.0,
                reference_source TEXT DEFAULT 'ICMR-NIN IFCT 2017'
            )
        """)
    else:
        # Migrate table if missing columns
        if "calories_per_100g" not in existing_cols:
            cur.execute("ALTER TABLE icmr_database ADD COLUMN calories_per_100g REAL DEFAULT 0.0")
        if "fiber" not in existing_cols:
            cur.execute("ALTER TABLE icmr_database ADD COLUMN fiber REAL DEFAULT 0.0")
        if "reference_source" not in existing_cols:
            cur.execute("ALTER TABLE icmr_database ADD COLUMN reference_source TEXT DEFAULT 'ICMR-NIN IFCT 2017'")

    # Seed data for all 26 classes
    seed_icmr_data = [
        ("tomato", 18.0, 0.9, 3.9, 0.2, 1.2, 0.96, 90.0, "ICMR-NIN IFCT 2017 (Tomato, red)"),
        ("onion", 40.0, 1.1, 9.3, 0.1, 1.7, 0.90, 110.0, "ICMR-NIN IFCT 2017 (Onion, big)"),
        ("cucumber", 15.0, 0.7, 3.6, 0.1, 0.5, 0.85, 150.0, "ICMR-NIN IFCT 2017 (Cucumber, green)"),
        ("carrot", 41.0, 0.9, 9.6, 0.2, 2.8, 0.85, 80.0, "ICMR-NIN IFCT 2017 (Carrot, orange)"),
        ("bellpepper", 24.0, 1.0, 5.3, 0.2, 1.4, 0.88, 120.0, "ICMR-NIN IFCT 2017 (Capsicum green)"),
        ("potato", 77.0, 2.0, 17.5, 0.1, 2.2, 0.85, 150.0, "ICMR-NIN IFCT 2017 (Potato, tuber)"),
        ("egg", 143.0, 12.6, 0.7, 9.5, 0.0, 0.88, 50.0, "ICMR-NIN IFCT 2017 (Egg, whole raw)"),
        ("eggplant", 25.0, 1.0, 5.9, 0.2, 3.0, 0.90, 180.0, "ICMR-NIN IFCT 2017 (Brinjal)"),
        ("garlic", 149.0, 6.4, 33.1, 0.5, 2.1, 0.88, 5.0, "ICMR-NIN IFCT 2017 (Garlic, cloves)"),
        ("green_onion", 32.0, 1.8, 7.3, 0.2, 2.6, 0.85, 30.0, "ICMR-NIN IFCT 2017 (Spring onion)"),
        ("radish", 16.0, 0.7, 3.4, 0.1, 1.6, 0.85, 100.0, "ICMR-NIN IFCT 2017 (Radish, white)"),
        ("pumpkin", 26.0, 1.0, 6.5, 0.1, 0.5, 0.80, 250.0, "ICMR-NIN IFCT 2017 (Pumpkin)"),
        ("mushroom", 22.0, 3.1, 3.3, 0.3, 1.0, 0.95, 20.0, "USDA FoodData Central (Mushroom, white)"),
        ("lettuce", 15.0, 1.4, 2.9, 0.2, 1.3, 0.90, 80.0, "USDA FoodData Central (Lettuce, green leaf)"),
        ("koreancabbage", 16.0, 1.2, 3.2, 0.2, 1.2, 0.88, 300.0, "USDA FoodData Central (Napa cabbage)"),
        ("mungbeansprout", 30.0, 3.0, 5.9, 0.2, 1.8, 1.0, 50.0, "USDA FoodData Central (Mung bean sprouts)"),
        ("tofu", 76.0, 8.1, 1.9, 4.8, 0.3, 1.0, 100.0, "USDA FoodData Central (Tofu, firm)"),
        ("chicken", 165.0, 31.0, 0.0, 3.6, 0.0, 0.80, 150.0, "ICMR-NIN IFCT 2017 (Chicken breast, raw)"),
        ("beaf", 250.0, 26.0, 0.0, 15.0, 0.0, 0.85, 150.0, "USDA FoodData Central (Beef, raw)"),
        ("pork", 242.0, 27.0, 0.0, 14.0, 0.0, 0.85, 150.0, "USDA FoodData Central (Pork, raw)"),
        ("fish", 105.0, 20.0, 0.0, 2.5, 0.0, 0.75, 120.0, "ICMR-NIN IFCT 2017 (Fish, Rohu raw)"),
        ("shrimp", 85.0, 20.1, 0.2, 0.5, 0.0, 0.65, 30.0, "ICMR-NIN IFCT 2017 (Prawn / Shrimp)"),
        ("squid", 92.0, 15.6, 3.1, 1.4, 0.0, 0.70, 80.0, "USDA FoodData Central (Squid, raw)"),
        ("chili", 40.0, 1.9, 8.8, 0.4, 1.5, 0.90, 15.0, "ICMR-NIN IFCT 2017 (Green chilli)"),
        ("sausage", 301.0, 12.0, 2.0, 27.0, 0.0, 1.0, 60.0, "USDA FoodData Central (Pork sausage)"),
        ("kimchi", 15.0, 1.1, 2.4, 0.5, 1.6, 1.0, 50.0, "USDA FoodData Central (Kimchi)")
    ]

    for item in seed_icmr_data:
        cur.execute("""
            INSERT INTO icmr_database 
            (item_name, calories_per_100g, protein, carbs, fat, fiber, edible_yield, unit_weight, reference_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_name) DO UPDATE SET
                calories_per_100g=excluded.calories_per_100g,
                protein=excluded.protein,
                carbs=excluded.carbs,
                fat=excluded.fat,
                fiber=excluded.fiber,
                edible_yield=excluded.edible_yield,
                unit_weight=excluded.unit_weight,
                reference_source=excluded.reference_source
        """, item)

    conn.commit()
    conn.close()
    print("[Database] Initialized and verified normalized SQLite schema in", db_path)

def record_system_event(session_id: Optional[str], event_type: str, prev_state: Optional[str],
                        next_state: Optional[str], message: str, details: Optional[Dict[str, Any]] = None):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO system_events (session_id, event_type, prev_state, next_state, message, details_json, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (session_id, event_type, prev_state, next_state, message, json.dumps(details or {}), time.time()))
    conn.commit()
    conn.close()

def save_weight_reading(session_id: Optional[str], device_id: str, raw_g: float,
                        filtered_g: float, is_stable: bool, std_dev: float):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO weight_readings (session_id, device_id, raw_weight_g, filtered_weight_g, is_stable, std_dev, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (session_id, device_id, raw_g, filtered_g, 1 if is_stable else 0, std_dev, time.time()))
    conn.commit()
    conn.close()

def save_cv_observation(session_id: Optional[str], detected_items: List[Dict[str, Any]],
                        avg_confidence: float, frame_timestamp: Optional[float] = None):
    conn = get_db_connection()
    cur = conn.cursor()
    now = time.time()
    cur.execute("""
        INSERT INTO cv_observations (session_id, frame_timestamp, detected_items_json, box_count, avg_confidence, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (session_id, frame_timestamp or now, json.dumps(detected_items), len(detected_items), avg_confidence, now))
    conn.commit()
    conn.close()

def save_removal_event(event_id: str, session_id: str, ingredient: str, weight_before_g: float,
                       weight_after_g: float, weight_delta_g: float, cv_confidence: float,
                       sync_latency_ms: float = 0.0, status: str = "COMMITTED"):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO removal_events 
        (event_id, session_id, ingredient, weight_before_g, weight_after_g, weight_delta_g, cv_confidence, sync_latency_ms, status, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (event_id, session_id, ingredient, weight_before_g, weight_after_g, weight_delta_g, cv_confidence, sync_latency_ms, status, time.time()))
    conn.commit()
    conn.close()

def save_nutrition_result(session_id: str, event_id: str, ingredient: str, measured_weight_g: float,
                          edible_mass_g: float, calories_kcal: float, protein_g: float,
                          carbs_g: float, fat_g: float, fiber_g: float,
                          reference_source: str, calculation_formula: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO nutrition_results
        (session_id, event_id, ingredient, measured_weight_g, edible_mass_g, calories_kcal, protein_g, carbs_g, fat_g, fiber_g, reference_source, calculation_formula, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (session_id, event_id, ingredient, measured_weight_g, edible_mass_g, calories_kcal, protein_g, carbs_g, fat_g, fiber_g, reference_source, calculation_formula, time.time()))
    conn.commit()
    conn.close()

def create_measurement_session(session_id: str, state: str = "STARTING"):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO measurement_sessions 
        (session_id, start_time, state, status)
        VALUES (?, ?, ?, 'IN_PROGRESS')
    """, (session_id, time.time(), state))
    conn.commit()
    conn.close()

def update_session_reconciliation(session_id: str, initial_weight_g: float, final_weight_g: float,
                                  sum_removed_g: float, error_g: float, error_pct: float,
                                  rec_status: str, session_state: str, status: str = "COMPLETED"):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE measurement_sessions
        SET end_time = ?, initial_weight_g = ?, final_weight_g = ?, sum_removed_g = ?,
            reconciliation_error_g = ?, reconciliation_error_pct = ?, reconciliation_status = ?,
            state = ?, status = ?
        WHERE session_id = ?
    """, (time.time(), initial_weight_g, final_weight_g, sum_removed_g, error_g, error_pct, rec_status, session_state, status, session_id))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_database()


# ==========================================
# Family Profiles & Smart Pantry Functions
# ==========================================

def get_all_family_profiles(db_path: str = "nutrisense.db"):
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM family_profiles ORDER BY profile_id")
    rows = cur.fetchall()
    
    # Calculate today's consumed for each profile
    import time
    start_of_day = time.time() - (time.time() % 86400)
    
    profiles = []
    for r in rows:
        p = dict(r)
        cur.execute("""
            SELECT COALESCE(SUM(calories), 0) as total_cal,
                   COALESCE(SUM(protein), 0) as total_prot,
                   COALESCE(SUM(carbs), 0) as total_carbs,
                   COALESCE(SUM(fat), 0) as total_fat,
                   COALESCE(SUM(fiber), 0) as total_fiber
            FROM meal_intake_logs
            WHERE profile_id = ? AND timestamp >= ?
        """, (p["profile_id"], start_of_day))
        stats = cur.fetchone()
        p["today_consumed"] = {
            "calories": round(stats["total_cal"], 1),
            "protein_g": round(stats["total_prot"], 1),
            "carbs_g": round(stats["total_carbs"], 1),
            "fat_g": round(stats["total_fat"], 1),
            "fiber_g": round(stats["total_fiber"], 1)
        }
        
        cur.execute("""
            SELECT meal_name, portion_weight_g, calories, protein, carbs, fat, fiber, timestamp
            FROM meal_intake_logs
            WHERE profile_id = ?
            ORDER BY timestamp DESC
            LIMIT 6
        """, (p["profile_id"],))
        recent_rows = cur.fetchall()
        import datetime
        p["recent_logs"] = [
            {
                "meal_name": r["meal_name"],
                "portion_weight_g": round(r["portion_weight_g"], 1),
                "calories": round(r["calories"], 1),
                "time_str": datetime.datetime.fromtimestamp(r["timestamp"]).strftime("%I:%M %p").lstrip("0")
            }
            for r in recent_rows
        ]
        profiles.append(p)
    conn.close()
    return profiles

def set_active_profile(profile_id: str, db_path: str = "nutrisense.db"):
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("UPDATE family_profiles SET is_active = 0")
    cur.execute("UPDATE family_profiles SET is_active = 1 WHERE profile_id = ?", (profile_id,))
    conn.commit()
    conn.close()

def add_family_profile(name: str, avatar: str = '👤', age: int = 25,
                       target_cal: float = 2000.0, target_prot: float = 60.0,
                       target_carbs: float = 250.0, target_fat: float = 50.0,
                       target_fiber: float = 30.0, db_path: str = "nutrisense.db"):
    import uuid
    pid = f"prof_{uuid.uuid4().hex[:6]}"
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO family_profiles (profile_id, name, avatar, age, target_calories, target_protein, target_carbs, target_fat, target_fiber, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
    """, (pid, name, avatar, age, target_cal, target_prot, target_carbs, target_fat, target_fiber))
    conn.commit()
    conn.close()
    return pid

def log_meal_intake(profile_id: str, meal_name: str, portion_weight_g: float,
                    calories: float, protein: float, carbs: float, fat: float, fiber: float,
                    session_id: str = None, db_path: str = "nutrisense.db"):
    import uuid, time
    lid = f"log_{uuid.uuid4().hex[:6]}"
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO meal_intake_logs (log_id, profile_id, session_id, meal_name, portion_weight_g, calories, protein, carbs, fat, fiber, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (lid, profile_id, session_id, meal_name, portion_weight_g, calories, protein, carbs, fat, fiber, time.time()))
    conn.commit()
    conn.close()
    return lid

def get_pantry_inventory(db_path: str = "nutrisense.db"):
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM smart_pantry ORDER BY item_name")
    rows = cur.fetchall()
    conn.close()
    pantry = []
    for r in rows:
        item = dict(r)
        item["is_low_stock"] = item["current_stock_g"] <= item["threshold_g"]
        pantry.append(item)
    return pantry

def deduct_pantry_item(item_name: str, used_grams: float, db_path: str = "nutrisense.db"):
    import time
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT current_stock_g FROM smart_pantry WHERE item_name = ?", (item_name.lower(),))
    row = cur.fetchone()
    if row:
        new_stock = max(0.0, round(row["current_stock_g"] - used_grams, 1))
        cur.execute("UPDATE smart_pantry SET current_stock_g = ?, last_updated = ? WHERE item_name = ?", (new_stock, time.time(), item_name.lower()))
    conn.commit()
    conn.close()
