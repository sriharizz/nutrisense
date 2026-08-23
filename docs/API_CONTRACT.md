# NutriSense — API Contract Specification (v1)

## Endpoints
- `POST /api/v1/hardware/weight` — ESP32 scale telemetry stream
- `POST /api/v1/sessions/start` — Start new measurement session
- `POST /api/v1/sessions/tare` — Tare scale reading
- `GET /api/v1/sessions/{id}` — Get session status & removal events
- `GET /api/v1/nutrition/summary` — Get active session nutrition breakdown
- `WS /ws/live` — WebSocket stream for real-time frontend updates
