# CR-1234 Cost Other Transaction Governance

Date: 2026-07-01

## Objective

Continue GitHub issue #474 by closing the cost-engine catch-all path for `OTHER` transactions.
`OTHER` is registry-classified as migration-only and must not receive default production booking
cost treatment.

## Change

- Removed the `TransactionType.OTHER -> DefaultStrategy` cost-calculator mapping.
- Added registry-backed fail-closed strategy resolution for transaction types that are not
  `production_booking_allowed`.
- Replaced implicit default-strategy fallback with an explicit error when a production-booking enum
  lacks a registered cost strategy.
- Added tests proving:
  - every production-booking cost enum has an explicit strategy,
  - `OTHER` is rejected before default cost fields are populated,
  - the registry still classifies `OTHER` as migration-only and not production-booking allowed.

## Expected Improvement

Unknown or migration-only transaction types can no longer bypass governance by receiving generic
book-cost fields. Future cost-engine enum additions now fail focused tests unless the registry
allows production booking and the cost engine registers an explicit strategy.

## Tests Added

- `tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py`
  - `test_cost_calculator_has_explicit_strategies_for_production_booking_enum_types`
  - `test_cost_calculator_rejects_other_before_default_costing`

## Validation Evidence

Focused validation:

- `python -m pytest tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py::test_cost_calculator_has_explicit_strategies_for_production_booking_enum_types tests/unit/services/calculators/cost_calculator_service/engine/test_cost_calculator.py::test_cost_calculator_rejects_other_before_default_costing tests/unit/libs/portfolio-common/test_transaction_type_registry.py -q`
  passed with 10 tests.
- Scoped Ruff lint and format passed for the cost calculator, cost tests, and registry tests.

Final validation for this commit is recorded in the issue comment and review ledger.

## Downstream Compatibility

This intentionally changes cost-calculator behavior for `OTHER`: it now records a cost-engine
error and leaves cost fields unset instead of applying `DefaultStrategy`. Route paths, DTOs,
OpenAPI schemas, database schema, Kafka topics, event payload shapes, and transaction type names are
unchanged. Legacy data migration can still carry `OTHER` as a classified type, but production cost
booking cannot process it without an explicit future migration policy.

## Documentation And Wiki Decision

Updated this architecture record, codebase review ledger, quality scorecard, refactor health
report, and repository context. No repo-local wiki update is required because no operator command,
route navigation, API field, or wiki workflow changed.

## Remaining Follow-Up

- Continue replacing or conformance-guarding local hard-coded transaction-type strategy sets across
  cost, cashflow, position, validation, and query layers.
- Add end-to-end transaction-type coverage for representative production and migration-only
  booking paths before closing issue #474.
