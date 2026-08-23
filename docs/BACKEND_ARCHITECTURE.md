# NutriSense — Backend Architecture & Service Layer

## 1. Technology Stack
- **Framework:** FastAPI (Python 3.11)
- **ASGI Server:** Uvicorn
- **Database:** SQLite 3 (`nutrisense.db`)
- **Concurrency:** Asynchronous Event Loops (`asyncio`) + WebSockets

## 2. Services Breakdown
1. **`HardwareService`:** Validates and buffers incoming scale payloads.
2. **`WeightStabilizer`:** Detects platform settlement and stable baselines.
3. **`CVObserver`:** Interface wrapping YOLOv8 inferences.
4. **`SensorFusionEngine`:** Pairs CV disappearance with weight drop.
5. **`NutritionEngine`:** Computes calories and macronutrients from measured mass.
