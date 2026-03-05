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

1. Added `portfolio_common.transaction_domain.portfolio_flow_guardrails`:
 - `PORTFOLIO_FLOW_NO_AUTO_GENERATE_TRANSACTION_TYPES`
 - `is_portfolio_flow_no_auto_generate_transaction_type(...)`
 - `assert_portfolio_flow_cash_entry_mode_allowed(...)`
2. Exported guardrail APIs through `portfolio_common.transaction_domain.__init__`.
3. Enforced guardrail in cost calculator consumer before emission/linkage handling.
4. Enforced guardrail in cashflow calculator consumer before mode-specific processing.
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
