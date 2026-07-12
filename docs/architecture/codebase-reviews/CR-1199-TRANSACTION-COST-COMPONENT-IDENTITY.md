# CR-1199: Transaction Cost Component Identity

Date: 2026-06-30

## Objective

Address GitHub issue #672 by giving explicit transaction-cost evidence a durable component
identity. Prevent accidental duplicate fee rows from inflating `TransactionCostCurve:v1` and
`PerformanceComponentEconomics:v1`.

## Change

- Added a normalized unique index for `transaction_costs` component identity:
  `(transaction_id, lower(trim(fee_type)), upper(trim(currency)))`.
- Added a migration pre-cleanup that retains the latest row per normalized component identity before
  creating the unique index.
- Normalized cost-calculator fee-row currency when persisting transaction-cost components.
- Added a shared read-side `unique_transaction_cost_components(...)` helper and reused it in both
  transaction-cost curve and performance component economics builders.
- Documented the component grain in methodology and wiki source.

## Expected Improvement

The database now enforces the authoritative component grain, and the two source-data products that
consume transaction-cost rows defensively follow the same identity. This reduces overstatement risk
from replay, repair, or legacy duplicate rows without changing the public product routes or response
shape.

## Tests Added

- Model/index contract coverage for the normalized unique transaction-cost component index.
- `TransactionCostCurve:v1` coverage proving duplicate normalized component rows are counted once
  while distinct fee components still aggregate.
- `PerformanceComponentEconomics:v1` coverage proving duplicate normalized fee components do not
  inflate returned fee evidence.

## Validation Evidence

- `python -m pytest tests/unit/services/query_service/services/test_transaction_cost_curve.py tests/unit/services/query_service/services/test_performance_component_economics.py tests/unit/libs/portfolio-common/test_database_models.py -q`
  passed with 44 tests.
- `python -m ruff check src/libs/portfolio-common/portfolio_common/database_models.py src/services/query_service/app/services/transaction_cost_curve.py src/services/query_service/app/services/performance_component_economics.py src/services/calculators/cost_calculator_service/app/repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/services/test_transaction_cost_curve.py tests/unit/services/query_service/services/test_performance_component_economics.py alembic/versions/c1006a7b8c9d0_feat_add_transaction_cost_component_identity.py`
  passed.
- `python -m ruff format --check src/libs/portfolio-common/portfolio_common/database_models.py src/services/query_service/app/services/transaction_cost_curve.py src/services/query_service/app/services/performance_component_economics.py src/services/calculators/cost_calculator_service/app/repository.py tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/services/test_transaction_cost_curve.py tests/unit/services/query_service/services/test_performance_component_economics.py alembic/versions/c1006a7b8c9d0_feat_add_transaction_cost_component_identity.py`
  passed.
- `python -m alembic heads` reported single head `c1006a7b8c9d0`.
- `make quality-wiki-docs-gate` passed.
- `git diff --check` passed.
- `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` reported
  existing published-wiki drift for `Data-Models.md`, `Event-Replay-Service.md`,
  `Financial-Reconciliation.md`, `Ingestion-Service.md`, `Mesh-Data-Products.md`,
  `Operations-Runbook.md`, `Outbox-Events.md`, and `Validation-and-CI.md`; repo-local wiki source
  validation passed.

## Downstream Compatibility

No route path, API DTO, response field, Kafka topic, or transaction event schema changed. The
intentional behavior change is duplicate protection at the normalized transaction-cost component
grain. Legitimate multiple fee components remain supported when their `fee_type` or `currency`
differs.

## Documentation

- Updated transaction-cost curve methodology.
- Updated performance component economics methodology.
- Updated repo-local Mesh Data Products and Data Models wiki source.
- Updated the codebase review ledger, quality scorecard, and refactor health report.

## Follow-Up

Issue #672 remains open for PR/CI/QA evidence. Future source-system support for multiple same-type
same-currency fee components must introduce a separate governed source component id or sequence
instead of weakening this component grain.
