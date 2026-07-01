# CR-1257 Portfolio Tax-Lot Typed Read Record

Date: 2026-07-01

## Scope

`PortfolioTaxLotWindow:v1` repository output, source-data row mapping, and boundary conformance.

## Finding

GitHub issues #664 and #648 are valid. `BuyStateRepository.list_portfolio_tax_lots(...)` returned
raw `(PositionLotState, trade_currency)` tuples to the source-data application layer, and
`portfolio_tax_lot_record(...)` accepted an untyped row object. That made the mapping contract
implicit and let SQLAlchemy ORM shape cross the repository/application boundary for a high-value
source-data product.

## Action Taken

Added `PortfolioTaxLotReadRecord` in `query_service.app.read_models` and changed:

1. `BuyStateRepository.list_portfolio_tax_lots(...)` to map SQLAlchemy rows into typed read records,
2. `PortfolioTaxLotWindow:v1` page, lineage, supportability, and pagination helpers to consume the
   read record directly,
3. `portfolio_tax_lot_record(...)` to accept `PortfolioTaxLotReadRecord` instead of `Any`,
4. repository, mapper, source-data window, and boundary-conformance tests to use and assert the
   typed record.

This is an in-process design-boundary improvement only. It does not introduce a new runtime service.

## Compatibility

No API route, OpenAPI schema, Kafka topic, database schema, source-product identity, response field,
pagination contract, lineage contract, or supportability behavior changed. The repository still
queries the same `position_lot_state` and transaction trade-currency evidence; it now converts the
result at the adapter boundary.

## Evidence

Focused behavior proof:

- `python -m pytest tests/unit/services/query_service/repositories/test_buy_state_repository.py tests/unit/services/query_service/services/test_portfolio_tax_lot_window.py tests/unit/services/query_service/services/test_reference_data_mappers.py tests/unit/boundary_mapping/test_transaction_and_source_data_conformance.py -q --tb=short`
- Result: `45 passed`

Static and governance proof:

- scoped Ruff lint passed for touched source and tests,
- scoped Ruff format check passed for touched source and tests,
- `make test-boundary-mapping-conformance` passed with `3 passed`,
- `make typecheck` passed with no issues in 50 source files,
- `make quality-wiki-docs-gate` passed,
- `git diff --check` passed with line-ending warnings only,
- stranded-truth reconciliation found only Dependabot branches:
  `origin/dependabot/github_actions/github-actions-02325a8da5` and
  `origin/dependabot/pip/python-runtime-b808a9fc65`,
- `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` failed
  because the published GitHub wiki is not synchronized with repo-authored wiki source. Drift:
  `Data-Models.md`, `Mesh-Data-Products.md`, `Operations-Runbook.md`, `Outbox-Events.md`.

## Documentation And Wiki Decision

Updated architecture docs, repository context, and quality reports because the repository output
shape and mapping guidance changed. No repo-local wiki source update was made because no
operator-facing workflow, public API contract, route behavior, or published data-model table shape
changed in this slice.

## Issue Posture

This advances #664 and #648 but does not close either issue locally. #664 still needs the
`PerformanceComponentEconomics:v1` optional cashflow/cost-row mapping work called out in its
acceptance criteria, including multiple fee currencies. #648 still needs broader repository
result-mapping standards and at least one architecture/static detection path for ORM-row leakage.

## Bank-Buyable Control Movement

This slice improves:

1. infrastructure/application boundary clarity,
2. source-data mapper testability,
3. typed contracts for high-value tax-lot source evidence,
4. repeatable pattern evidence for future source-data product mapper hardening.
