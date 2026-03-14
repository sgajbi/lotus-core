# CR-206 - Support Job Mapping Convergence Review

Status: Hardened

## Scope
- `OperationsService`
- shared `SupportJobRecord` mapping for valuation, aggregation, and durable replay jobs

## Problem
`OperationsService` rebuilt `SupportJobRecord` three different times for valuation jobs, aggregation jobs, and durable replay jobs.

That duplication had become increasingly fragile as the shared support contract grew richer with:
- durable job identity
- correlation lineage
- creation timing
- terminal failure truth
- derived lifecycle state

Each new field increased the risk that one job family would silently drift from the others.

## Fix
- Extracted `_build_support_job_record(...)` in `OperationsService`
- Switched valuation, aggregation, and durable replay listings to reuse the same builder
- Re-ran the support-plane unit, router dependency, and OpenAPI contract pack

## Why This Matters
- the shared support-job contract is now implemented in one place
- future support-plane enrichments are less likely to drift across job families
- this improves maintainability without changing runtime behavior or widening API surface area

## Evidence
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
