# CR-1240 Cost Sort Cash Dependency Conformance

Date: 2026-07-01

## Objective

Continue GitHub issue #474 by guarding the cost-engine cash dependency sort rule table against
transaction-type registry drift.

## Change

- Added registry conformance coverage for the cost-engine sorter cash inflow and outflow
  transaction-type sets.
- Proved sorter cash dependency types are registered, production-booking compatible, directionally
  compatible with registry position/cash effects, and not present in both inflow and outflow sets.
- Preserved the current sorter rule table because cash-row trade labels intentionally invert product
  trade cash direction (`BUY` cash rows are inflows and `SELL` cash rows are outflows).

## Expected Improvement

The cost sorter cannot silently add unregistered, migration-only, target-only, or directionally
incompatible transaction types to cash dependency ordering. This hardens the remaining local sorter
table without changing runtime ordering semantics before cash-leg vocabulary is modeled as a
first-class registry dimension.

## Tests Added

- `tests/unit/libs/portfolio-common/test_transaction_type_registry.py`
  - `test_cost_sort_cash_dependency_sets_are_registry_compatible`

## Validation Evidence

Focused validation is recorded in the issue comment and review ledger for this commit.

## Downstream Compatibility

No route paths, DTOs, OpenAPI schemas, database schema, Kafka topics, event payload shapes,
transaction type names, or cost-engine sort behavior changed. This is a conformance guard over the
existing sorter rule table.

## Documentation And Wiki Decision

Updated this architecture record, codebase review ledger, quality scorecard, refactor health
report, and repository context. No repo-local wiki update is required because no operator command,
route navigation, API field, or wiki workflow changed.

## Remaining Follow-Up

- Model cash-leg transaction direction explicitly before replacing cost sorter cash dependency
  trade-label inversion with a fully registry-derived rule.
- Continue replacing or conformance-guarding local transaction-type sets in e2e coverage support
  and validation layers.
