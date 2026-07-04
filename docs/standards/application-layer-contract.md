# Application Layer Contract

The application layer owns use-case orchestration, command/query handling, workflow coordination,
application error classification, idempotency coordination, audit coordination, and calls to ports.

## Required Responsibilities

Application modules may:

1. accept command/query models and return application result models,
2. coordinate domain policies and value objects,
3. call repository, publisher, audit, idempotency, clock, UUID, downstream-client, or unit-of-work
   ports,
4. classify application errors using framework-independent error taxonomy,
5. coordinate transaction and recovery boundaries through explicit unit-of-work or workflow
   contracts.

Application modules must not:

1. import FastAPI, Starlette, or HTTP framework objects,
2. construct SQLAlchemy sessions or concrete repositories,
3. construct Kafka producers, concrete downstream clients, Redis/cache clients, or file/cloud
   infrastructure,
4. expose API request/response DTOs as use-case contracts,
5. own HTTP status codes, headers, or response envelopes,
6. own persistence schema or ORM model behavior.

## Current Package Convention

Representative application packages live under:

1. `src/services/ingestion_service/app/application/`
2. `src/services/query_service/app/application/`
3. `src/services/event_replay_service/app/application/`
4. `src/services/financial_reconciliation_service/app/application/`

Use `src/services/<service>/app/ports/` for service-local ports and
`src/services/<service>/app/infrastructure/` for concrete adapters when a migrated service already
has those package boundaries. Existing legacy `services`, `repositories`, `adapters`, `producers`,
and `consumers` packages remain transitional migration scope.

## Current Representative Workflows

1. Ingestion upload command/result contracts run without FastAPI or Kafka mocks at the application
   service boundary.
2. Ingestion idempotency and replay-audit workflows run through store ports and fake-port tests.
3. Query lookup catalog read workflows return application results and are mapped to API DTOs in the
   router.
4. Core snapshot request fingerprinting uses a canonical application identity command.
5. Financial reconciliation use cases run behind repository capability ports.

## Enforcement

`make architecture-guard` runs `scripts/application_layer_contract_guard.py`. The guard scans
`app/application` and `app/use_cases` packages and blocks FastAPI/Starlette imports, SQLAlchemy
imports, direct Kafka producer construction, direct repository imports, producer imports, and
consumer infrastructure imports.

## Runtime Boundary

This standard is a design-time modularity contract inside the existing deployables. It does not
approve or require a runtime service split.

