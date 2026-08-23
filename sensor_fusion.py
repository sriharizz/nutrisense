"""
NutriSense Sensor Fusion & Mass Reconciliation Subsystem
Coordinates timestamp-synchronized pairing between Computer Vision ingredient disappearance
and load-cell physical mass delta drops, enforcing strict mass conservation checks.
"""
import time
import uuid
from typing import Dict, Any, List, Optional, Set, Tuple
import database

class SensorFusionCoordinator:
    def __init__(self, min_mass_delta_g: float = 8.0, min_cv_confidence: float = 0.40):
        self.min_mass_delta_g = min_mass_delta_g
        self.min_cv_confidence = min_cv_confidence

    def evaluate_removal(self, session_id: str, before_weight_g: float, after_weight_g: float,
                         before_scene: Set[str], after_scene: Set[str],
                         confidence_map: Optional[Dict[str, float]] = None,
                         timestamp: Optional[float] = None) -> Dict[str, Any]:
        """
        Evaluates whether a physical removal occurred and assigns ingredient identity to mass delta.
        Returns evaluation dict with status: 'COMMITTED', 'CV_UNCERTAIN', or 'NO_CHANGE'.
        """
        if timestamp is None:
            timestamp = time.time()
            
        weight_delta_g = round(before_weight_g - after_weight_g, 1)
        disappeared = list(before_scene - after_scene)
        
        # Case 1: Insignificant weight change
        if weight_delta_g < self.min_mass_delta_g:
            return {
                "status": "NO_CHANGE",
                "weight_delta_g": weight_delta_g,
                "disappeared": disappeared,
                "reason": f"Weight delta ({weight_delta_g}g) below threshold ({self.min_mass_delta_g}g)"
            }

        # Case 2: Exactly 1 ingredient disappeared (Unambiguous removal)
        if len(disappeared) == 1:
            ingredient = disappeared[0]
            conf = (confidence_map or {}).get(ingredient, 0.95)
            
            if conf >= self.min_cv_confidence:
                event_id = f"evt_{int(timestamp)}_{uuid.uuid4().hex[:4]}"
                event_record = {
                    "event_id": event_id,
                    "session_id": session_id,
                    "ingredient": ingredient,
                    "weight_before_g": round(before_weight_g, 1),
                    "weight_after_g": round(after_weight_g, 1),
                    "weight_delta_g": weight_delta_g,
                    "cv_confidence": round(conf, 3),
                    "status": "COMMITTED",
                    "timestamp": timestamp,
                    "reason": f"Successfully identified {ingredient} removal with {weight_delta_g}g mass drop"
                }
                
                # Persist to database
                try:
                    database.save_removal_event(
                        event_id=event_id,
                        session_id=session_id,
                        ingredient=ingredient,
                        weight_before_g=round(before_weight_g, 1),
                        weight_after_g=round(after_weight_g, 1),
                        weight_delta_g=weight_delta_g,
                        cv_confidence=round(conf, 3),
                        status="COMMITTED"
                    )
                except Exception as e:
                    print(f"[SensorFusion DB Error] {e}")
                    
                return event_record
            else:
                return {
                    "status": "CV_UNCERTAIN",
                    "ingredient": ingredient,
                    "weight_delta_g": weight_delta_g,
                    "cv_confidence": conf,
                    "reason": f"Disappeared item '{ingredient}' confidence ({conf:.2f}) below threshold ({self.min_cv_confidence})"
                }

        # Case 3: Multiple ingredients disappeared simultaneously
        elif len(disappeared) > 1:
            return {
                "status": "CV_UNCERTAIN",
                "disappeared": disappeared,
                "weight_delta_g": weight_delta_g,
                "reason": f"Multiple simultaneous removals detected: {disappeared}"
            }

        # Case 4: Weight dropped significantly, but no visual disappearance observed (e.g. occlusion)
        else:
            return {
                "status": "CV_UNCERTAIN",
                "disappeared": [],
                "weight_delta_g": weight_delta_g,
                "reason": f"Significant weight drop of {weight_delta_g}g detected without visual ingredient disappearance"
            }

class MassReconciliationEngine:
    @staticmethod
    def reconcile(initial_total_weight_g: float, removals_list: List[Dict[str, Any]],
                  tolerance_pct: float = 5.0, tolerance_abs_g: float = 10.0) -> Dict[str, Any]:
        """
        Calculates mass reconciliation: sum(removals) vs initial_total_weight.
        """
        sum_removed_g = round(sum(r.get("weight_delta_g", 0.0) for r in removals_list if r.get("status") == "COMMITTED"), 1)
        error_g = round(initial_total_weight_g - sum_removed_g, 1)
        
        if initial_total_weight_g > 0.0:
            error_pct = round((abs(error_g) / initial_total_weight_g) * 100.0, 2)
        else:
            error_pct = 0.0
            
        passed = (error_pct <= tolerance_pct) or (abs(error_g) <= tolerance_abs_g)
        status = "PASSED" if passed else "MASS_RECONCILIATION_WARNING"
        
        return {
            "initial_total_weight_g": round(initial_total_weight_g, 1),
            "sum_removed_weights_g": sum_removed_g,
            "reconciliation_error_g": error_g,
            "reconciliation_error_percent": error_pct,
            "tolerance_percent": tolerance_pct,
            "tolerance_abs_g": tolerance_abs_g,
            "status": status,
            "reconciled": passed,
            "message": "Mass reconciliation verified within tolerance" if passed else f"Reconciliation error {error_g}g ({error_pct}%) exceeds tolerance"
        }
