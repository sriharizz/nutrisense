# NutriSense — Computer Vision Subsystem Integration

## 1. Engine & Model
- **Model:** YOLOv8 Nano (`nutrisense_model/v4/weights/best.pt`)
- **Vocabulary:** 26 native classes (Tomato, Onion, Carrot, Cucumber, Egg, etc.)
- **Threshold:** `conf >= 0.40` (configurable via `CV_CONFIDENCE_THRESHOLD`)

## 2. Temporal Difference Algorithm
$$	ext{Removed Set} = \mathcal{S}_{	ext{before}} \setminus \mathcal{S}_{	ext{after}}$$
- If $|	ext{Removed Set}| = 1$: Identity confirmed.
- If $|	ext{Removed Set}| > 1$: `CV_UNCERTAIN` event raised; request manual verification or wait for visual stabilization.
