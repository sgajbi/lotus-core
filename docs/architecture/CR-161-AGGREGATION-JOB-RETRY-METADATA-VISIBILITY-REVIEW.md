# CR-161 Aggregation Job Retry Metadata Visibility Review

## Scope

- Query/control-plane support API visibility for durable aggregation jobs
- End-to-end visibility of the new aggregation retry model

## Finding

CR-160 added durable `attempt_count` and `failure_reason` to
`portfolio_aggregation_jobs`, but the control-plane support API still mapped
aggregation jobs as if those fields did not exist. That hid active retry and
terminal-failure context from operators even though the queue model had already
been hardened.

## Fix

- Updated `OperationsService.get_aggregation_jobs(...)` to expose:
  - `attempt_count`
  - `failure_reason`
- Updated unit and control-plane integration contract tests to prove the fields
  are present on the support API response.

## Evidence

- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`

## Validation

- operations service + control-plane router dependency slice:
  - `29 passed`
- `ruff check`:
  - passed

## Follow-up

- If operators need aggregation retry/failure pressure on the dashboard,
  surface these fields or derived counters through a dedicated support or
  observability panel rather than leaving them visible only in row-level job
  listings.
