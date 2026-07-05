# In-Process Modularity Package Standard

Deployable Lotus Core services should express conceptual boundaries inside the service before a
runtime split is considered.

## Recommended Package Layout

Use this package shape for new or migrated deployable service internals:

1. `app/domain/`
   Pure domain policies, value objects, vocabulary, and deterministic business rules. No FastAPI,
   SQLAlchemy sessions, repositories, Kafka, Redis, cloud clients, downstream clients, API DTOs, or
   persistence models.
2. `app/application/`
   Use cases, commands, queries, result models, workflow policies, and application errors. Depends
   on domain and ports. Does not depend on routers, repositories, concrete infrastructure, or API
   DTOs.
3. `app/ports/`
   Protocols and small capability contracts for external effects such as repositories, publishers,
   clocks, ID providers, audit stores, idempotency stores, and downstream clients.
4. `app/adapters/`
   Transitional or compatibility adapters that implement ports while preserving legacy import
   paths. Prefer `app/infrastructure/` for new concrete runtime adapters.
5. `app/infrastructure/`
   Concrete implementations for database sessions, repositories, Kafka/EventHub publishers,
   metrics, clocks, cloud clients, and downstream clients.
6. `app/routers/` or `app/delivery/`
   HTTP delivery adapters. They translate API DTOs, headers, query parameters, and path values into
   application commands/queries and map application results/errors back to HTTP responses.
7. `app/repositories/` or `app/persistence/`
   Persistence adapters and query implementations. They own ORM rows, SQLAlchemy sessions, SQL
   query shape, pagination primitives, locks, and database exceptions.
8. `app/runtime/` or runtime composition files such as `app/dependencies.py`,
   `app/consumer_manager.py`, `app/main.py`, and `app/web.py`
   Runtime assembly, dependency injection, service startup/shutdown, consumer registration, and
   concrete adapter wiring.
9. `app/proof_builders/`
   Optional package for implementation-backed evidence/proof artifact assembly when a service owns
   proof outputs. Proof builders depend on application results and domain values, not raw framework
   request objects.

## DTOs, Domain Objects, And Persistence Models

API DTOs and OpenAPI-facing contracts belong at the delivery boundary, typically in `app/dtos/`,
`app/DTOs/`, or router-local modules during migration. They should not become application or domain
input/output contracts.

Application command/query/result models belong in `app/application/`. They are internal contracts
for use cases and workers.

Domain objects belong in `app/domain/` or shared domain libraries. They should be framework-free
and persistence-free.

Persistence models and ORM rows belong in repository, persistence, or shared database-model
modules. They should not cross into domain/application logic except through typed adapter records
or ports.

## Dependency Direction

Allowed direction:

1. delivery/runtime -> application,
2. application -> domain,
3. application -> ports,
4. infrastructure/adapters/repositories -> ports,
5. infrastructure/adapters/repositories -> persistence models,
6. tests -> fakes implementing ports.

Forbidden direction:

1. domain -> application, ports, routers, repositories, infrastructure, API DTOs, or persistence
   models,
2. application -> routers, repositories, infrastructure, concrete clients, framework request
   objects, or API DTOs,
3. ports -> infrastructure, repositories, concrete clients, framework objects, or runtime globals.

## Migration Guidance

Do not rename existing `services`, `repositories`, `core`, `transformers`, `DTOs`, or `dtos`
folders in broad mechanical churn.

When touching a cohesive workflow:

1. extract pure policy to `domain/` when it is business rule logic,
2. extract orchestration to `application/` when it is a use case or workflow,
3. introduce a narrow port in `ports/` for each required external capability,
4. keep existing concrete repositories or clients as adapters until safe to rename or move,
5. keep API DTO compatibility at routers/delivery,
6. update the adoption catalog and architecture guards when a service adopts the package shape,
7. record a no-runtime-split rationale when the slice improves design modularity only.

## Representative Adoption

`docs/architecture/in-process-modularity-adoption-catalog.json` records services that have adopted
or partially adopted this layout. The first representative adoption is `ingestion_service`, which
has domain, application, ports, adapters, infrastructure, routers, repositories, and runtime
composition files while retaining legacy `DTOs`, `services`, `transformers`, and `producers`
folders as explicit migration scope.

## Enforcement

`make architecture-guard` runs `scripts/in_process_modularity_guard.py`.

The guard validates the adoption catalog, representative package paths, runtime composition files,
legacy-folder classification, and evidence links.
