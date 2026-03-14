# CR-259 Reconciliation List Snapshot Review

## Summary

The reconciliation-run and reconciliation-finding support listings were still live count plus live
row queries even though they are operator-facing control surfaces used alongside newer
snapshot-based support responses. That left them out of step with the surrounding support-plane
contract and made their effective snapshot time ambiguous during active control churn.

## Finding

- Class: support-plane correctness risk
- Consequence: one response could report a reconciliation run or finding set that changed after
  the moment the caller believed they were observing, while adjacent support responses already
  exposed explicit `generated_at_utc` snapshot semantics.

## Action Taken

- added `generated_at_utc` to:
  - `ReconciliationRunListResponse`
  - `ReconciliationFindingListResponse`
- added optional `as_of` fences to:
  - `get_reconciliation_runs_count(...)`
  - `get_reconciliation_runs(...)`
  - `get_reconciliation_findings_count(...)`
  - `get_reconciliation_findings(...)`
- fenced reconciliation runs by `FinancialReconciliationRun.updated_at <= as_of`
- fenced reconciliation findings by `FinancialReconciliationFinding.created_at <= as_of`
- updated `OperationsService` to capture one `generated_at_utc` per reconciliation list response
  and pass it into both the count and row queries
- strengthened repository, service, router dependency, and OpenAPI tests

## Evidence

- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
  - `153 passed`
- `python -m ruff check src/services/query_service/app/dtos/operations_dto.py src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
  - passed

## Follow-up

- keep snapshot timestamps coupled to real repository fences rather than decorative response fields
- continue checking remaining support/detail surfaces for any list or count path that still reads
  live data while adjacent contract layers already imply snapshot semantics
