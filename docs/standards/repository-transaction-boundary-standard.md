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

`SimulationService` (`src/services/query_control_plane_service/app/application/simulation.py`) uses
the `SimulationUnitOfWork` port from
`src/services/query_control_plane_service/app/ports/simulation.py`. The implementation is
`src/services/query_control_plane_service/app/infrastructure/simulation_unit_of_work.py`.

The same service carries a second unit-of-work family for analytics —
`…/app/ports/analytics.py` with `…/app/infrastructure/analytics_unit_of_work.py` — which is why
these adapters are named per family rather than as a single `unit_of_work.py`.

`SimulationRepository` stages session rows, change rows, status changes, and deletes only. It does
not commit, rollback, generate identifiers, or read clocks.

## Transitional Exceptions

`src/services/query_control_plane_service/app/infrastructure/operations/repository.py` remains a
transitional
standalone repository transaction exception for operator control-plane status updates. Remove the
exception when those updates move behind an explicit unit-of-work boundary.

## Enforcement

`make architecture-guard` runs `scripts/quality/repository_transaction_boundary_guard.py`. The guard
scans legacy repository modules and repository adapters under `app/infrastructure/` for direct
`commit()` or `rollback()` calls and fails unless the file is listed as a transitional exception. It
also fails stale exceptions after a repository no longer owns direct transaction completion.

Generated `build/lib` copies are intentionally excluded from this guard as disposable local build
artifacts. They are not authored source truth and should remain untracked under the generated
artifact cleanup policy.

## Runtime Boundary

This standard changes transaction ownership inside existing deployables. It does not introduce a
new database, service, or runtime deployment topology.
