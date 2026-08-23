# NutriSense — Measurement State Machine Specification

## 1. States & Flow
```text
[IDLE] -> [TARING] -> [WAITING_FOR_INITIAL_LOAD] -> [INITIAL_WEIGHT_STABLE]
                                                            │
                                                            ▼
                                                  [MEASUREMENT_ACTIVE]
                                                            │
                                                            ▼
                                                   [REMOVAL_DETECTED]
                                                            │
                                                            ▼
                                                  [WEIGHT_STABILIZING]
                                                            │
                                                            ▼
                                                   [REMOVAL_COMMITTED]
```

## 2. State Rules
- **Initial Load:** Established when total weight $> 50.0	ext{ g}$ settles for $\ge 1.5	ext{ s}$.
- **Removal Trigger:** Weight drop $> 10.0	ext{ g}$ AND CV item disappearance.
- **Commit:** Mass delta committed only when scale reading stabilizes at new value.
