# NutriSense — SQLite Relational Database Schema

## Tables
1. `devices` (device_id, sensor_type, firmware_ver, last_seen)
2. `measurement_sessions` (session_id, start_time, end_time, initial_weight, status)
3. `weight_readings` (id, session_id, weight_g, is_stable, timestamp)
4. `cv_observations` (id, session_id, detected_items_json, timestamp)
5. `removal_events` (id, session_id, item_name, weight_delta_g, confidence, timestamp)
6. `icmr_database` (item_name, protein, carbs, fat, edible_yield, unit_weight)
7. `pantry_inventory` (item_name, current_grams, updated_at)
