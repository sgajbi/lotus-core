# lotus-core Architecture Rules

Status: Initial report-only rule set on 2026-06-02.

## Layering Rules

1. Routers call application services or use-case functions only.
2. Routers must not call repositories, database clients, HTTP clients, Kafka, Redis, or downstream
   adapters directly.
3. Middleware stays thin and free of business logic.
4. Domain and application logic must not depend on FastAPI request/response objects.
5. Infrastructure access sits behind repositories, ports, adapters, or shared platform helpers.
6. DTOs and persistence models must not become uncontrolled domain logic surfaces.
7. Downstream errors map to consistent platform errors.

## Initial Enforcement

1. Existing `make architecture-guard` remains authoritative where present.
2. `.importlinter` starts report-only checks for selected high-value boundaries.
3. Future slices should add focused import contracts as ownership boundaries stabilize.
