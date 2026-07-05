# CR-1400 Explicit Service Dependency Factories

## Objective

Fix GitHub issue #551 by making representative broad query/control-plane services expose their
repository and policy dependency graphs through explicit dependency bundles instead of constructing
repositories only inside raw `AsyncSession` constructors.

## Expected Improvement

- CoreSnapshot, Integration, and Operations service dependencies are visible at construction time.
- Focused unit tests can instantiate those services with fake repositories/ports without creating
  an `AsyncSession` or patching repository constructors.
- Query-control-plane dependency providers now call `from_session(...)` factory methods, making
  repository additions visible in factory code review.
- Existing raw-session constructors remain compatible for incremental migration.
- The change improves design modularity inside the existing deployables; no runtime service split is
  justified.

## Scope

- Added `CoreSnapshotDependencies.from_session(...)`.
- Added `IntegrationServiceDependencies.from_session(...)`.
- Added `OperationsServiceDependencies.from_session(...)`.
- Updated query-control-plane dependency providers to construct those dependency bundles.
- Added focused fake-dependency unit tests for the three service families.

## Behavior And Compatibility

No route path, request/response DTO, OpenAPI schema, database schema, repository SQL, page-token
configuration, business logic, or deployment topology changed. Existing `Service(db)` construction
remains supported while new code should prefer explicit dependency bundles/factories.

## Validation Evidence

- `python -m pytest tests\unit\services\query_service\services\test_integration_service.py tests\unit\services\query_service\services\test_operations_service.py tests\unit\services\query_service\services\test_core_snapshot_service.py -q`
  - `210 passed`
- `python -m pytest tests\unit\services\query_control_plane_service\routers\test_integration_router.py -q`
  - `71 passed`
- `python -m pytest tests\integration\services\query_control_plane_service\test_operations_router_dependency.py -k "dependency_factory" -q`
  - `1 passed, 50 deselected`
- `python -m pytest tests\integration\services\query_control_plane_service\test_integration_router_dependency.py -k "factory or dependency" -q`
  - `49 passed`
- Scoped Ruff lint and format checks passed.
- `make typecheck` passed.

Final architecture/docs/lint/diff checks are recorded in the issue comment before commit.

## Documentation And Guidance Decision

- Repo context updated because future broad services should expose repository/port dependencies
  through dependency bundles or use-case ports.
- Codebase review ledger updated with this hardened boundary.
- No wiki update: no operator command, endpoint contract, or runbook truth changed.
- No platform skill update: existing backend delivery guidance already covers explicit dependency
  boundaries and repo-context updates for repeated issue patterns.
