# CR-1256 Transaction Persistence Cash Account Policy

Date: 2026-07-01

## Scope

`persistence_service` raw transaction persistence for `TransactionEvent` settlement cash-account
references.

## Finding

GitHub issue #673 was partially hardened by CR-1200 on the read side: cash-balance responses no
longer promote unresolved transaction settlement account strings as governed cash-account master
evidence. The remaining persistence-boundary gap was that raw transaction landing still accepted a
supplied `settlement_cash_account_id` without an explicit policy decision or structured evidence
when the referenced cash-account master had not arrived or was inactive/outside its effective
window.

That made the system harder to operate because support teams could see provisional account
identity only later in source-product degradation, not at the raw persistence boundary where the
reference first entered Core.

## Action Taken

Added `raw_transaction_cash_account_reference_policy_v1` for raw transaction persistence:

1. transactions with no `settlement_cash_account_id` are `not_applicable`;
2. transactions with an active/effective matching cash-account master are `validated`;
3. transactions with an unresolved settlement cash-account reference land only as
   `provisional_raw_landing` with reason `TRANSACTION_CASH_ACCOUNT_REFERENCE_PENDING`.

`TransactionDBRepository` now checks `cash_account_masters` for an active/effective row matching
the portfolio, settlement cash-account id, settlement date or transaction date, and, when supplied,
the settlement cash instrument. `TransactionPersistenceConsumer` preserves raw landing behavior but
emits source-safe structured policy evidence when the account reference is unresolved.

## Compatibility

No Kafka topic, event schema, database schema, API route, OpenAPI contract, or downstream response
field changed. Existing raw transaction persistence remains allowed so source-batch ordering is not
broken when reference data arrives later.

The intentional behavior change is operational: unresolved settlement cash-account references are
now explicitly classified as provisional persistence evidence and downstream lifecycle remains
blocked or degraded through existing read-side supportability.

## Evidence

Focused behavior proof:

- `python -m pytest tests/unit/services/persistence_service/consumers/test_persistence_transaction_consumer.py tests/unit/services/persistence_service/repositories/test_transaction_db_repository.py -q --tb=short`
- Result: `11 passed`
- `python -m pytest tests/unit/services/persistence_service/consumers/test_persistence_transaction_consumer.py tests/unit/services/persistence_service/repositories/test_transaction_db_repository.py tests/unit/services/query_service/repositories/test_reporting_repository.py tests/unit/services/query_service/services/test_cash_balance_service.py tests/integration/services/query_service/test_main_app.py::test_openapi_describes_reporting_and_enhanced_discovery_contracts -q --tb=short`
- Result: `43 passed`
- `python -m pytest tests/unit/services/query_service/services/test_transaction_cost_curve.py tests/unit/services/query_service/services/test_performance_component_economics.py tests/unit/libs/portfolio-common/test_database_models.py -q --tb=short`
- Result: `44 passed`

Static and governance proof:

- Scoped Ruff lint and format checks passed for touched persistence source and tests.
- `make typecheck` passed with no issues in 50 source files.
- `python -m alembic heads` returned single head `c1009d0e1f2a3`.
- `make openapi-gate` passed.
- `make api-vocabulary-gate` passed.
- `make quality-wiki-docs-gate` passed.
- `git diff --check` passed with line-ending warnings only.
- Stranded-truth reconciliation found only Dependabot branches:
  `origin/dependabot/github_actions/github-actions-02325a8da5` and
  `origin/dependabot/pip/python-runtime-b808a9fc65`.
- `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` failed
  because the published GitHub wiki is not synchronized with repo-authored wiki source. Drift:
  `Data-Models.md`, `Mesh-Data-Products.md`, `Operations-Runbook.md`, `Outbox-Events.md`.

## Bank-Buyable Control Movement

This slice improves:

1. reference-data correctness for transaction settlement account identity,
2. operational supportability at the raw persistence boundary,
3. reuse of the provisional-reference policy pattern introduced for instrument references,
4. documentation truth for cash-account lifecycle handling.

It does not claim full bank-buyable readiness for `lotus-core`.
