# CR-219 - Replay Job Support Type Fence Review

Status: Hardened

## Scope
- `OperationsRepository.get_reprocessing_jobs_count(...)`
- `OperationsRepository.get_reprocessing_jobs(...)`
- replay job support-plane contract

## Problem
The replay job support DTO and operator semantics only model `RESET_WATERMARKS`, but the repository query did not explicitly constrain `job_type`.

That meant any future replay job type with a compatible payload shape could leak into a support endpoint whose schema, descriptions, and operational meaning are specific to `RESET_WATERMARKS`.

## Fix
- Added explicit `ReprocessingJob.job_type == "RESET_WATERMARKS"` fencing to replay job support count and listing queries
- Strengthened repository tests to prove the generated SQL carries the durable job-type fence

## Why This Matters
- support-plane replay job responses now match the contract they advertise
- future replay job types will not silently bleed into an endpoint with narrower semantics and DTO shape
- this keeps support scope explicit instead of relying on informal assumptions about current data

## Evidence
- `src/services/query_service/app/repositories/operations_repository.py`
- `tests/unit/services/query_service/repositories/test_operations_repository.py`
- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
- `python scripts/openapi_quality_gate.py`
- `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
