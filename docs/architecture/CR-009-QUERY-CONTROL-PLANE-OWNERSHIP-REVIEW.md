# CR-009 Query / Control-Plane Ownership Review

## Scope

Review whether the `query_service` / `query_control_plane_service` split introduced by RFC 81
is reflected cleanly in source ownership, tests, and documentation.

Reviewed areas:

- `src/services/query_service/app/main.py`
- `src/services/query_control_plane_service/app/main.py`
- router ownership under `src/services/query_service/app/routers/`
- related integration tests under `tests/integration/services/query_service/`
- architecture documentation and service-boundary notes

## Findings

### 1. Runtime boundary is correct, but source ownership is still blurred

The API surface split is real:

- `query_service` exposes core read-plane endpoints only
- `query_control_plane_service` exposes support, integration, capabilities, analytics-input,
  and simulation endpoints

However, `query_control_plane_service` still imports its routers and enterprise-readiness
middleware directly from the `query_service` package:

- `src/services/query_control_plane_service/app/main.py`
  imports:
  - `src.services.query_service.app.enterprise_readiness`
  - `src.services.query_service.app.routers.analytics_inputs`
  - `src.services.query_service.app.routers.capabilities`
  - `src.services.query_service.app.routers.integration`
  - `src.services.query_service.app.routers.operations`
  - `src.services.query_service.app.routers.simulation`

Implication:

- runtime ownership is separated
- source ownership is not yet separated

This is acceptable in the short term, but it is not a clean long-term microservice boundary.

### 2. Test ownership still reflects the old package shape

Several control-plane route dependency tests still live under:

- `tests/integration/services/query_service/`

even though they exercise `query_control_plane_service.app.main`.

Examples:

- `test_analytics_inputs_router_dependency.py`
- `test_capabilities_router_dependency.py`
- `test_operations_router_dependency.py`
- `test_simulation_router_dependency.py`

This is not functionally wrong, but it weakens service-level ownership clarity.

### 3. There is no immediate correctness defect from this overlap

Current app-contract tests already prove:

- `query_service` excludes control-plane endpoints
- `query_control_plane_service` excludes core read-plane endpoints

So this is not a runtime contract failure.

The real issue is maintainability:

- router code remains physically anchored to `query_service`
- service decomposition can drift because code ownership is not explicit
- future refactors may accidentally re-couple the services

## Recommendation

Treat this as a staged convergence item, not an emergency rewrite.

Recommended order:

1. extract shared non-router cross-cutting utilities from `query_service` into a shared package
   if they truly belong to both services
2. move control-plane routers into `query_control_plane_service/app/routers/`
3. move control-plane integration tests into `tests/integration/services/query_control_plane_service/`
4. keep app-contract tests proving exclusion on both sides

Do **not** re-merge the services. The runtime split remains correct.

## Action taken

No source move was applied in this review batch.

Reason:

- this is a structural ownership cleanup, not a correctness hotfix
- moving router modules and tests is a larger refactor that should be done intentionally,
  not mixed into unrelated hardening slices

The review has been logged so the cleanup can be taken as a dedicated convergence task.

## Sign-off state

Current state: `Refactor Needed`

Reason:

- boundary is correct at API/runtime layer
- ownership is not yet correct at source-tree layer
