# CR-1238 Portfolio Flow Registry Sets

Date: 2026-07-01

## Objective

Continue GitHub issue #474 by removing another duplicated transaction-type set from
portfolio-flow cash-entry guardrails and by extracting a reusable registry selector for
production-booking lifecycle-family views.

## Change

- Added `production_transaction_types_for_lifecycle_families(...)` to the canonical transaction
  type registry.
- Moved `FX_BUSINESS_TRANSACTION_TYPES` onto the reusable lifecycle-family selector.
- Derived `PORTFOLIO_FLOW_NO_AUTO_GENERATE_TRANSACTION_TYPES` from registry lifecycle families
  `cash_movement`, `expense`, and `transfer` instead of a hard-coded local set.
- Kept the guardrail error message derived from the same registry-backed set.
- Added conformance coverage proving the portfolio-flow no-auto-generate set matches the registry
  and that the FX business set uses the shared selector.

## Expected Improvement

Portfolio-flow cash-entry guardrails now share the registry pattern used by other transaction-type
rule tables. Future production-booking cash movement, expense, or transfer transaction types must be
classified in the registry first and will be included consistently, instead of requiring another
local copy-paste update.

## Tests Added

- `tests/unit/libs/portfolio-common/test_transaction_type_registry.py`
  - `test_portfolio_flow_no_auto_generate_types_are_registry_derived`

## Validation Evidence

Focused validation is recorded in the issue comment and review ledger for this commit.

## Downstream Compatibility

No route paths, DTOs, OpenAPI schemas, database schema, Kafka topics, event payload shapes, or
transaction type names changed. Current portfolio-flow guardrail behavior is preserved for `FEE`,
`TAX`, `DEPOSIT`, `WITHDRAWAL`, `TRANSFER_IN`, and `TRANSFER_OUT`; the rule source moved from a
duplicated local set to the shared registry.

## Documentation And Wiki Decision

Updated this architecture record, codebase review ledger, quality scorecard, refactor health
report, and repository context. No repo-local wiki update is required because no operator command,
route navigation, API field, or wiki workflow changed.

## Remaining Follow-Up

- Continue replacing or conformance-guarding local transaction-type sets in cost sorting,
  adjustment cash-leg generation, e2e coverage support, and validation layers.
- Add end-to-end transaction-type coverage for representative production and migration-only
  booking paths before closing issue #474.
