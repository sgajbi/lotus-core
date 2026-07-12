# CR-1313 Infrastructure Adapter Layer

## Scope

Issue cluster: GitHub issue #646.

This slice defines the repo-local infrastructure adapter package contract and migrates one
representative concrete adapter family behind it.

## Objective

Make the concrete side of the port boundary explicit: application code names ports, while concrete
SQLAlchemy, Kafka, downstream-client, cache, storage, and configuration adapters live in a governed
infrastructure layer or transitional packages with a migration path.

## Changes

1. Added `docs/standards/infrastructure-adapter-layer-standard.md`.
2. Moved ingestion workflow store implementations to
   `src/services/ingestion_service/app/infrastructure/workflow_stores.py`.
3. Left `src/services/ingestion_service/app/adapters/ingestion_workflow_stores.py` as a
   compatibility re-export.
4. Updated `IngestionJobService` to import migrated concrete stores from `app.infrastructure`.
5. Added `scripts/infrastructure_adapter_layer_guard.py` and unit tests.
6. Wired `infrastructure-adapter-layer-guard` into `make architecture-guard`.
7. Updated the application port catalog and repo context with the infrastructure adapter boundary.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI metadata, repository SQL, database schema, Kafka
topic, event payload field, ingestion job idempotency behavior, replay-audit behavior, metric name,
runtime composition behavior, or deployment topology changed.

Existing imports from the old adapter module remain compatible through the re-export while governed
application code uses the new infrastructure path.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/scripts/test_infrastructure_adapter_layer_guard.py tests/unit/scripts/test_application_port_catalog_guard.py tests/unit/services/ingestion_service/services/test_ingestion_job_service_ports.py -q`
2. `python scripts/infrastructure_adapter_layer_guard.py`
3. Scoped Ruff lint and format checks for the migrated adapter, guard, and tests.
4. `make architecture-guard`

All listed commands passed locally before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated repo-local standards, architecture catalog docs, codebase review ledger, and repo context.

No wiki update is required because this slice changes internal package governance, not
operator-facing commands, route behavior, supported features, or published wiki truth.

No new platform skill source change is required in this slice because the existing backend delivery
guidance already directs repeated coupling issues toward ports, adapters, guards, and context.

## Remaining Work

GitHub issue #646 is locally fixed for representative infrastructure-layer acceptance pending PR
CI/QA and issue closure.

Existing `repositories`, `consumers`, `producers`, and `adapters` packages across other services
remain transitional migration scope.
