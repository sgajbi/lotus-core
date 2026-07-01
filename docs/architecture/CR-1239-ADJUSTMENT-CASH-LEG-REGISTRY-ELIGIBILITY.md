# CR-1239 Adjustment Cash-Leg Registry Eligibility

Date: 2026-07-01

## Objective

Continue GitHub issue #474 by removing the duplicated auto-generated adjustment cash-leg
eligibility set while preserving explicit transaction-specific amount, direction, and reason
formulas.

## Change

- Derived `AUTO_GENERATE_ELIGIBLE_TRANSACTION_TYPES` from the canonical transaction type registry
  for production-booking `trade` and `income` types with direct inflow/outflow cash effects and
  required cash-leg settlement.
- Kept the resolver table explicit for BUY, SELL, DIVIDEND, and INTEREST formula behavior.
- Added conformance coverage proving derived eligibility matches the registry and that every
  eligible type has an implemented resolver.

## Expected Improvement

Adjustment cash-leg generation no longer maintains a copied eligibility set. Future production
trade or income transaction types that require auto-generated adjustment cash legs must be
classified in the registry and implemented in the resolver table before tests pass.

## Tests Added

- `tests/unit/libs/portfolio-common/test_transaction_type_registry.py`
  - `test_auto_generated_adjustment_cash_leg_types_are_registry_derived_and_implemented`

## Validation Evidence

Focused validation is recorded in the issue comment and review ledger for this commit.

## Downstream Compatibility

No route paths, DTOs, OpenAPI schemas, database schema, Kafka topics, event payload shapes, or
transaction type names changed. Current auto-generated adjustment cash-leg eligibility and formulas
are preserved for BUY, SELL, DIVIDEND, and INTEREST.

## Documentation And Wiki Decision

Updated this architecture record, codebase review ledger, quality scorecard, refactor health
report, and repository context. No repo-local wiki update is required because no operator command,
route navigation, API field, or wiki workflow changed.

## Remaining Follow-Up

- Continue replacing or conformance-guarding local transaction-type sets in cost sorting, e2e
  coverage support, and validation layers.
- Add end-to-end transaction-type coverage for representative production and migration-only booking
  paths before closing issue #474.
