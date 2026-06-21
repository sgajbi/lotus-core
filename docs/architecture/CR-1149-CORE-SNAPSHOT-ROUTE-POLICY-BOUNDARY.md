# CR-1149 Core Snapshot Route Policy Boundary

Date: 2026-06-22

## Scope

Governed core snapshot route orchestration in
`src/services/query_control_plane_service/app/routers/integration.py`.

## Finding

`create_core_snapshot(...)` mixed requested-section normalization, effective policy lookup,
allowed-section filtering, strict/non-strict dropped-section posture, no-section response posture,
governance metadata construction, service invocation, and service error-to-HTTP mapping in one
C-ranked API route.

Radon reported:

- `create_core_snapshot`: `C (17)`

## Action Taken

Extracted focused helpers for:

- policy section-code normalization,
- governed request construction,
- applied/dropped section resolution,
- strict-mode and empty-section assertion,
- snapshot governance metadata construction,
- core snapshot service response/error mapping.

The route path, request/response contract, strict policy block body, non-strict dropped-section
warning, no-section error, governance metadata fields, and service exception-to-HTTP mapping remain
unchanged.

## Evidence

Focused route proof:

- `python -m pytest tests\unit\services\query_control_plane_service\routers\test_integration_router.py::test_create_core_snapshot_router_function tests\unit\services\query_control_plane_service\routers\test_integration_router.py::test_create_core_snapshot_maps_not_found_to_404 tests\unit\services\query_control_plane_service\routers\test_integration_router.py::test_create_core_snapshot_maps_bad_request_to_400 tests\unit\services\query_control_plane_service\routers\test_integration_router.py::test_create_core_snapshot_maps_conflict_to_409 tests\unit\services\query_control_plane_service\routers\test_integration_router.py::test_create_core_snapshot_maps_unavailable_section_to_422 tests\unit\services\query_control_plane_service\routers\test_integration_router.py::test_create_core_snapshot_maps_policy_block_to_403 tests\unit\services\query_control_plane_service\routers\test_integration_router.py::test_create_core_snapshot_filters_sections_in_non_strict_mode -q`
- Result: `7 passed`

Focused static proof:

- `python -m ruff check src/services/query_control_plane_service/app/routers/integration.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py`
- Result: passed

Focused format proof:

- `python -m ruff format --check src/services/query_control_plane_service/app/routers/integration.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py`
- Result: passed

Focused complexity proof:

- `python -m radon cc src/services/query_control_plane_service/app/routers/integration.py -s --exclude "*/build/*" | Select-String -Pattern " - [C-F] \("`
- Result: no C-or-worse functions reported in `integration.py`

Measured movement:

- `create_core_snapshot`: `C (17)` -> `A (1)`
- `integration.py`: no C-or-worse functions remain

## Residual Risk

This slice does not change the core snapshot data contract, source-data-product metadata,
downstream consumer policy configuration, or CoreSnapshotService behavior. `_policy_applied_snapshot_sections(...)`
is B-ranked and can be revisited separately if policy rules expand.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of policy-governed source-product route behavior,
- separation of governance metadata construction from service invocation,
- focused proof across success, strict block, non-strict drop, and service error mappings.

It does not claim full bank-buyable readiness for `lotus-core`.
