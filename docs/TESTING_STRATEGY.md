# NutriSense — Automated Testing Strategy

## Test Suites
1. `test_hardware_simulator.py`: Test mock ESP32 telemetry producer.
2. `test_weight_stabilizer.py`: Test noise filtering & stability detection.
3. `test_state_machine.py`: Verify all session state transitions.
4. `test_sensor_fusion.py`: Test pairing of weight drop + CV disappearance.
5. `test_nutrition_engine.py`: Test macronutrient & calorie calculations.
