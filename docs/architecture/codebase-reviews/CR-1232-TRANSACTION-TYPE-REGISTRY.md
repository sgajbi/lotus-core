# CR-1232 Transaction Type Registry

Date: 2026-07-01

## Objective

Begin fixing GitHub issue #474 by creating a canonical transaction type registry and pinning
existing transaction-type rule tables to it. The slice promotes the reusable pattern that
transaction-type semantics are domain truth and must not drift independently across calculators,
validators, query helpers, and API examples.

## Change

- Added `portfolio_common.transaction_type_registry` with a canonical
  `TransactionTypeDefinition` for current transaction types, internal generated FX cash-settlement
  markers, and target-only redemption/conversion types from the RFC backlog.
- Classified `OTHER` as `migration_only` and `production_booking_allowed=false` rather than a
  generic production catch-all.
- Classified target redemption and conversion/exercise types as `target_not_implemented` and
  `production_booking_allowed=false` until their runtime models, validation, cost, position,
  cashflow, and supportability paths are implemented.
- Added coverage tests proving:
  - every cost-calculator `TransactionType` enum value is registered,
  - local cashflow, position-calculator, and query-service position-flow rule-table transaction
    types are registered,
  - `OTHER` cannot be treated as a production booking type,
  - target redemption/conversion types are explicitly known but not runtime-supported,
  - registry entries are normalized and complete.
- Updated the cost-calculator enum comment for `OTHER` to point to the registry-governed
  migration-only posture.

## Expected Improvement

Adding or changing a transaction type in the cost enum or representative local rule tables now
requires an explicit registry classification. The registry makes unsupported target types visible
without allowing them to bypass production booking governance, and it gives future slices a single
source for progressively replacing local hard-coded transaction-type sets.

## Tests Added

- `tests/unit/libs/portfolio-common/test_transaction_type_registry.py`
  - cost enum coverage,
  - local cashflow/position/query rule-table coverage,
  - `OTHER` migration-only behavior,
  - RFC target redemption/conversion unsupported classification,
  - registry completeness, read-only publication, and lookup normalization.

## Validation Evidence

Initial focused validation:

- `python -m pytest tests/unit/libs/portfolio-common/test_transaction_type_registry.py -q`
  passed with 7 tests.
- Scoped Ruff lint and format passed for the new registry, new tests, and touched cost enum.

Final validation for this commit is recorded in the issue comment and review ledger.

## Downstream Compatibility

No route path, request/response DTO shape, OpenAPI schema, database schema, Kafka topic, event
payload, or runtime calculation behavior changed. This slice adds shared classification and tests
only. Redemption, conversion, exercise, and full command-model behavior remain unsupported until
separate implementation slices add runtime semantics and downstream compatibility evidence.

## Documentation And Wiki Decision

Updated this architecture record, codebase review ledger, repository context, quality scorecard,
and refactor health report. No repo-local wiki update is required because no operator command,
route navigation, API field, or wiki workflow changed.

## Remaining Follow-Up

- Continue issue #474 by replacing local hard-coded transaction-type sets with registry-derived
  views where runtime risk is low.
- Add validator/cost/position/cashflow/query conformance tests for support status and behavior,
  not just registration coverage.
- Keep redemption and conversion/exercise runtime behavior under their dedicated issue slices
  until those transaction families have validated processing, supportability, and downstream
  contract evidence.
