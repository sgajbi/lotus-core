# FX Slice 7 - Query and Observability Completion

## Scope
This slice extends existing query surfaces so FX lifecycle state can be investigated without introducing dedicated FX-only endpoints.

## Delivered
1. Extended `/portfolios/{portfolio_id}/transactions` filters with:
 - `transaction_type`
 - `component_type`
 - `linked_transaction_group_id`
 - `fx_contract_id`
 - `swap_event_id`
 - `near_leg_group_id`
 - `far_leg_group_id`
2. Query service plumbing updated across router, service, and repository layers.
3. Existing transaction DTOs and instrument DTOs already expose FX metadata, so filtered ledger interrogation is now operational.

## Key Design Decisions
1. Reuse the existing transaction ledger API rather than create dedicated FX endpoints.
2. Keep FX observability centered on canonical identifiers:
 - event
 - group
 - contract
 - swap leg group

## Shared-Doc Conformance Note
Validated against:
1. `10-query-audit-and-observability.md`
2. `12-canonical-modeling-guidelines.md`

## Residuals
1. No dedicated support summary endpoint for FX yet; current direction remains to extend existing surfaces only when justified.

## Exit Evidence
1. `tests/unit/services/query_service/repositories/test_transaction_repository.py`
2. `tests/unit/services/query_service/services/test_transaction_service.py`

