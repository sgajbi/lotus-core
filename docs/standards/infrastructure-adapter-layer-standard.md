# Infrastructure Adapter Layer Standard

Concrete infrastructure adapters must live behind explicit package boundaries and implement ports
owned by application or shared capability layers.

## Package Convention

Service-local concrete infrastructure should use these package families:

1. `app/infrastructure/repositories` for SQLAlchemy repositories and query adapters,
2. `app/infrastructure/events` for Kafka/EventHub producers and consumers,
3. `app/infrastructure/clients` for downstream HTTP or service clients,
4. `app/infrastructure/cache` for Redis/cache adapters,
5. `app/infrastructure/storage` for file or object-storage adapters,
6. `app/infrastructure/workflow_stores.py` or a narrower module when one service has a small
   adapter family that does not justify a subpackage yet.
7. `app/infrastructure/unit_of_work.py` for SQLAlchemy transaction adapters.

`app/runtime` or dependency/composition modules may wire concrete infrastructure adapters into
application services. API routers, domain modules, and port modules should not construct concrete
infrastructure adapters.

## Transitional Packages

Existing `app/repositories`, `app/consumers`, `app/producers`, and `app/adapters` packages are
classified as transitional unless a service-specific standard says otherwise. They may remain until
their owners migrate them safely behind `app/infrastructure` or an approved shared library.

When a module is migrated, the old package may temporarily re-export the new implementation to
preserve imports while callers are updated. Compatibility modules must not retain duplicated class
definitions or concrete helper wiring.

## Import And Export Rules

1. Infrastructure adapters may import concrete database, Kafka, cache, storage, configuration, and
   downstream-client libraries.
2. Infrastructure adapters should implement application/shared ports and translate concrete
   failures into typed infrastructure errors when failure behavior crosses the application boundary.
3. Infrastructure adapters should expose concrete adapter classes or provider functions, not API
   DTOs, FastAPI dependencies, routers, or domain policies.
4. Application services should depend on ports for business behavior and use runtime composition for
   concrete infrastructure wiring as each workflow is migrated.
5. Domain modules must not import infrastructure modules.

## Current Protected Scope

`IngestionJobStore` and `ReplayAuditStore` SQLAlchemy implementations now live in
`src/services/ingestion_service/app/infrastructure/workflow_stores.py`. The previous
`app/adapters/ingestion_workflow_stores.py` module is a transitional compatibility re-export only.

`SimulationService` uses `src/services/query_service/app/infrastructure/unit_of_work.py` as the
representative SQLAlchemy unit-of-work adapter.

`make architecture-guard` runs `scripts/infrastructure_adapter_layer_guard.py` to keep this
representative migration from drifting back into the transitional package.

## Runtime Boundary

This standard is an in-process package boundary. It does not create a new deployable service,
database, queue, cache, storage account, or ownership boundary.
