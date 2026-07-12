# CR-1235 Query Position Flow Registry Sets

Date: 2026-07-01

## Objective

Continue GitHub issue #474 by removing duplicated transaction-type position-effect rule sets from
query-service projected-position quantity math.

## Change

- Replaced hard-coded query `POSITION_*_TRANSACTION_TYPES` and
  `CASH_POSITION_*_TRANSACTION_TYPES` sets with registry-derived frozensets based on
  `production_booking_allowed` and canonical `position_effect`.
- Added exact conformance coverage proving query position-flow effect sets match the registry.

## Expected Improvement

Projected-position query behavior now follows the same canonical transaction-type registry used by
cost and calculator conformance tests. Future production-booking transaction types that change
position quantity or cash-position amount cannot be added to the registry without automatically
being visible to query position-flow math and its tests.

## Tests Added

- `tests/unit/services/query_service/services/test_position_flow_effects.py`
  - `test_position_flow_effect_sets_are_registry_derived`

## Validation Evidence

Focused validation:

- `python -m pytest tests/unit/services/query_service/services/test_position_flow_effects.py tests/unit/libs/portfolio-common/test_transaction_type_registry.py -q`
  passed locally.

Final validation for this commit is recorded in the issue comment and review ledger.

## Downstream Compatibility

No route paths, DTOs, OpenAPI schemas, database schema, Kafka topics, event payload shapes, or
transaction type names changed. The effective current behavior is preserved for existing production
booking types; this slice changes the rule source from a query-local duplicated set to the shared
registry.

## Documentation And Wiki Decision

Updated this architecture record, codebase review ledger, quality scorecard, refactor health
report, and repository context. No repo-local wiki update is required because no operator command,
route navigation, API field, or wiki workflow changed.

## Remaining Follow-Up

- Continue replacing or conformance-guarding local hard-coded transaction-type strategy sets across
  cost sorting, cashflow transfer signing, validation, and query layers.
- Add end-to-end transaction-type coverage for representative production and migration-only
  booking paths before closing issue #474.
