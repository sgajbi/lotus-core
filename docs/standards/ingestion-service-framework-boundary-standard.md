# Ingestion Service Framework Boundary Standard

Ingestion business services and adapter-mode policy must stay independent of the HTTP framework.

## Rule

Modules under `src/services/ingestion_service/app/services/` and
`src/services/ingestion_service/app/adapter_mode.py` must not:

1. import FastAPI,
2. declare `Depends(...)` providers,
3. raise `HTTPException`,
4. own HTTP status-code mapping.

FastAPI dependency providers, HTTP exception mapping, and API-edge policy translation belong in
`src/services/ingestion_service/app/dependencies.py` or the router that owns the API contract.

## Rationale

Keeping framework wiring out of ingestion services makes use cases directly constructable with fake
publishers, fake stores, and fake sessions. It also prevents HTTP concerns from leaking into worker,
batch, replay, or test execution paths that reuse the same business services.

## Current Pattern

1. `adapter_mode.py` raises `AdapterModeDisabledError` with stable machine-readable detail.
2. `dependencies.py` translates that error to HTTP `410 Gone` for router dependencies.
3. `dependencies.py` owns `get_ingestion_service(...)` and
   `get_reference_data_ingestion_service(...)`.
4. Routers keep using `Depends(...)`, but import providers from `dependencies.py`.

## Enforcement

`make architecture-guard` runs `scripts/ingestion_service_framework_guard.py`. The guard scans the
ingestion service modules and adapter-mode policy for FastAPI imports, `Depends(...)`,
`HTTPException`, and `status.HTTP` usage.

## Compatibility

This standard is a design-time modularity rule. It does not change route paths, request DTOs,
response DTOs, OpenAPI metadata, Kafka topics, database schema, or runtime topology.
