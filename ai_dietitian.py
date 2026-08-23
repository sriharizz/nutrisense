"""
NutriSense Groq-Powered AI Clinical Dietitian & Zero-Waste Recipe Engine
Uses Groq LPU inference (groq/compound-mini) with clean, simple, everyday conversational language.
"""
import os
import json
import unicodedata
from typing import Dict, Any, List, Optional
from pathlib import Path

# Load from .env if present
env_file = Path(__file__).resolve().parent / ".env"
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ[k.strip()] = v.strip()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

try:
    from groq import Groq
    groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
except Exception as e:
    print("[AI Dietitian] Groq initialization warning:", e)
    groq_client = None

PRIMARY_MODEL = "groq/compound-mini"

PERSONA_CONTEXT = {
    "hari": {
        "condition": "Active & Workout (Muscle Recovery)",
        "focus": "Clean protein, energy, and muscle recovery."
    },
    "mom": {
        "condition": "Heart Health & Blood Pressure",
        "focus": "Low salt (sodium), healthy potassium, and heart-friendly fresh vegetables."
    },
    "dad": {
        "condition": "Blood Sugar Care (Type-2 Diabetes)",
        "focus": "Low sugar impact, steady energy, and fiber to prevent blood sugar spikes."
    }
}

def clean_text(s: str) -> str:
    if not isinstance(s, str):
        return s
    
    # Explicitly map all unicode dashes/hyphens to ASCII hyphen '-' before NFKD
    dashes = [
        "\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015", "\u2212",
        "–", "—", "−", "‐", "‑", "‒"
    ]
    for d in dashes:
        s = s.replace(d, "-")
        
    # Explicitly map unicode quotes
    quotes = ["\u2018", "\u2019", "‘", "’", "`"]
    for q in quotes:
        s = s.replace(q, "'")
    double_quotes = ["\u201c", "\u201d", "“", "”"]
    for dq in double_quotes:
        s = s.replace(dq, '"')
        
    # Map special spaces
    spaces = ["\u00a0", "\u202f", "\u2009", "\u200b", "\u2002", "\u2003"]
    for sp in spaces:
        s = s.replace(sp, " ")
        
    normalized = unicodedata.normalize('NFKD', s)
    return normalized.encode('ascii', 'ignore').decode('ascii')

def sanitize_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = {}
    for k, v in d.items():
        if isinstance(v, str):
            cleaned[k] = clean_text(v)
        elif isinstance(v, list):
            cleaned[k] = [clean_text(item) if isinstance(item, str) else item for item in v]
        elif isinstance(v, dict):
            cleaned[k] = sanitize_dict(v)
        else:
            cleaned[k] = v
    return cleaned

def analyze_portion_nutrition(person_name: str, meal_name: str, portion_weight_g: float,
                              calories: float, protein_g: float, carbs_g: float,
                              fat_g: float, fiber_g: float,
                              ingredients_used: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Generates ultra-simple, clear, everyday dietary feedback from Groq LLM.
    """
    p_key = person_name.lower()
    persona = PERSONA_CONTEXT.get(p_key, {
        "condition": "Healthy Adult",
        "focus": "Balanced natural nutrients, hydration, and energy."
    })
    
    ingredients_str = ", ".join(ingredients_used) if ingredients_used else "mixed fresh vegetables"

    prompt = f"""
You are the NutriSense AI Family Nutritionist.
Analyze this meal portion prepared on the smart cutting board:

- Person: {person_name} ({persona['condition']})
- Goal: {persona['focus']}
- Portion: {portion_weight_g:.1f}g ({ingredients_str})
- Stats: {calories:.1f} kcal | Protein: {protein_g:.1f}g | Carbs: {carbs_g:.1f}g | Fat: {fat_g:.1f}g | Fiber: {fiber_g:.1f}g

CRITICAL RULES:
1. Speak in super simple, friendly, easy-to-read everyday words (like talking to a friend).
2. Keep it to 1-2 short sentences.
3. Always use standard hyphens '-' for ranges (e.g. 10 - 15 g).

Provide in valid JSON:
{{
    "clinical_verdict": "1-2 super simple sentences explaining how this food helps their goal.",
    "glycemic_index_rating": "Very Low",
    "key_antioxidant": "Simple benefit (e.g. Heart-Healthy Lycopene, Digestive Fiber, Vitamin C)"
}}
"""

    if groq_client:
        try:
            res = groq_client.chat.completions.create(
                model=PRIMARY_MODEL,
                messages=[
                    {"role": "system", "content": "You are a friendly family nutritionist. Speak in super simple, clear words. Respond ONLY with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=200
            )
            raw_text = res.choices[0].message.content.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
            data = json.loads(raw_text.strip())
            return sanitize_dict(data)
        except Exception as e:
            print("[Groq Error in analyze_portion]:", e)

    # Ultra-Simple Default Fallbacks
    if p_key == "dad":
        verdict = f"Very low in sugar with {fiber_g:.1f}g of healthy fiber. Keeps blood sugar steady after meals without sudden spikes."
        gi = "Very Low"
        antiox = "Digestive Fiber"
    elif p_key == "mom":
        verdict = f"Naturally low in salt and rich in potassium. Great for keeping your heart strong and blood pressure balanced."
        gi = "Low"
        antiox = "Heart-Healthy Lycopene"
    else:
        verdict = f"Provides clean energy and {protein_g:.1f}g of protein to help your muscles recover and keep you energized."
        gi = "Low"
        antiox = "Vitamin C & Energy"

    return {
        "clinical_verdict": clean_text(verdict),
        "glycemic_index_rating": gi,
        "key_antioxidant": antiox
    }

def ask_dietitian_chat(question: str, person_name: str = "Hari",
                       today_intake: Optional[Dict[str, Any]] = None,
                       pantry_items: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    Interactive Q&A with Groq AI Dietitian with proper hyphens (e.g. 70-90g, 18-24g).
    """
    p_key = person_name.lower()
    persona = PERSONA_CONTEXT.get(p_key, {
        "condition": "Family Member",
        "focus": "Balanced health and fresh meals."
    })
    
    intake_summary = f"Consumed today: {today_intake.get('calories', 0):.0f} kcal, {today_intake.get('protein_g', 0):.1f}g protein, {today_intake.get('fiber_g', 0):.1f}g fiber." if today_intake else "Logged fresh vegetable dishes today."
    pantry_summary = ", ".join([f"{i['item_name']} ({i.get('current_stock_g', 0):.0f}g)" for i in pantry_items[:6]]) if pantry_items else "Tomato, Onion, Cucumber, Carrot, Eggs in stock."

    prompt = f"""
You are the NutriSense AI Family Nutritionist. Speak in simple, friendly, easy-to-understand conversational English.

Context:
- User asking for: {person_name} ({persona['condition']})
- Today's stats: {intake_summary}
- In the pantry: {pantry_summary}
- User Question: "{question}"

CRITICAL FORMATTING RULES:
1. Always write ranges with a clear hyphen and space, like "70 - 90 g" or "18 - 24 g" or "3 - 4 eggs". Never write numbers back-to-back.
2. Give simple, practical, step-by-step advice in 2-3 friendly sentences.
3. Suggest real meals using what's in the pantry where relevant.
"""

    if groq_client:
        try:
            res = groq_client.chat.completions.create(
                model=PRIMARY_MODEL,
                messages=[
                    {"role": "system", "content": "You are a warm, friendly family nutritionist. Always format number ranges with clear hyphens like '70 - 90 g' and '18 - 24 g'."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,
                max_tokens=250
            )
            raw = res.choices[0].message.content.strip()
            return clean_text(raw)
        except Exception as e:
            print("[Groq Error in ask_dietitian_chat]:", e)

    return f"To reach your goal, try having 3 - 4 boiled eggs or paneer with your fresh cucumber, tomato, and carrot salad to easily add 18 - 24 g of clean protein!"

def generate_zero_waste_pantry_recipes(pantry_items: List[Dict[str, Any]],
                                       recent_logs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Generates a simple zero-waste recipe using what is in the pantry in clear English.
    """
    inventory_summary = ", ".join([f"{i['item_name']}: {i.get('current_stock_g', 0):.0f}g" for i in pantry_items if i.get('current_stock_g', 0) > 0])

    prompt = f"""
You are the NutriSense AI Kitchen Chef.
Available Pantry Ingredients: {inventory_summary}

Suggest 1 simple, delicious recipe to use what's in the pantry so nothing goes to waste. Use simple, friendly words. Always format number ranges with clear hyphens like '8 - 10 min'.

Respond in valid JSON format:
{{
    "recipe_title": "...",
    "estimated_prep_time_min": 10,
    "highlight_ingredients": ["..."],
    "chef_summary": "1-2 simple sentences on how to make this dish and save ingredients from spoiling.",
    "health_benefit": "1 simple sentence on why it is good for the family.",
    "restock_advice": "1 simple sentence on what grocery to buy next."
}}
"""

    if groq_client:
        try:
            res = groq_client.chat.completions.create(
                model=PRIMARY_MODEL,
                messages=[
                    {"role": "system", "content": "You are a friendly kitchen chef. Use simple everyday language. Respond ONLY with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,
                max_tokens=300
            )
            raw_text = res.choices[0].message.content.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
            data = json.loads(raw_text.strip())
            return sanitize_dict(data)
        except Exception as e:
            print("[Groq Error in generate_pantry_recipes]:", e)

    return sanitize_dict({
        "recipe_title": "Fresh Garden Kachumber & Herb Salad",
        "estimated_prep_time_min": 8,
        "highlight_ingredients": ["Cucumber", "Tomato", "Onion", "Carrot"],
        "chef_summary": "Toss freshly chopped cucumber, carrots, tomatoes, and red onions with a squeeze of fresh lemon juice and black pepper for a crunchy side dish.",
        "health_benefit": "Rich in natural Vitamin A, Vitamin C, and fiber to support healthy digestion for the whole family.",
        "restock_advice": "Pantry is running low on protein like eggs or paneer; grab some on your next grocery run."
    })
