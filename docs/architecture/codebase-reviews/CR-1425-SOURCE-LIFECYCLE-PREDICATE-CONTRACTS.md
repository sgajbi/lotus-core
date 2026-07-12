# CR-1425 Source Lifecycle Predicate Contracts

Date: 2026-07-06

## Objective

Fix GitHub issue #538 by moving active/current source-data lifecycle predicate ownership out of
scattered persistence strings and repository literals into named, documented predicate contracts.

## Change

- Added `portfolio_common.source_lifecycle_predicates`.
- Defined named active/current contracts for DPM discretionary mandate bindings, client restriction
  profiles, sustainability preferences, client tax profiles, client tax rule sets, income-needs
  schedules, liquidity reserve requirements, planned withdrawals, model-portfolio targets,
  benchmark definitions, and index definitions.
- Rewired partial-index `postgresql_where` clauses to use the named contracts while preserving the
  generated SQL text.
- Rewired reference-data repository filters for DPM mandates, model-portfolio targets, and client
  source-data families to use the same active-status vocabulary.
- Added direct predicate-contract tests and bound existing index metadata tests to the named
  contracts.

## Expected Improvement

- Reduces design-time complexity by giving lifecycle semantics a single named ownership point.
- Reduces drift risk between source-data repository reads and hot-path partial indexes.
- Keeps runtime behavior unchanged because the SQL predicates and compiled repository filters remain
  equivalent.
- Makes future active/current lifecycle additions reviewable by concept instead of by local string.

## Compatibility

No API route, DTO field, OpenAPI schema, database table, index name, migration, repository method
signature, pagination behavior, response shape, or runtime deployment topology changed.

The generated partial-index SQL remains explicit and reviewable. This slice intentionally does not
change existing rows, status values, normalization behavior, effective-date window rules, or
consumer contracts.

## Validation

- `python -m pytest tests\unit\libs\portfolio-common\test_source_lifecycle_predicates.py tests\unit\libs\portfolio-common\test_database_models.py tests\unit\services\query_service\repositories\test_reference_data_repository.py tests\unit\services\query_service\repositories\test_repository_query_helpers.py -q`
- Scoped Ruff check and format check for touched files.
- Scoped mypy for the new predicate module and touched repository modules.
- Same-pattern scan: no remaining hardcoded `= 'active'` partial-index strings in
  `database_models.py` or touched query repository modules after the refactor.

## Documentation Decision

Repo context updated because this is a reusable repository-local boundary rule. No wiki change is
required because no operator workflow, public runbook, or published API behavior changed.

No platform skill change is required for this narrow repo-local predicate pattern; the durable
guidance belongs in `REPOSITORY-ENGINEERING-CONTEXT.md` and the codebase review ledger.
