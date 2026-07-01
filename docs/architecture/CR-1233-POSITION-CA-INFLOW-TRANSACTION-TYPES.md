# CR-1233 Position Corporate-Action Inflow Transaction Types

Date: 2026-07-01

## Objective

Continue GitHub issue #474 by using the transaction-type registry to find and fix an adjacent
cross-layer drift in corporate-action position handling.

## Change

- Added `SPIN_IN` and `DEMERGER_IN` to the position calculator's transfer-inflow rule table.
- Added behavior coverage proving `SPIN_IN` and `DEMERGER_IN` increase position quantity and cost
  basis rather than being treated as transfer outflows.
- Added a registry-conformance test that derives expected position transfer inflows from
  `portfolio_common.transaction_type_registry` and compares them with the position calculator rule
  table.

## Expected Improvement

The position calculator now aligns with cashflow/query semantics and the canonical registry for
inbound spin-off and demerger target-security legs. Future additions to registry-classified
inflow-like transfer types fail fast if the position rule table is not updated.

## Tests Added

- `tests/unit/services/calculators/position_calculator/core/test_position_logic.py`
  - extends corporate-action transfer behavior cases for `SPIN_IN` and `DEMERGER_IN`.
- `tests/unit/libs/portfolio-common/test_transaction_type_registry.py`
  - adds registry-to-position-transfer-inflow conformance coverage.

## Validation Evidence

Focused validation:

- `python -m pytest tests/unit/libs/portfolio-common/test_transaction_type_registry.py tests/unit/services/calculators/position_calculator/core/test_position_logic.py::test_calculate_next_position_for_ca_transfer_types -q`
  passed with 20 tests.
- Scoped Ruff lint and format passed for the position calculator, position tests, and registry
  tests.

Final validation for this commit is recorded in the issue comment and review ledger.

## Downstream Compatibility

This intentionally changes position-calculator behavior for `SPIN_IN` and `DEMERGER_IN`: those
target-security legs now increase quantity and basis instead of being treated as outflow legs.
Route paths, DTOs, OpenAPI schemas, database schema, Kafka topics, event payload shapes, and
transaction type names are unchanged.

## Documentation And Wiki Decision

Updated this architecture record, codebase review ledger, quality scorecard, refactor health
report, and repository context. No repo-local wiki update is required because no operator command,
route navigation, API field, or wiki workflow changed.

## Remaining Follow-Up

- Continue replacing local hard-coded transaction-type sets with registry-derived or
  registry-conformance-protected views where the behavior impact is understood.
- Add support-status conformance for cost, cashflow, position, validation, and query layers before
  enabling target redemption or conversion/exercise runtime support.
