# CR-239 - Reconciliation Finding Scope Drill-Through Filters Review

Status: Hardened

## Scope
- reconciliation findings support listing repository, service, and router
- support overview top blocking finding scope to findings drill-through path

## Problem
The support overview already exposed the top blocking finding's:
- `controls_latest_blocking_finding_security_id`
- `controls_latest_blocking_finding_transaction_id`

But the reconciliation findings endpoint still only accepted `finding_id`.

That left the causal scope clues from the overview as dead-end support signals: operators could see which security or transaction was implicated first, yet still could not query the findings list by those same handles.

## Fix
- Added optional `security_id` and `transaction_id` filters to:
  - `OperationsRepository.get_reconciliation_findings_count(...)`
  - `OperationsRepository.get_reconciliation_findings(...)`
  - `OperationsService.get_reconciliation_findings(...)`
  - `GET /support/portfolios/{portfolio_id}/reconciliation-runs/{run_id}/findings`
- Updated OpenAPI assertions so the new filters are explicit and governed
- Strengthened repository SQL tests, service forwarding tests, router dependency tests, and OpenAPI contract tests

## Why This Matters
- top blocking finding scope from the support overview is now directly usable on the findings endpoint
- the control summary and findings surfaces now compose cleanly instead of forcing manual result scanning after the initial drill-through
- this keeps reconciliation support aligned with the same operator drill-through standard now applied to run ids, finding ids, job ids, dates, and lineage handles

## Evidence
- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/services/operations_service.py`
- `src/services/query_control_plane_service/app/routers/operations.py`
- `tests/unit/services/query_service/repositories/test_operations_repository.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
- `python scripts/openapi_quality_gate.py`
- `python -m ruff check src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/services/operations_service.py src/services/query_control_plane_service/app/routers/operations.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
