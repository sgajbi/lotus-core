# CR-1236 Cashflow Transfer Sign Registry Sets

Date: 2026-07-01

## Objective

Continue GitHub issue #474 by removing duplicated transaction-type transfer-signing rule sets from
cashflow calculation.

## Change

- Replaced hard-coded cashflow transfer inflow/outflow transaction sets with registry-derived sets
  based on production-booking lifecycle family and `position_effect`.
- Kept the current `CASH_IN_LIEU` fallback-signing behavior explicit instead of changing cashflow
  semantics in a registry cleanup slice.
- Added tests proving the transfer sign sets match registry-derived semantics and the fallback
  exception remains behaviorally pinned.

## Expected Improvement

Cashflow transfer sign handling now consumes the canonical registry for supported transfer,
corporate-action, and rights transaction types. Future production-booking transaction types with
transfer-signing semantics cannot drift silently from cashflow calculation without failing focused
conformance tests.

## Tests Added

- `tests/unit/libs/portfolio-common/test_transaction_type_registry.py`
  - `test_cashflow_transfer_sign_rule_tables_match_registry_effects`
- `tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py`
  - extended fallback-sign coverage for `CASH_IN_LIEU`

## Validation Evidence

Focused validation:

- `python -m pytest tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py tests/unit/libs/portfolio-common/test_transaction_type_registry.py -q`
  passed locally.

Final validation for this commit is recorded in the issue comment and review ledger.

## Downstream Compatibility

No route paths, DTOs, OpenAPI schemas, database schema, Kafka topics, event payload shapes, or
transaction type names changed. Current cashflow sign behavior is preserved, including quantity
fallback signing for `CASH_IN_LIEU` when a transfer-classified rule reaches this calculator.

## Documentation And Wiki Decision

Updated this architecture record, codebase review ledger, quality scorecard, refactor health
report, and repository context. No repo-local wiki update is required because no operator command,
route navigation, API field, or wiki workflow changed.

## Remaining Follow-Up

- Continue replacing or conformance-guarding local hard-coded transaction-type sets in cost
  sorting, validation, and query layers.
- Add end-to-end transaction-type coverage for representative production and migration-only
  booking paths before closing issue #474.
