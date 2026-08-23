import time
import uuid
from enum import Enum
from typing import Dict, Any, List, Optional, Set
import database
from nutrition_engine import NutritionEngine, MassReconciliationEngine

nutrition_engine = NutritionEngine()

class SessionState(Enum):
    IDLE = "IDLE"
    STARTING = "STARTING"
    TARING = "TARING"
    WAITING_FOR_INGREDIENTS = "WAITING_FOR_INGREDIENTS"
    DETECTING_INGREDIENTS = "DETECTING_INGREDIENTS"
    WAITING_FOR_INITIAL_STABLE_WEIGHT = "WAITING_FOR_INITIAL_STABLE_WEIGHT"
    MEASUREMENT_ACTIVE = "MEASUREMENT_ACTIVE"
    POSSIBLE_REMOVAL = "POSSIBLE_REMOVAL"
    WAITING_FOR_POST_REMOVAL_STABILITY = "WAITING_FOR_POST_REMOVAL_STABILITY"
    REMOVAL_VALIDATION = "REMOVAL_VALIDATION"
    REMOVAL_COMMITTED = "REMOVAL_COMMITTED"
    COMPLETING = "COMPLETING"
    NUTRITION_CALCULATION = "NUTRITION_CALCULATION"
    COMPLETE = "COMPLETE"

class SessionStateMachine:
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or f"session_{int(time.time())}"
        self.state = SessionState.IDLE
        self.start_time = time.time()
        self.end_time = None
        self.initial_weight_g = 0.0
        self.current_weight_g = 0.0
        self.baseline_weight_g = 0.0
        
        # Zone tracking: zone_id (1, 2, 3, 4) -> item_name (e.g. {1: 'tomato', 2: 'onion', 3: 'onion'})
        self.zone_map: Dict[int, Optional[str]] = {1: None, 2: None, 3: None, 4: None}
        self.initial_scene_list: List[str] = []
        self.current_scene_set: Set[str] = set()
        
        self.removal_history: List[Dict[str, Any]] = []
        self.transition_history: List[Dict[str, Any]] = []
        
        # Debouncing & Stabilization Tracking
        self.drop_start_time = 0.0
        self.drop_start_weight = 0.0
        self.last_removal_time = 0.0
        self.last_stable_weight = 0.0
        self.stable_counter = 0

    def transition_to(self, new_state: SessionState, reason: str = "", details: Optional[Dict[str, Any]] = None):
        old_state = self.state
        self.state = new_state
        entry = {
            "from_state": old_state.value if isinstance(old_state, SessionState) else str(old_state),
            "to_state": new_state.value if isinstance(new_state, SessionState) else str(new_state),
            "reason": reason,
            "details": details or {},
            "timestamp": time.time()
        }
        self.transition_history.append(entry)
        try:
            database.log_state_transition(
                self.session_id,
                entry["from_state"],
                entry["to_state"],
                reason,
                entry["details"]
            )
        except Exception:
            pass

    def start_session(self, current_weight_g: float = 0.0, current_items: Optional[List[str]] = None, current_zones: Optional[List[Dict]] = None) -> Dict[str, Any]:
        self.start_time = time.time()
        self.removal_history = []
        self.transition_history = []
        self.last_removal_time = 0.0
        self.drop_start_time = 0.0
        self.zone_map = {1: None, 2: None, 3: None, 4: None}
        
        items = []
        if current_zones:
            for z in current_zones:
                zid = z.get("zone_id")
                zitem = z.get("item")
                if zitem and z.get("status") == "OCCUPIED":
                    self.zone_map[zid] = zitem.lower()
                    items.append(zitem.lower())
        elif current_items:
            items = [it.lower() for it in current_items]
            for idx, it in enumerate(items):
                if idx < 4:
                    self.zone_map[idx + 1] = it

        self.initial_scene_list = list(items)
        self.current_scene_set = set(items)

        database.create_measurement_session(self.session_id, state=SessionState.MEASUREMENT_ACTIVE.value)

        if current_weight_g > 15.0:
            self.initial_weight_g = round(current_weight_g, 1)
            self.baseline_weight_g = round(current_weight_g, 1)
            self.transition_to(SessionState.MEASUREMENT_ACTIVE, f"Session started with initial load {current_weight_g:.1f}g ({items})")
        else:
            self.initial_weight_g = 0.0
            self.baseline_weight_g = 0.0
            self.transition_to(SessionState.WAITING_FOR_INGREDIENTS, "Session started. Place ingredients on scale.")
            
        return self.get_summary()

    def process_scale_and_cv(self, weight_info: Dict[str, Any], cv_detected_set: Set[str],
                             cv_confidence_map: Optional[Dict[str, float]] = None,
                             zones: Optional[List[Dict]] = None) -> Dict[str, Any]:
        weight_g = weight_info.get("filtered_g", weight_info.get("raw_g", 0.0))
        is_stable = weight_info.get("is_stable", True)
        now = time.time()
        
        self.current_weight_g = round(weight_g, 1)
        self.current_scene_set = set(cv_detected_set)
        action_event = None

        # Dynamically populate zone occupants if any zone is detected as occupied
        if zones:
            for z in zones:
                zid = z.get("zone_id")
                zitem = z.get("item")
                if zitem and z.get("status") == "OCCUPIED":
                    # Only register if not already empty due to a confirmed removal
                    if self.zone_map.get(zid) is None and (now - self.last_removal_time) >= 2.0:
                        self.zone_map[zid] = zitem.lower()

        # 1. If waiting for ingredients and mass is placed on scale
        if self.state in (SessionState.WAITING_FOR_INGREDIENTS, SessionState.DETECTING_INGREDIENTS, SessionState.WAITING_FOR_INITIAL_STABLE_WEIGHT, SessionState.STARTING, SessionState.TARING):
            if weight_g > 5.0:
                self.initial_weight_g = round(weight_g, 1)
                self.baseline_weight_g = round(weight_g, 1)
                self.transition_to(
                    SessionState.MEASUREMENT_ACTIVE,
                    f"Initial load locked: {weight_g:.1f}g with zones: {self.zone_map}"
                )

        # 2. MEASUREMENT_ACTIVE: Detect potential start of a removal
        elif self.state == SessionState.MEASUREMENT_ACTIVE:
            if (now - self.last_removal_time) >= 2.0:
                weight_drop = round(self.baseline_weight_g - weight_g, 1)
                if weight_drop >= 15.0: # Minimum 15g threshold
                    self.drop_start_time = now
                    self.drop_start_weight = self.baseline_weight_g
                    self.last_stable_weight = weight_g
                    self.stable_counter = 1
                    self.transition_to(
                        SessionState.POSSIBLE_REMOVAL,
                        f"Weight drop detected (-{weight_drop:.1f}g). Settling scale reading..."
                    )

        # 3. POSSIBLE_REMOVAL: Settle scale and find exactly which zone cleared
        elif self.state in (SessionState.POSSIBLE_REMOVAL, SessionState.WAITING_FOR_POST_REMOVAL_STABILITY, SessionState.REMOVAL_VALIDATION):
            if abs(weight_g - self.last_stable_weight) <= 2.5:
                self.stable_counter += 1
            else:
                self.stable_counter = 1
                self.last_stable_weight = weight_g

            # Settled after 4 consecutive samples (~0.8s) or 1.2s total
            if self.stable_counter >= 4 or (now - self.drop_start_time) >= 1.2:
                final_drop = round(self.drop_start_weight - weight_g, 1)
                
                if final_drop >= 15.0:
                    # STRICT ZONE IDENTIFICATION: Find which zone cleared (was occupied, now READY)
                    cleared_item = None
                    cleared_zone_id = None
                    
                    if zones:
                        for z in zones:
                            zid = z.get("zone_id")
                            status = z.get("status")
                            item = z.get("item")
                            # If this zone previously held an ingredient, but is now READY / item is None
                            if self.zone_map.get(zid) and (status == "READY" or not item):
                                cleared_item = self.zone_map[zid]
                                cleared_zone_id = zid
                                break
                    
                    # If zone matching didn't trigger, check remaining occupied zones
                    if not cleared_item:
                        for zid, it in self.zone_map.items():
                            if it:
                                cleared_item = it
                                cleared_zone_id = zid
                                break
                                
                    if not cleared_item:
                        cleared_item = "unknown"

                    conf = (cv_confidence_map or {}).get(cleared_item, 0.95)
                    event_id = f"evt_{int(now)}_{uuid.uuid4().hex[:4]}"
                    
                    # Compute portion nutrition
                    nut = {}
                    try:
                        nut = nutrition_engine.calculate_ingredient_nutrition(cleared_item, final_drop)
                    except Exception:
                        pass

                    commit_record = {
                        "event_id": event_id,
                        "session_id": self.session_id,
                        "ingredient": cleared_item,
                        "zone_id": cleared_zone_id,
                        "weight_before_g": round(self.drop_start_weight, 1),
                        "weight_after_g": round(weight_g, 1),
                        "weight_delta_g": final_drop,
                        "cv_confidence": conf,
                        "status": "COMMITTED",
                        "timestamp": now,
                        "nutrition": nut
                    }
                    self.removal_history.append(commit_record)
                    action_event = commit_record

                    # Mark this zone empty
                    if cleared_zone_id and cleared_zone_id in self.zone_map:
                        self.zone_map[cleared_zone_id] = None

                    try:
                        database.save_removal_event(
                            event_id=event_id,
                            session_id=self.session_id,
                            ingredient=cleared_item,
                            weight_before_g=self.drop_start_weight,
                            weight_after_g=weight_g,
                            weight_delta_g=final_drop,
                            cv_confidence=conf,
                            status="COMMITTED",
                            timestamp=now
                        )
                    except Exception:
                        pass

                    self.transition_to(
                        SessionState.REMOVAL_COMMITTED,
                        f"Quadrant removal committed: Zone {cleared_zone_id} ({cleared_item}) -{final_drop}g"
                    )
                    
                    # Lock new baseline weight
                    self.baseline_weight_g = round(weight_g, 1)
                    self.last_removal_time = now
                    self.stable_counter = 0

                    self.transition_to(
                        SessionState.MEASUREMENT_ACTIVE,
                        f"Baseline updated to {self.baseline_weight_g:.1f}g. Remaining zones: {self.zone_map}"
                    )
                else:
                    self.transition_to(SessionState.MEASUREMENT_ACTIVE, "Transient bounce resolved without net removal.")

        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "current_weight_g": self.current_weight_g,
            "initial_weight_g": self.initial_weight_g,
            "baseline_weight_g": self.baseline_weight_g,
            "is_stable": is_stable,
            "action_event": action_event,
            "removal_history": self.removal_history,
            "zone_map": self.zone_map,
            "detected_ingredients": list(self.current_scene_set),
            "initial_ingredients": self.initial_scene_list
        }

    def end_measurement(self) -> Dict[str, Any]:
        self.end_time = time.time()
        self.transition_to(SessionState.COMPLETING, "Ending measurement session")
        self.transition_to(SessionState.NUTRITION_CALCULATION, "Calculating final portion nutrition and mass reconciliation")
        self.transition_to(SessionState.COMPLETE, "Measurement session successfully completed")
        return self.get_summary()

    def get_summary(self) -> Dict[str, Any]:
        sum_removed = round(sum(r.get("weight_delta_g", 0.0) for r in self.removal_history), 1)
        rec_error_g = round(self.initial_weight_g - sum_removed, 1)
        rec_error_pct = round((rec_error_g / self.initial_weight_g * 100.0) if self.initial_weight_g > 0 else 0.0, 2)
        rec_status = "PASSED" if (abs(rec_error_pct) <= 5.0 or abs(rec_error_g) <= 10.0) else "WARNING"
        
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_sec": round((self.end_time or time.time()) - self.start_time, 1),
            "initial_weight_g": self.initial_weight_g,
            "current_weight_g": self.current_weight_g,
            "baseline_weight_g": self.baseline_weight_g,
            "sum_removed_g": sum_removed,
            "reconciliation_error_g": rec_error_g,
            "reconciliation_error_pct": rec_error_pct,
            "reconciliation_status": rec_status,
            "removal_count": len(self.removal_history),
            "removal_history": self.removal_history,
            "zone_map": self.zone_map,
            "initial_ingredients": self.initial_scene_list,
            "current_ingredients": list(self.current_scene_set),
            "transitions_count": len(self.transition_history)
        }
