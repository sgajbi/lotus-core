# CR-188 - Derived Support State Contract Review

Date: 2026-03-13

## Problem

The support plane had already gained row-level timestamps, stale flags, blocking flags, and better ordering, but clients still had to reconstruct operational meaning from combinations of raw fields:

- valuation and aggregation jobs needed `status + attempt_count + updated_at`
- analytics export jobs needed `status + updated_at + created_at`
- reconciliation runs needed `status + blocking policy knowledge`

That leaves client code duplicating server-side policy.

## Change

Extended support-plane row contracts with explicit derived operational state:

- `SupportJobRecord`
  - `is_retrying`
  - `operational_state`
- `AnalyticsExportJobRecord`
  - `is_terminal_failure`
  - `operational_state`
- `ReconciliationRunRecord`
  - `is_terminal_failure`
  - `operational_state`

The derivation now lives centrally in `OperationsService`.

## Why this is better

- Clients can render or alert on support rows without re-implementing server policy.
- Support listing ordering and support row semantics now speak the same language.
- Operational state remains test-backed and OpenAPI-visible.

## Evidence

- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
