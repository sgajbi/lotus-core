# CR-195 - Support Job Durable Identity and Failure Contract Review

Status: Hardened

## Scope
- `SupportJobRecord`
- valuation, aggregation, and durable replay support listings
- support-plane router and OpenAPI contracts

## Problem
Support job listings exposed lifecycle truth such as `is_retrying` and `is_stale_processing`, but they still omitted two durable operator-facing facts:
- the stable job row identifier
- whether the row was already in a terminal failed state

That left the support-plane contract weaker than analytics export and reconciliation listings, and forced clients to infer or separately look up basic durable identity and terminal failure truth.

## Fix
- Added `job_id` to `SupportJobRecord`
- Added `is_terminal_failure` to `SupportJobRecord`
- Wired valuation, aggregation, and reprocessing support listings to populate both fields from durable state
- Extended unit, router dependency, and OpenAPI contract tests

## Why This Matters
- operators can correlate support rows to durable database state directly
- support clients no longer need to infer terminal failure from raw `status`
- support-plane job listings are now aligned with the richer analytics export and reconciliation contracts

## Evidence
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
