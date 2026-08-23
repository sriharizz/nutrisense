"""
NutriSense Nutrition Calculation Engine
Computes portion-specific macronutrients (calories, protein, carbs, fat, fiber)
with explicit data provenance, formula traceability, and ICMR-NIN reference backing.
"""
import sqlite3
from typing import Dict, Any, List, Optional
import database

class NutritionEngine:
    def __init__(self, db_path: str = "nutrisense.db"):
        self.db_path = db_path

    def calculate_ingredient_nutrition(self, ingredient: str, measured_weight_g: float,
                                       session_id: Optional[str] = None,
                                       event_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Calculates portion-specific nutrition for a single measured ingredient mass.
        """
        conn = database.get_db_connection(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            SELECT item_name, calories_per_100g, protein, carbs, fat, fiber, edible_yield, unit_weight, reference_source
            FROM icmr_database WHERE item_name = ?
        """, (ingredient.lower(),))
        row = cur.fetchone()
        conn.close()

        if not row:
            # Standard reference fallback
            ref_cal = 30.0
            ref_prot = 1.0
            ref_carb = 5.0
            ref_fat = 0.5
            ref_fib = 1.0
            edible_yield = 1.0
            source_name = "NutriSense Generic Reference (Estimated)"
        else:
            ref_cal = float(row["calories_per_100g"])
            ref_prot = float(row["protein"])
            ref_carb = float(row["carbs"])
            ref_fat = float(row["fat"])
            ref_fib = float(row["fiber"])
            edible_yield = float(row["edible_yield"])
            source_name = row["reference_source"] or "ICMR-NIN IFCT 2017"

        # Calculate edible portion
        edible_mass_g = round(measured_weight_g * edible_yield, 1)
        
        # Calculate nutrients per measured mass
        # Formula: (nutrient_per_100g * edible_mass_g) / 100
        protein_g = round((ref_prot * edible_mass_g) / 100.0, 2)
        carbs_g   = round((ref_carb * edible_mass_g) / 100.0, 2)
        fat_g     = round((ref_fat  * edible_mass_g) / 100.0, 2)
        fiber_g   = round((ref_fib  * edible_mass_g) / 100.0, 2)
        
        # Calories: computed from reference calories per 100g * mass, or Atwater 4-4-9
        if ref_cal > 0.0:
            calories_kcal = round((ref_cal * edible_mass_g) / 100.0, 1)
        else:
            calories_kcal = round(protein_g * 4.0 + carbs_g * 4.0 + fat_g * 9.0, 1)

        formula_str = (
            f"Edible Mass: {measured_weight_g}g * {edible_yield} = {edible_mass_g}g | "
            f"Calories: ({ref_cal} kcal/100g * {edible_mass_g}g) / 100 = {calories_kcal} kcal | "
            f"Protein: ({ref_prot}g/100g * {edible_mass_g}g) / 100 = {protein_g}g | "
            f"Carbs: ({ref_carb}g/100g * {edible_mass_g}g) / 100 = {carbs_g}g | "
            f"Fat: ({ref_fat}g/100g * {edible_mass_g}g) / 100 = {fat_g}g | "
            f"Fiber: ({ref_fib}g/100g * {edible_mass_g}g) / 100 = {fiber_g}g"
        )

        result = {
            "ingredient": ingredient,
            "measured_weight_g": round(measured_weight_g, 1),
            "edible_mass_g": edible_mass_g,
            "edible_yield": edible_yield,
            "calories_kcal": calories_kcal,
            "protein_g": protein_g,
            "carbs_g": carbs_g,
            "fat_g": fat_g,
            "fiber_g": fiber_g,
            "reference_source": source_name,
            "calculation_formula": formula_str,
            "provenance_note": "Nutritional estimate based on measured mass and reference food composition data."
        }

        # Save to database if session is provided
        if session_id:
            try:
                database.save_nutrition_result(
                    session_id=session_id,
                    event_id=event_id or "",
                    ingredient=ingredient,
                    measured_weight_g=measured_weight_g,
                    edible_mass_g=edible_mass_g,
                    calories_kcal=calories_kcal,
                    protein_g=protein_g,
                    carbs_g=carbs_g,
                    fat_g=fat_g,
                    fiber_g=fiber_g,
                    reference_source=source_name,
                    calculation_formula=formula_str
                )
            except Exception as e:
                print(f"[Nutrition Save Error] {e}")

        return result

    def calculate_session_nutrition(self, removals_list: List[Dict[str, Any]], session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Calculates total and per-ingredient nutrition for all committed removals in a session.
        """
        items_breakdown = []
        total_calories = 0.0
        total_protein = 0.0
        total_carbs = 0.0
        total_fat = 0.0
        total_fiber = 0.0
        total_measured_mass = 0.0
        total_edible_mass = 0.0

        for r in removals_list:
            if r.get("status") == "COMMITTED":
                ing = r.get("ingredient", "unknown")
                wt = r.get("weight_delta_g", 0.0)
                evt_id = r.get("event_id", "")
                
                nut = self.calculate_ingredient_nutrition(ing, wt, session_id=session_id, event_id=evt_id)
                items_breakdown.append(nut)
                
                total_calories += nut["calories_kcal"]
                total_protein  += nut["protein_g"]
                total_carbs    += nut["carbs_g"]
                total_fat      += nut["fat_g"]
                total_fiber    += nut["fiber_g"]
                total_measured_mass += nut["measured_weight_g"]
                total_edible_mass   += nut["edible_mass_g"]

        return {
            "totals": {
                "measured_food_mass_g": round(total_measured_mass, 1),
                "edible_mass_g": round(total_edible_mass, 1),
                "calories_kcal": round(total_calories, 1),
                "protein_g": round(total_protein, 2),
                "carbs_g": round(total_carbs, 2),
                "fat_g": round(total_fat, 2),
                "fiber_g": round(total_fiber, 2),
            },
            "items": items_breakdown,
            "ingredient_count": len(items_breakdown),
            "disclaimer": "Nutritional estimates calculated from measured portion mass and reference food composition data (ICMR-NIN / USDA)."
        }


class MassReconciliationEngine:
    @staticmethod
    def reconcile(initial_total_weight_g: float, removals_list: list) -> dict:
        sum_removed = round(sum(r.get("weight_delta_g", 0.0) for r in removals_list), 1)
        err = round(initial_total_weight_g - sum_removed, 1)
        pct = round((err / initial_total_weight_g * 100.0) if initial_total_weight_g > 0 else 0.0, 2)
        status = "PASSED" if (abs(pct) <= 5.0 or abs(err) <= 10.0) else "WARNING"
        return {
            "initial_weight_g": initial_total_weight_g,
            "sum_removed_g": sum_removed,
            "reconciliation_error_g": err,
            "error_percentage": pct,
            "status": status
        }
