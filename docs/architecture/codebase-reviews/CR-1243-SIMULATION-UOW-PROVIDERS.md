# CR-1243 Simulation Unit Of Work And Providers

Date: 2026-07-01

## Objective

Fix GitHub issue #667 by moving simulation session transaction ownership, UUID generation, clock
selection, and version mutation out of the repository adapter and into the application service.

## Change

- Changed `SimulationRepository` to stage session rows, change rows, status updates, and deletes
  without calling `commit()`, `rollback()`, `refresh()`, `uuid4()`, or `datetime.now(...)`.
- Added injectable clock and ID providers to `SimulationService`.
- Moved session ID generation, change ID generation, expiry calculation, version increments,
  commit/refresh, and rollback-on-missing-delete behavior into the simulation use case.
- Updated repository tests to prove staging behavior and service tests to prove deterministic
  providers plus application-owned unit-of-work behavior.

## Expected Improvement

Simulation workflows now have one application-level transaction boundary per mutation. Future audit,
idempotency, replay, or lifecycle evidence can be composed around the complete use case without
fighting repository-owned commits, and tests can use deterministic clocks and IDs without patching
infrastructure internals.

## Tests Added Or Updated

- `tests/unit/services/query_service/repositories/test_simulation_repository.py`
- `tests/unit/services/query_service/services/test_simulation_service.py`
- `tests/integration/services/query_control_plane_service/test_simulation_router_dependency.py`

## Validation Evidence

- `python -m pytest tests/unit/services/query_service/repositories/test_simulation_repository.py tests/unit/services/query_service/services/test_simulation_service.py tests/integration/services/query_control_plane_service/test_simulation_router_dependency.py -q --tb=short`
  - `57 passed`
- `python -m ruff check src/services/query_service/app/repositories/simulation_repository.py src/services/query_service/app/services/simulation_service.py tests/unit/services/query_service/repositories/test_simulation_repository.py tests/unit/services/query_service/services/test_simulation_service.py tests/integration/services/query_control_plane_service/test_simulation_router_dependency.py`
  - `All checks passed!`
- `python -m ruff format --check src/services/query_service/app/repositories/simulation_repository.py src/services/query_service/app/services/simulation_service.py tests/unit/services/query_service/repositories/test_simulation_repository.py tests/unit/services/query_service/services/test_simulation_service.py tests/integration/services/query_control_plane_service/test_simulation_router_dependency.py`
  - `5 files already formatted`
- `python -m mypy --config-file mypy.ini src/services/query_service/app/repositories/simulation_repository.py src/services/query_service/app/services/simulation_service.py`
  - `Success: no issues found in 2 source files`

## Downstream Compatibility

Simulation route paths, request DTOs, success DTOs, HTTP statuses, problem-details contracts,
OpenAPI contracts, database schema, table names, persistence columns, Kafka topics, and projected
position semantics are preserved. The internal ownership change preserves successful mutation
behavior while changing where the commit, refresh, rollback, version increment, clock, and ID
selection happen. No client-supplied expected-version or optimistic-concurrency conflict contract
exists on the current simulation mutation DTOs, so this slice preserves the existing monotonic
output-version behavior rather than adding a new conflict API.

## Documentation And Wiki Decision

Updated this architecture record, the codebase review ledger, quality scorecard, refactor health
report, and repository engineering context. No repo-local wiki update is required because no
operator command, route navigation, API field, or wiki workflow changed.

## Remaining Follow-Up

- Apply the same repository-staging/use-case-transaction pattern when future simulation audit,
  idempotency, or lifecycle evidence is added.
- Keep deterministic providers at the application-service boundary rather than patching repository
  internals in tests.
