# CR-183 Reconciliation Support Listing Review

## Scope
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/services/operations_service.py`
- `src/services/query_control_plane_service/app/routers/operations.py`
- query-service and query-control-plane unit/integration tests

## Finding

The support plane exposed reconciliation state only through aggregated overview fields. Operators could not inspect the underlying durable reconciliation runs or findings through the same control-plane surface.

There was also an ownership gap during implementation: findings lookup was keyed only by `run_id`, which meant a support-plane request could retrieve findings for a run that did not belong to the requested portfolio. That is a real control-boundary defect for a banking system.

## Fix

Added support-plane listing endpoints:

- `GET /support/portfolios/{portfolio_id}/reconciliation-runs`
- `GET /support/portfolios/{portfolio_id}/reconciliation-runs/{run_id}/findings`

Added dedicated support DTOs for durable reconciliation runs and findings.

Hardened the service boundary so `get_reconciliation_findings(...)` first verifies the reconciliation run belongs to the requested portfolio before returning findings.

Corrected the support-plane findings contract so:

- `total` reflects the durable run-wide finding count, not only the current page length
- findings are ordered by operational severity before type and recency

## Why this matters

- Operators can now inspect blocked control runs without leaving the control plane.
- Durable reconciliation support is aligned with the existing valuation, aggregation, and analytics export support listings.
- Portfolio scoping is now explicit and enforced instead of being inferred from a naked `run_id`.

## Evidence

- Operations DTO/repository/service/router changes
- Query-service unit tests
- Query-control-plane router dependency tests
- Query-control-plane OpenAPI contract tests
