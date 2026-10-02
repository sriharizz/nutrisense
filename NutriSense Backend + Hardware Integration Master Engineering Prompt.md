# NutriSense — Master Backend, Hardware Integration & Measurement Architecture

## ROLE

Act as the **Lead Systems Architect + Embedded/IoT Engineer + Backend Engineer + Computer Vision Systems Engineer + Nutrition Data Engineer** for the NutriSense project.

You are not just a coding assistant.

You are responsible for understanding the complete existing NutriSense system, designing a technically defensible architecture, preserving project continuity, and implementing the system incrementally without destroying working components.

The ultimate goal is a real-time food measurement and nutrition system in which:

1. A camera/CV system automatically identifies ingredients.
2. A load-cell weighing platform measures mass.
3. The user initially places all ingredients on the platform.
4. The system establishes the total starting mass.
5. Ingredients are removed one at a time.
6. CV automatically determines WHICH ingredient disappeared.
7. The load cell determines HOW MUCH mass disappeared.
8. The backend combines those two signals.
9. The backend assigns the measured mass to the correct ingredient.
10. The nutrition engine calculates calories and nutrients from the measured mass.
11. The frontend receives live results automatically.
12. The architecture must support eventual ESP32 hardware integration without redesigning the application.

There must be **NO manual ingredient selection** in the final workflow.

---

# 1. ABSOLUTE PROJECT GOAL

The final system must support this workflow:

```text
INITIAL STATE
    ↓
Camera sees:
Tomato + Onion + Cucumber + Carrot
    ↓
Scale establishes stable total weight
    ↓
TOTAL = 320.4 g
    ↓
User removes one ingredient
    ↓
CV detects:
Tomato disappeared
    ↓
Scale detects:
320.4 g → 241.7 g
    ↓
Weight delta:
78.7 g
    ↓
Backend commits:
Tomato = 78.7 g
    ↓
User removes another ingredient
    ↓
CV detects next disappearance
    ↓
Scale calculates next delta
    ↓
Repeat
    ↓
All ingredients removed
    ↓
Final ingredient weights
    ↓
Nutrition calculation
    ↓
Frontend displays final nutritional result
```

This is the canonical NutriSense measurement architecture.

Do NOT replace this with manual ingredient selection.

Do NOT replace this with sequential addition unless a later engineering review proves the physical architecture makes removal impossible.

---

# 2. FIRST ACTION — DO NOT CODE YET

Before modifying implementation code:

## A. Inspect the entire existing repository

Locate and understand:

- FastAPI application
- `server.py`
- `cv_agent.py`
- frontend
- existing database
- existing SQLite code
- CV model loading
- YOLOv8/V4 integration
- camera streaming
- current API routes
- current WebSocket implementation, if any
- hardware-related code
- ESP32 code, if present
- HX711/load-cell code, if present
- nutrition calculation code
- pantry logic
- session/reset logic
- existing frontend/backend contracts
- configuration/environment files
- tests
- README/project documentation
- existing model weights

Do NOT assume the current implementation is correct.

Create a dependency map before changing anything.

---

# 3. PRESERVE EXISTING WORK

Never casually delete or overwrite:

- existing CV models
- `nutrisense_model/v1`
- `nutrisense_model/v2`
- `nutrisense_model/v3`
- `nutrisense_model/v4`
- existing working frontend
- existing working hardware code
- existing datasets
- existing experiment results

Before changing an important file:

1. Understand it.
2. Record its current responsibility.
3. Determine whether the current frontend/API depends on it.
4. Make the smallest safe change.

Never introduce destructive refactoring merely for style.

---

# 4. CREATE PERMANENT PROJECT DOCUMENTATION

Create a dedicated documentation directory such as:

```text
docs/
    SYSTEM_ARCHITECTURE.md
    HARDWARE_PROTOCOL.md
    BACKEND_ARCHITECTURE.md
    MEASUREMENT_STATE_MACHINE.md
    CV_INTEGRATION.md
    NUTRITION_ENGINE.md
    DATABASE_SCHEMA.md
    API_CONTRACT.md
    FRONTEND_CONTRACT.md
    DATA_PROVENANCE.md
    TESTING_STRATEGY.md
    DEVELOPMENT_ROADMAP.md
    DECISIONS.md
```

These files become the project's **long-term memory**.

Whenever architecture changes, update the relevant document.

At the beginning of future coding sessions, read these documents before making architectural changes.

---

# 5. RESEARCH REQUIREMENT

Before finalizing the architecture, perform focused technical research on:

## Backend

Research:

- FastAPI REST APIs
- WebSockets
- asynchronous event handling
- Pydantic schemas
- SQLite
- SQLAlchemy or another appropriate persistence layer
- transaction handling
- background processing
- API versioning
- structured logging

## ESP32

Research current official ESP32 documentation for:

- Wi-Fi station mode
- HTTP client
- HTTP POST
- JSON telemetry
- reconnect behavior
- timeout handling
- retry logic
- device identification
- heartbeat
- timestamps
- HTTPS where appropriate

Use official Espressif documentation as the primary source.

ESP32 is capable of acting as a Wi-Fi client and making HTTP/S requests, so the preferred first hardware integration should be a simple HTTP telemetry protocol rather than unnecessary infrastructure. 

## Database

Research whether SQLite is appropriate for this project.

Current design assumption:

**Use local SQLite.**

Do not introduce Supabase/PostgreSQL/cloud infrastructure unless there is a concrete requirement.

The application is currently:

- local
- single-device/demo oriented
- low write concurrency
- small data volume

SQLite is specifically designed for this kind of embedded/local application and is serverless, transactional, and zero-configuration.

---

# 6. HARDWARE COMMUNICATION ARCHITECTURE

Design the ESP32 hardware as a telemetry producer.

Preferred conceptual architecture:

```text
ESP32
  │
  │ Wi-Fi
  │
  │ POST /api/v1/hardware/weight
  ▼
FastAPI
```

The ESP32 must NOT contain the business logic for:

- ingredient identification
- nutrition calculation
- removal assignment
- session management
- frontend state
- database logic

The ESP32 should primarily provide reliable sensor measurements.

---

# 7. HARDWARE TELEMETRY CONTRACT

Design a versioned JSON contract.

Example conceptual payload:

```json
{
  "device_id": "weight-platform-01",
  "sensor": "hx711",
  "weight_g": 320.4,
  "timestamp": "2026-08-12T10:30:15.123Z",
  "sequence": 1842
}
```

The exact schema should be finalized after repository inspection.

Requirements:

- device ID
- timestamp
- sequence number
- measured weight
- sensor/source
- optional calibration/status information
- protocol version

The backend must validate every incoming payload.

Malformed or impossible values must be rejected safely.

---

# 8. DO NOT TRUST A SINGLE WEIGHT READING

The backend must NOT calculate removal weight from two arbitrary sensor readings.

Implement a weight stabilization layer.

Conceptually:

```text
raw readings
     ↓
noise filtering
     ↓
stability detection
     ↓
stable baseline
```

The system should determine when the platform has settled.

Research and choose an appropriate approach such as:

- moving average
- median filtering
- rolling window
- stability threshold
- minimum stable duration
- outlier rejection

Do NOT blindly hard-code thresholds without explaining why.

All thresholds should be configurable.

---

# 9. MEASUREMENT STATE MACHINE

Design an explicit state machine.

At minimum investigate these states:

```text
IDLE
  ↓
TARING
  ↓
WAITING_FOR_INITIAL_LOAD
  ↓
INITIAL_WEIGHT_STABILIZING
  ↓
MEASUREMENT_ACTIVE
  ↓
REMOVAL_DETECTED
  ↓
WEIGHT_STABILIZING
  ↓
REMOVAL_COMMITTED
  ↓
MEASUREMENT_ACTIVE
  ↓
COMPLETE
```

Also support error states such as:

```text
SENSOR_ERROR
CV_UNCERTAIN
WEIGHT_UNSTABLE
INVALID_DELTA
DEVICE_DISCONNECTED
SESSION_TIMEOUT
```

The state machine is extremely important.

Do NOT implement the application as a collection of unrelated `if` statements.

---

# 10. CORE REMOVAL ALGORITHM

The central calculation is:

```text
removed_weight =
    stable_weight_before
    -
    stable_weight_after
```

Example:

```text
before = 320.4 g
after  = 241.7 g

removed = 78.7 g
```

The backend then needs CV to tell it:

```text
removed_ingredient = tomato
```

Therefore:

```text
ingredient = tomato
weight = 78.7 g
```

This becomes an immutable measurement event.

---

# 11. CV CONTRACT

The CV subsystem must not directly manipulate nutrition or database logic.

CV should expose structured observations.

Conceptually:

```json
{
  "frame_id": 18482,
  "timestamp": "...",
  "detections": [
    {
      "track_id": 4,
      "class": "tomato",
      "confidence": 0.94,
      "bbox": [x1, y1, x2, y2],
      "zone": "Z1"
    }
  ]
}
```

The final schema must be determined after inspecting the existing CV implementation.

The CV subsystem should provide:

- detected objects
- confidence
- bounding boxes
- track IDs where possible
- timestamps/frame IDs
- zone information
- detection lifecycle

The backend/session engine decides whether an object has actually disappeared.

---

# 12. AUTOMATIC BEFORE/AFTER CV COMPARISON

The final system must NOT simply compare two random frames.

Design a robust temporal detection system:

```text
BEFORE
  ↓
Stable ingredient set
  ↓
User removes ingredient
  ↓
TEMPORARY MOTION / TRANSITION
  ↓
WAIT
  ↓
AFTER
  ↓
Stable ingredient set
```

Then compute:

```text
before_objects - after_objects
```

The result is the candidate removed ingredient.

Example:

```text
BEFORE:
{tomato, onion, cucumber}

AFTER:
{tomato, onion}

DIFFERENCE:
{cucumber}
```

If multiple objects disappear simultaneously, the system must NOT pretend it knows which one was removed.

Instead:

```text
CV_UNCERTAIN
```

and request another stable observation through the normal system flow.

There must be no silent false assignment.

---

# 13. STATIC CAMERA / ZONE ARCHITECTURE

The final hardware will use a static ESP32-CAM.

Therefore investigate and design the CV system around:

- fixed camera position
- fixed board geometry
- predefined regions/zones
- controlled lighting
- stable background
- perspective calibration
- object tracking
- temporal consistency

This is preferable to designing a completely unconstrained general-purpose food detector.

The system should exploit the controlled environment to improve reliability.

Do not unnecessarily solve a harder computer-vision problem than the hardware requires.

---

# 14. CV AND WEIGHT MUST BE SYNCHRONIZED

The most important system-level problem is synchronization.

Do NOT simply process:

```text
CV result
+
latest weight
```

independently.

Design an event timeline:

```text
t0:
CV stable
Weight = 320.4 g

t1:
Object motion detected

t2:
CV transition

t3:
CV stable again
Weight = 241.7 g

t4:
Removal event committed
```

The backend should associate the correct before/after stable weight window with the corresponding CV change.

This is the core sensor-fusion problem.

---

# 15. NUTRITION ENGINE

Design nutrition as an independent backend service/module.

Input:

```text
ingredient
+
measured mass
+
food state
+
nutrient reference
```

Output:

```text
calories
protein
carbohydrates
fat
fiber
and other supported nutrients
```

Core calculation:

```text
nutrient_amount =
    nutrient_per_100g
    ×
    measured_weight_g / 100
```

Example:

```text
Tomato = 78.7 g

Calories =
tomato_kcal_per_100g × 78.7 / 100
```

Do NOT invent nutrition values.

---

# 16. NUTRIENT DATA SOURCE

Research and document the best authoritative source strategy.

Investigate:

1. ICMR-NIN Indian Food Composition Tables
2. USDA FoodData Central
3. Other authoritative sources only when necessary

The system must store provenance:

```text
ingredient
source
food/reference ID
raw/cooked state
nutrient values
unit
source version
date imported
```

Do NOT scrape or redistribute copyrighted food-composition data blindly.

If IFCT 2017 is used, investigate the publication's electronic-use restrictions before storing its data inside the software.

USDA FoodData Central provides an official REST API and detailed food/nutrient documentation, so it can be used as an additional authoritative source where appropriate.

---

# 17. RAW VS COOKED STATE

Nutrition calculation must explicitly distinguish:

```text
raw
cooked
boiled
fried
etc.
```

Do not mix values.

For the first NutriSense prototype, define a controlled scope such as:

```text
RAW INGREDIENTS ONLY
```

unless the existing project requirements explicitly require otherwise.

Document this limitation.

---

# 18. DATABASE DESIGN

Use SQLite initially.

Design normalized tables/entities for at least:

```text
devices
measurement_sessions
weight_readings
cv_observations
ingredient_observations
removal_events
ingredient_measurements
nutrient_references
nutrition_results
system_events
```

Do not store everything as one giant JSON blob.

Use relational tables for important measurements.

Store raw payloads additionally where useful for debugging.

Every measurement should be traceable.

Example:

```text
Session
  ↓
Removal Event #1
  ↓
CV observation before
CV observation after
  ↓
Weight before
Weight after
  ↓
Calculated delta
  ↓
Ingredient assignment
  ↓
Nutrition calculation
```

---

# 19. AUDITABILITY

Every final nutrition result should be explainable.

If the system says:

```text
Tomato = 78.7 g
Calories = X
Protein = Y
```

we must be able to trace:

```text
Which session?
Which CV observation?
Which before weight?
Which after weight?
Which delta?
Which nutrient reference?
Which formula?
Which source/version?
```

This is essential for a serious engineering project.

---

# 20. API DESIGN

Design a versioned API.

Conceptually:

```text
/api/v1/hardware/weight
/api/v1/hardware/heartbeat
/api/v1/sessions
/api/v1/sessions/{session_id}
/api/v1/cv/observations
/api/v1/removals
/api/v1/nutrition/{session_id}
/api/v1/system/status
```

Do NOT blindly use these exact routes.

First inspect the existing project and integrate with existing APIs where possible.

Create `API_CONTRACT.md` containing:

- endpoint
- method
- request schema
- response schema
- validation
- error codes
- authentication/device identity strategy
- example payload
- frontend usage

---

# 21. FRONTEND COMMUNICATION

The frontend should NOT repeatedly poll the backend if real-time updates are needed.

Use:

```text
FastAPI
   ↓
WebSocket
   ↓
Frontend
```

for live:

- weight
- CV detections
- session state
- removal events
- nutrition updates
- hardware status

REST APIs remain useful for commands and retrieving historical/session data.

FastAPI officially supports WebSockets for persistent bidirectional communication with frontend clients.

---

# 22. HARDWARE DISCONNECTION

Design for reality.

The system must handle:

```text
ESP32 connected
ESP32 disconnected
Wi-Fi lost
ESP32 reconnects
duplicate packet
out-of-order packet
stale timestamp
invalid weight
sensor fault
backend unavailable
```

The ESP32 should have:

- reconnect logic
- timeout
- sequence number
- heartbeat
- safe retry strategy

The backend should detect stale devices.

Do not assume the network is always perfect.

---

# 23. HARDWARE ADAPTER / SIMULATION MODE

Before physical hardware is connected, implement a simulator.

Example:

```text
MockWeightDevice
```

which can generate:

```text
320.4
319.9
320.2
320.3
320.4
241.7
241.5
241.8
```

This lets us test the entire backend without waiting for hardware fabrication.

Also create mock CV observations:

```text
BEFORE:
tomato
onion
cucumber

AFTER:
tomato
onion
```

Expected:

```text
removed = cucumber
```

This is mandatory.

---

# 24. TESTING STRATEGY

Create automated tests for:

### Weight

- stable readings
- noisy readings
- tare
- positive delta
- tiny delta
- invalid negative delta
- duplicate readings
- sensor disconnect

### CV

- one ingredient disappears
- multiple disappear
- false detection
- temporary occlusion
- confidence drops
- object reappears

### Sensor fusion

Test:

```text
CV says tomato disappeared
Weight decreases 78.7g
→ tomato = 78.7g
```

Also:

```text
CV says tomato disappeared
Weight unchanged
→ do NOT commit
```

And:

```text
CV uncertain
Weight decreases
→ do NOT blindly assign ingredient
```

And:

```text
CV says tomato disappeared
Weight decreases 78.7g
then tomato reappears
→ handle according to state machine
```

---

# 25. PHASED IMPLEMENTATION

Do NOT attempt to build the entire system in one uncontrolled coding operation.

Use these phases.

## PHASE 0 — Repository Audit

No functional changes.

Produce:

```text
SYSTEM_AUDIT.md
```

Explain the existing architecture and identify:

- reusable components
- broken components
- missing components
- integration risks
- current API
- current database
- current CV pipeline
- current frontend pipeline

---

## PHASE 1 — Architecture + Contracts

Create:

```text
SYSTEM_ARCHITECTURE.md
HARDWARE_PROTOCOL.md
BACKEND_ARCHITECTURE.md
MEASUREMENT_STATE_MACHINE.md
CV_INTEGRATION.md
NUTRITION_ENGINE.md
DATABASE_SCHEMA.md
API_CONTRACT.md
FRONTEND_CONTRACT.md
DATA_PROVENANCE.md
TESTING_STRATEGY.md
DEVELOPMENT_ROADMAP.md
DECISIONS.md
```

Do NOT start large implementation until these are internally consistent.

---

## PHASE 2 — Backend Core

Implement:

- SQLite
- models
- migrations/schema management
- sessions
- weight ingestion
- validation
- stabilization
- state machine
- removal calculation
- event logging

Use mock hardware.

---

## PHASE 3 — CV Integration

Integrate the existing V4 model.

Do NOT retrain the CV model yet unless testing proves it is necessary.

Create a clean CV interface so that the model can later be replaced without changing the backend.

---

## PHASE 4 — Sensor Fusion

Implement:

```text
CV before/after
+
weight before/after
=
automatic removal event
```

This is the most important phase.

---

## PHASE 5 — Nutrition Engine

Implement:

```text
ingredient
→ nutrient reference
→ measured grams
→ calculated nutrients
```

with source provenance.

---

## PHASE 6 — ESP32 Integration

Replace mock weight device with real ESP32 telemetry.

Do NOT redesign the backend.

The hardware should simply satisfy the documented API contract.

---

## PHASE 7 — ESP32-CAM Integration

Connect the static camera.

Implement:

- stream
- frame capture
- CV processing
- timestamps
- detection events
- zone configuration

---

## PHASE 8 — Frontend Integration

Connect existing frontend to:

- WebSocket events
- session API
- live weight
- CV detections
- removal events
- nutrition results
- hardware status

Do not rewrite the frontend unnecessarily.

---

## PHASE 9 — Hardware Calibration

Perform:

- load-cell calibration
- tare testing
- repeatability testing
- stability testing
- camera positioning
- lighting setup
- zone calibration

Record all calibration constants.

---

## PHASE 10 — Full-System Validation

Test the actual workflow:

```text
Place all ingredients
↓
Stable total
↓
Remove tomato
↓
Automatic CV identification
↓
Weight delta
↓
Tomato grams
↓
Remove onion
↓
Automatic identification
↓
Weight delta
↓
Onion grams
↓
...
↓
Final nutrition
```

No manual ingredient selection.

---

# 26. CRITICAL DESIGN RULE

Separate these responsibilities:

```text
CV
=
"What ingredient/object is present?"

Load Cell
=
"How much mass changed?"

Session Engine
=
"When did a real removal happen?"

Sensor Fusion
=
"Which ingredient corresponds to that weight change?"

Nutrition Engine
=
"What nutrients correspond to that measured mass?"

Database
=
"What happened and how can we prove it?"

Frontend
=
"How do we display it?"

ESP32
=
"How do we reliably send sensor data?"
```

Do not mix these responsibilities.

---

# 27. NUTRITION ACCURACY WARNING

Do NOT claim that nutrition values are mathematically exact.

The system can make the **mass measurement highly reproducible**, but food composition naturally varies.

Therefore distinguish:

```text
Measured quantity:
high confidence if hardware is calibrated

Nutrient estimate:
based on reference composition × measured mass
```

The UI/reporting language should reflect this.

---

# 28. ENGINEERING PRINCIPLES

Follow these rules throughout the project:

1. Read the architecture documents before coding.
2. Inspect existing code before replacing it.
3. Never invent hardware capabilities.
4. Never invent nutrition values.
5. Never silently assign an ingredient when CV is uncertain.
6. Never calculate ingredient mass from visual appearance.
7. Load-cell measurements are the mass source of truth.
8. CV is the ingredient identity source.
9. Every important event must be timestamped.
10. Every removal must be auditable.
11. Keep hardware, CV, backend, database, nutrition, and frontend modular.
12. Prefer simple local architecture over unnecessary cloud infrastructure.
13. Use configuration files/environment variables for secrets.
14. Never hardcode API keys, Wi-Fi passwords, or credentials.
15. Never expose credentials in source control.
16. Write tests before declaring a subsystem complete.
17. Use simulation before requiring physical hardware.
18. Do not retrain CV merely because an integration bug looks like a model problem.
19. Distinguish model errors from integration errors.
20. Do not perform large refactors without documenting the reason.

---

# 29. IMPORTANT: CURRENT PROJECT CONTEXT

The current NutriSense CV V4 model has already been trained and evaluated.

The existing V4 model achieved strong benchmark performance on the dataset, including approximately:

- mAP@50 ≈ 85.5%
- mAP@50-95 ≈ 62.7%
- Tomato mAP@50 ≈ 99.5%
- Onion mAP@50 ≈ 99.0%
- Cucumber mAP@50 ≈ 98.1%
- Carrot mAP@50 ≈ 87.5%

However, real-world testing has shown that controlled lighting/background/placement significantly affects performance.

Therefore:

**Do not immediately retrain the model.**

First build the system architecture and establish the hardware/software contracts.

Later, once the actual static ESP32-CAM environment exists, collect representative frames/video from that exact environment and evaluate whether domain-specific fine-tuning is required.

---

# 30. FUTURE DATA COLLECTION

The eventual hardware setup should make it possible to collect:

```text
ESP32-CAM video
+
timestamp
+
CV predictions
+
weight telemetry
+
session state
```

The system should be designed so these can later become a synchronized dataset.

This will allow future training data to represent the actual NutriSense environment:

- exact camera
- exact board
- exact lighting
- exact zones
- exact background
- actual ingredient appearance
- actual camera angle

Do not build this dataset collection blindly now.

Design the hooks now, collect the data after the hardware is operational.

---

# 31. FIRST DELIVERABLE

Your first task is NOT to write the whole backend.

Your first task is:

### 1. Audit the repository.

### 2. Research the required architecture.

### 3. Create/update the permanent Markdown architecture documents.

### 4. Produce a concrete implementation roadmap.

### 5. Identify conflicts with the existing code.

### 6. Identify what can be reused.

### 7. Identify what must be changed.

### 8. Identify anything that requires a decision from me.

Only after this should implementation begin.

Do not ask me unnecessary questions that can be answered by inspecting the repository.

Do not make assumptions where repository evidence is available.

When a decision genuinely requires my approval, clearly explain:

```text
DECISION REQUIRED
Option A:
Option B:
Recommendation:
Reason:
```

---

# 32. DEFINITION OF DONE

The backend/hardware architecture is complete only when:

```text
ESP32
  ↓
HTTP telemetry
  ↓
FastAPI
  ↓
validated weight stream
  ↓
stabilization
  ↓
session state machine

ESP32-CAM
  ↓
CV observations
  ↓
before/after comparison
  ↓
removed ingredient

Weight delta
  +
removed ingredient
  ↓
Removal Event
  ↓
Nutrition Engine
  ↓
SQLite
  ↓
WebSocket
  ↓
Frontend
```

can operate as one coherent system.

The final system must be capable of automatically producing:

```text
Ingredient:
Tomato

Measured weight:
78.7 g

Calories:
calculated from documented nutrient source

Protein:
calculated from documented nutrient source

Carbohydrates:
calculated from documented nutrient source

Fat:
calculated from documented nutrient source

Evidence:
CV before/after + weight before/after + nutrient source
```

with no manual ingredient selection.

---

# START NOW

Begin with:

**PHASE 0 — COMPLETE REPOSITORY AUDIT**

Do not start by writing random implementation code.

Inspect the current NutriSense project thoroughly, research only the technical areas required for this architecture, create the permanent Markdown documentation, and then report:

1. Existing architecture
2. Proposed architecture
3. Existing components that can be reused
4. Components that need modification
5. Missing components
6. Database recommendation
7. Hardware communication recommendation
8. CV/backend integration recommendation
9. Nutrition-data strategy
10. State-machine design
11. API contract proposal
12. Testing strategy
13. Exact implementation order
14. Risks and failure modes
15. Any decisions requiring human approval

After the audit, wait for the implementation phase rather than making uncontrolled changes.