# Repository Transaction Boundary Standard

Repositories should execute SQL and stage persistence changes. Application command workflows should
own transaction completion through an explicit unit-of-work boundary.

## Required Pattern

1. Repository methods may call `add`, `execute`, `flush`, query builders, and row-mapping helpers.
2. Repository methods must not call `commit()` or `rollback()` unless explicitly registered as a
   transitional standalone infrastructure exception.
3. Application write workflows should use a `UnitOfWork` port or equivalent runtime transaction
   adapter for commit, rollback, and refresh behavior.
4. Multi-step write workflows should have tests proving rollback when the unit of work fails or the
   workflow rejects a mutation.
5. Read-only repositories do not need transaction commits.

## Current Representative Unit Of Work

`SimulationService` uses the query-service `UnitOfWork` port from
`src/services/query_service/app/ports/unit_of_work.py`. The default implementation is
`SqlAlchemyUnitOfWork` in `src/services/query_service/app/infrastructure/unit_of_work.py`.

`SimulationRepository` stages session rows, change rows, status changes, and deletes only. It does
not commit, rollback, generate identifiers, or read clocks.

## Transitional Exceptions

`src/services/query_service/app/repositories/operations_repository.py` remains a transitional
standalone repository transaction exception for operator control-plane status updates. Remove the
exception when those updates move behind an explicit unit-of-work boundary.

## Enforcement

`make architecture-guard` runs `scripts/repository_transaction_boundary_guard.py`. The guard scans
repository modules for direct `commit()` or `rollback()` calls and fails unless the file is listed
as a transitional exception. It also fails stale exceptions after a repository no longer owns direct
transaction completion.

Generated `build/lib` copies are intentionally excluded from this guard while issue #649 tracks
removing or governing tracked generated artifacts.

## Runtime Boundary

This standard changes transaction ownership inside existing deployables. It does not introduce a
new database, service, or runtime deployment topology.
