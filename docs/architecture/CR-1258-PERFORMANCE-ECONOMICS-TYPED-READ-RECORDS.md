# CR-1258 Performance Economics Typed Read Records

Date: 2026-07-01

## Scope

`PerformanceComponentEconomics:v1` repository output, optional cashflow/cost evidence mapping, and
boundary conformance.

## Finding

GitHub issue #664 is valid. `PerformanceComponentEconomics:v1` still accepted broad transaction
objects in the source-data assembly path and repeatedly reached through optional `cashflow` and
`costs` joins with `getattr(...)`. That kept SQLAlchemy relationship shape implicit in application
code and made optional joined evidence harder to type-check, test, and reuse.

This is the same defect class as CR-1257: high-value source-data products should consume explicit
read records at the repository boundary rather than raw ORM rows, tuple-shaped SQL results, or
ad-hoc objects.

## Action Taken

Added typed read records in `query_service.app.read_models`:

1. `PerformanceEconomicsTransactionReadRecord`,
2. `PerformanceEconomicsCashflowReadRecord`,
3. `PerformanceEconomicsCostReadRecord`.

Changed `TransactionRepository.list_performance_component_economics_evidence(...)` to preserve the
existing query shape and latest-cashflow selection while mapping returned ORM `Transaction`,
`Cashflow`, and `TransactionCost` rows into typed read records before returning.

Changed `performance_component_economics.py` to consume typed read records directly. Optional
cashflow evidence is now represented as `PerformanceEconomicsCashflowReadRecord | None`, and fee
evidence is represented as `tuple[PerformanceEconomicsCostReadRecord, ...]`. Cost-component
deduplication is now local to the typed performance-economics read-record model and preserves the
existing `(fee_type, currency)` component identity behavior, fallback trade-fee behavior, and mixed
fee-currency response behavior.

This is an in-process design-boundary improvement only. It does not introduce a new runtime service.

## Compatibility

No API route, OpenAPI schema, response DTO, Kafka topic, database schema, source-product identity,
pagination contract, lineage contract, or supportability behavior changed.

The repository still queries the same `transactions`, latest `cashflows`, and `transaction_costs`
evidence. The intentional internal change is that repository output is now a typed read-record
contract before application/source-data assembly.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\query_service\services\test_performance_component_economics.py tests\unit\services\query_service\repositories\test_transaction_repository.py tests\unit\boundary_mapping\test_transaction_and_source_data_conformance.py -q --tb=short`
- Result: `47 passed`

Static and governance proof:

- scoped Ruff lint passed for touched source and tests,
- scoped Ruff format check passed for touched source and tests,
- `make test-boundary-mapping-conformance` passed with `4 passed`,
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

Updated architecture docs, repository context, quality reports, and mapping-boundary guidance
because the repository output shape and boundary conformance coverage changed. No repo-local wiki
source update was made because no operator-facing workflow, public API contract, route behavior, or
published data-model table shape changed in this slice.

## Issue Posture

This closes the local implementation gap for #664 that remained after CR-1257: representative
high-value source-data mappers now cover both `PortfolioTaxLotWindow:v1` and
`PerformanceComponentEconomics:v1`, including missing optional joined rows, zero/default values,
multiple fee currencies, fee component identity, currency/date normalization, source lineage, and
typecheck-backed field access.

Issue #648 remains open for broader repository result-mapping standards and static/architecture
detection of ORM-row leakage across the remaining repository surface.

## Bank-Buyable Control Movement

This slice improves:

1. infrastructure/application boundary clarity,
2. typed source-data contracts for contribution-economics evidence,
3. optional joined-row correctness and testability,
4. boundary conformance coverage for another high-value source-data product,
5. repeatable guidance for repository output-shape hardening.
