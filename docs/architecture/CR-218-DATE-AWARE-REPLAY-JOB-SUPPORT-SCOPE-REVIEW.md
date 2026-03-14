# CR-218 - Date-Aware Replay Job Support Scope Review

Status: Hardened

## Scope
- `OperationsRepository.get_reprocessing_jobs_count(...)`
- `OperationsRepository.get_reprocessing_jobs(...)`
- replay job support-plane scope for one portfolio

## Problem
The support-plane replay job listing and count scoped jobs to a portfolio by security membership only. That allowed a portfolio to see durable `RESET_WATERMARKS` jobs for a security even when the portfolio was not actually impacted on the job's `earliest_impacted_date`.

That diverged from the replay worker's own date-aware fanout rule and made the support plane operationally misleading.

## Fix
- Added a date-aware portfolio-scope fence for replay jobs in `OperationsRepository`
- Scoped replay job count and listing queries by the latest current-epoch `PositionHistory` row on or before each job's impacted date
- Required the portfolio's latest position on or before the impacted date to have `quantity > 0`
- Strengthened repository tests to prove the generated SQL uses the impacted-date and current-epoch holding fence

## Why This Matters
- replay job support listings now reflect the same date-aware business impact model as the replay worker
- unaffected portfolios no longer see security-level replay jobs that should not fan out to them
- this removes a real support-plane truth gap on a banking replay surface

## Evidence
- `src/services/query_service/app/repositories/operations_repository.py`
- `tests/unit/services/query_service/repositories/test_operations_repository.py`
- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
- `python scripts/openapi_quality_gate.py`
- `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
