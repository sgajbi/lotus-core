# CR-196 - Support Job Correlation Lineage Visibility Review

Status: Hardened

## Scope
- `SupportJobRecord`
- valuation, aggregation, and durable replay support listings
- support-plane router and OpenAPI contracts

## Problem
The durable job tables already persisted `correlation_id`, and earlier review slices had normalized that lineage at persistence boundaries. But the support-plane job listings still hid it.

That left operators in an awkward spot:
- the support API could show that a job was stale or failed
- the durable row knew its correlation lineage
- but the support contract still forced operators to pivot into logs or direct database inspection to join triage back to the originating request or replay chain

## Fix
- Added `correlation_id` to `SupportJobRecord`
- Wired valuation, aggregation, and durable replay support listings to surface the stored durable correlation id
- Extended the reprocessing job support query to select durable replay correlation lineage explicitly
- Strengthened unit, router dependency, and OpenAPI contract tests

## Why This Matters
- support triage can now bridge directly from a durable job row to logs, events, and replay lineage
- the shared support job contract is now closer to the real durable truth already present in the database
- this keeps correlation visibility reusable across valuation, aggregation, and replay instead of creating another one-off support endpoint

## Evidence
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
