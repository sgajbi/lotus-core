# CR-1241 E2E Transaction Coverage Registry Sets

Date: 2026-07-01

## Objective

Continue GitHub issue #474 by removing duplicated transaction-type rule sets from the e2e
transaction-type coverage support helper.

## Change

- Derived e2e supported transaction coverage from production-booking registry types plus the
  migration-only `OTHER` type used to prove no-cashflow-rule behavior.
- Derived transfer inflow/outflow sign sets from registry lifecycle and `position_effect`
  semantics while preserving the current `CASH_IN_LIEU` fallback-signing exception and
  `RIGHTS_REFUND` inflow special case.
- Derived cash-instrument test routing from registry `cash_movement` and `expense` lifecycle
  families.
- Derived no-cashflow-rule coverage from registry non-production and linked-FX-cash-leg semantics.
- Added dry-run e2e coverage assertions proving the helper sets match registry semantics.

## Expected Improvement

The e2e transaction coverage matrix now evolves with the canonical transaction registry instead of
copying local transfer and cashflow exception sets. CI coverage is less likely to silently omit new
production-booking transaction types or keep stale cashflow exceptions after registry semantics
change.

## Tests Added

- `tests/e2e/test_transaction_type_coverage_matrix.py`
  - `test_transaction_type_coverage_sets_are_registry_derived`

## Validation Evidence

Focused validation is recorded in the issue comment and review ledger for this commit.

## Downstream Compatibility

No runtime code, route paths, DTOs, OpenAPI schemas, database schema, Kafka topics, event payload
shapes, transaction type names, or application behavior changed. This slice updates test-support
classification only and preserves the generated e2e transaction payload matrix.

## Documentation And Wiki Decision

Updated this architecture record, codebase review ledger, quality scorecard, refactor health
report, and repository context. No repo-local wiki update is required because no operator command,
route navigation, API field, or wiki workflow changed.

## Remaining Follow-Up

- Continue replacing or conformance-guarding local transaction-type sets in validation layers.
- Add broader representative booking-path coverage before closing issue #474.
