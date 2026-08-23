# NutriSense — Architectural Decisions Record (ADR)

## ADR-001: Use Local SQLite Database
- **Status:** Approved
- **Context:** Low concurrency, local demo execution, serverless requirement.
- **Decision:** Use SQLite `nutrisense.db` with normalized relational tables.

## ADR-002: Automatic Removal Measurement Model
- **Status:** Approved
- **Context:** Automatic removal measurement workflow (Total load -> subtract removals).
- **Decision:** CV handles identity; scale handles mass delta; backend pairs them.
