# CR-191 Reprocessing Job Support Listing Review

Date: 2026-03-14

## Finding

The support plane exposed durable replay keys and aggregate replay counters, but
not the durable replay jobs that actually queue and drive
`RESET_WATERMARKS` processing.

That left operators unable to inspect queued, stale, retried, or failed replay
jobs without dropping to direct database inspection.

## Change

Added:

- `GET /support/portfolios/{portfolio_id}/reprocessing-jobs`

The new listing:

- reuses the shared `SupportJobRecord` contract
- fences replay jobs to a portfolio through durable replay-key ownership
- exposes:
  - `attempt_count`
  - `is_retrying`
  - `is_stale_processing`
  - `failure_reason`
  - `operational_state`

## Why it improves the system

- keeps support-plane lifecycle language consistent across valuation,
  aggregation, analytics export, and replay
- removes a real operator blind spot on the durable replay queue
- avoids inventing a parallel support model for another job family

## Evidence

- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/services/operations_service.py`
- `src/services/query_control_plane_service/app/routers/operations.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
