# lotus-core Architecture Rules

Status: Progressive enforcement rule set on 2026-06-02.

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
2. `.importlinter` enforces selected high-value import boundaries through
   `make quality-import-boundary-gate`.
3. `make architecture-guard` also enforces selected direct-import boundaries for
   query-control-plane router repository bypass, query runtime router control-plane imports, and
   ingestion router cross-service imports.
4. Future slices should add focused import contracts as ownership boundaries stabilize.
