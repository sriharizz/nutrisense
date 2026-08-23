# NutriSense — Frontend UI Integration Contract

## WebSocket Messaging
- Client connects to `ws://localhost:8000/ws/live`
- Receives JSON events:
  - `WEIGHT_UPDATE`: `{ "weight_g": 241.7, "stable": true }`
  - `REMOVAL_EVENT`: `{ "item": "tomato", "weight_g": 78.7, "calories": 14.2 }`
  - `STATE_CHANGE`: `{ "state": "MEASUREMENT_ACTIVE" }`
