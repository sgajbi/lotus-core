# CR-1314 Repository Transaction Boundary

## Scope

Issue cluster: GitHub issue #647.

This slice moves representative simulation transaction completion behind a unit-of-work port and
adds static repository transaction-boundary enforcement.

## Objective

Make transaction ownership explicit: repositories stage persistence changes, while application
write workflows commit, roll back, and refresh through a unit-of-work adapter.

## Changes

1. Added `src/services/query_service/app/ports/unit_of_work.py`.
2. Added `src/services/query_service/app/infrastructure/unit_of_work.py`.
3. Routed `SimulationService` commit, rollback, and refresh behavior through the `UnitOfWork` port.
4. Added fake-unit-of-work tests proving rollback on commit failure and missing-change rejection.
5. Added `docs/standards/repository-transaction-boundary-standard.md`.
6. Added `scripts/repository_transaction_boundary_guard.py` and unit tests.
7. Wired `repository-transaction-boundary-guard` into `make architecture-guard`.
8. Cataloged the representative query-service unit-of-work port.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI metadata, repository SQL, database schema,
simulation session identity, simulation versioning behavior, projected-position behavior, error
mapping, metric name, or deployment topology changed.

Existing default behavior still uses the supplied SQLAlchemy `AsyncSession`; the difference is that
transaction completion now flows through an explicit adapter.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/services/query_service/services/test_simulation_service.py tests/unit/services/query_service/repositories/test_simulation_repository.py tests/unit/scripts/test_repository_transaction_boundary_guard.py tests/unit/scripts/test_application_port_catalog_guard.py -q`
2. `python scripts/repository_transaction_boundary_guard.py`
3. `python scripts/application_port_catalog_guard.py`
4. Scoped Ruff lint and format checks for the changed modules and tests.
5. `make architecture-guard`

All listed commands passed locally before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated repo-local standards, architecture catalog docs, codebase review ledger, and repo context.

No wiki update is required because this slice changes internal transaction-boundary governance, not
operator-facing commands, route behavior, supported features, or published wiki truth.

No new platform skill source change is required in this slice because the existing backend delivery
guidance already directs repeated coupling issues toward ports, adapters, guards, and context.

## Remaining Work

GitHub issue #647 is locally fixed for representative simulation unit-of-work acceptance pending PR
CI/QA and issue closure.

`OperationsRepository` remains a documented transitional exception for direct repository-owned
transaction completion and should be migrated in a future issue slice.
