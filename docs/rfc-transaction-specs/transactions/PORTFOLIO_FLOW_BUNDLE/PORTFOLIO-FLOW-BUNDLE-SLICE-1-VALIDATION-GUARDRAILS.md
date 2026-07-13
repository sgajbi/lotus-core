# Portfolio Flow Bundle Slice 1 Validation and Guardrails

## Objective

Introduce shared guardrails for portfolio-level flow bundle transaction types:

1. `FEE`
2. `TAX`
3. `DEPOSIT`
4. `WITHDRAWAL`
5. `TRANSFER_IN`
6. `TRANSFER_OUT`

Primary rule:

- explicit `cash_entry_mode=AUTO_GENERATE` is rejected for these transaction types.

## Implemented Changes

1. Added `portfolio_transaction_processing_service.app.domain.transaction.settlement.cash_entry`:
 - `PORTFOLIO_LEVEL_CASH_FLOW_TRANSACTION_TYPES`
 - `is_portfolio_level_cash_flow(...)`
 - `assert_cash_entry_mode_supported(...)`
2. Exported guardrail APIs through the service-owned transaction domain.
3. Enforced the guardrail in the unified cost-processing stage before emission and linkage.
4. Enforced the guardrail in the unified cashflow-processing stage before mode-specific handling.
5. Added unit tests:
 - transaction-domain guardrail tests
 - cashflow consumer reject-path test for `FEE + AUTO_GENERATE`
 - cost consumer reject-path test for `FEE + AUTO_GENERATE`

## Behavioral Contract (After Slice 1)

1. Explicit `AUTO_GENERATE` on bundle transaction types is non-canonical and rejected.
2. `UPSTREAM_PROVIDED` remains allowed for bundle transaction types.
3. `cash_entry_mode=None` remains accepted (no explicit mode policy override).
4. Runtime consumers now enforce the same rule, so downstream behavior is deterministic.

## Follow-On Work

1. Slice 2: align `cashflow_rules` classification flags (notably `TAX is_portfolio_flow`) and related consumers.
2. Slice 3: harmonize calculator semantics (position/cost/timeseries) to canonical portfolio-flow invariants.
