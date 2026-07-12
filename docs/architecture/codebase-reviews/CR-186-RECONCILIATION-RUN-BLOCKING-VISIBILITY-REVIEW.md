# CR-186 - Reconciliation Run Blocking Visibility Review

## Summary

The reconciliation support listing already exposed durable run records, but still forced operators
to interpret `status` manually to determine whether a run blocked publication. That duplicated
control-plane policy logic on the client side and made the support contract weaker than the rest of
the portfolio-day control model.

## Findings

1. `ReconciliationRunRecord` exposed raw `status` but not whether that status was blocking.
2. The control plane already treats `FAILED` and `REQUIRES_REPLAY` as publication-blocking, but the
   support listing did not surface that derived truth directly.
3. This left room for drift between operator tooling and server-side policy interpretation.

## Fix

The support-plane reconciliation run record now includes:

- `is_blocking`

`OperationsService` computes this from the same `_is_controls_blocking(...)` contract already used by
the portfolio support overview.

## Why This Is Better

- Operators can see blocking truth directly in the run listing.
- Client tools do not need to re-encode portfolio-day publication policy.
- The listing and the support overview now speak the same control semantics.

## Evidence

- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
