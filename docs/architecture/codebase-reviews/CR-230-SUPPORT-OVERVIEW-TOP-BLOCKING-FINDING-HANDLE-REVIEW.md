# CR-230 - Support Overview Top Blocking Finding Handle Review

Status: Hardened

## Scope
- `ReconciliationFindingSummary`
- `SupportOverviewResponse`
- `OperationsService.get_support_overview(...)`
- linked reconciliation-run top blocking finding context on the support overview

## Problem
After CR-229, the support overview could tell operators whether the linked reconciliation run had blocking findings, but it still hid the concrete blocking finding handle behind those counts.

That meant operators still had to pivot into the findings endpoint to learn the first blocking clue:
- which finding
- what type of finding
- which security or transaction it implicated

## Fix
- Extended `ReconciliationFindingSummary` with top blocking finding context:
  - `top_blocking_finding_id`
  - `top_blocking_finding_type`
  - `top_blocking_finding_security_id`
  - `top_blocking_finding_transaction_id`
- Extended `get_reconciliation_finding_summary(run_id)` to project the most recent blocking finding
- Surfaced through `SupportOverviewResponse`:
  - `controls_latest_blocking_finding_id`
  - `controls_latest_blocking_finding_type`
  - `controls_latest_blocking_finding_security_id`
  - `controls_latest_blocking_finding_transaction_id`
- Strengthened repository, service, router dependency, and OpenAPI tests to prove the widened overview contract

## Why This Matters
- the support overview now exposes the first blocking evidence, not just blocking-finding counts
- operators can decide whether they need a deeper findings drill-down without a blind extra call
- the overview is closer to one-step triage for financial reconciliation control failures

## Evidence
- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/repositories/test_operations_repository.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
- `python scripts/openapi_quality_gate.py`
- `python -m ruff check src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/dtos/operations_dto.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
