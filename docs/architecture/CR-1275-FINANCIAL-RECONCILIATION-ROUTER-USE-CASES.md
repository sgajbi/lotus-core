# CR-1275 Financial Reconciliation Router Use Cases

- Date: 2026-07-04
- Scope: financial reconciliation API router boundary
- GitHub issue: #636

## Objective

Move financial reconciliation repository construction, transaction commit handling, and read-query
orchestration out of `routers/reconciliation.py` while preserving the existing HTTP route contract.

## Expected Improvement

The financial reconciliation router now maps HTTP inputs to application commands/queries and maps
application results to HTTP responses. Repository construction and SQLAlchemy transaction handling
live behind application use cases and the service dependency module.

This removes the financial reconciliation router from
`docs/standards/api-layer-router-boundary-exceptions.json`, shrinking the transitional API-boundary
debt introduced by CR-1274.

## Tests Added

Added `tests/unit/services/financial_reconciliation_service/test_reconciliation_use_cases.py`
covering:

1. transaction-cashflow command execution and commit,
2. position-valuation command execution and commit,
3. timeseries-integrity command execution and commit,
4. run listing query behavior without commit,
5. get-run optional result behavior,
6. findings query behavior and missing-run handling.

## Validation Evidence

Local evidence for this slice:

1. `python -m pytest tests/unit/services/financial_reconciliation_service/test_reconciliation_use_cases.py tests/unit/scripts/test_architecture_boundary_guard.py -q`
   passed with 20 tests.
2. `python -m pytest tests/integration/services/financial_reconciliation_service/test_financial_reconciliation_app.py -q`
   passed with 11 tests.
3. `make architecture-guard` passed and the financial reconciliation router exception is no longer
   present in `docs/standards/api-layer-router-boundary-exceptions.json`.
4. Scoped Ruff lint and format checks passed for the affected reconciliation application, dependency,
   router, and unit-test files.

Additional broad validation:

1. `make quality-import-boundary-gate` passed with two kept contracts.
2. `make lint` passed.
3. `make quality-wiki-docs-gate` passed.
4. `make typecheck` passed.
5. `git diff --check` passed with Windows CRLF normalization warnings only.

## Downstream Compatibility Impact

No route path, HTTP status, request DTO, response DTO, OpenAPI output, database schema, Kafka topic,
reconciliation repository query, or reconciliation service behavior changed. The intentional change
is internal layering: transaction boundaries and repository selection moved out of the API router.

## Documentation Updates

Updated the codebase review ledger and repository context. No wiki update is required because this
slice changes internal architecture and validation evidence, not consumer-facing or operator-facing
wiki truth.
