# CR-639: Realized Tax Evidence Timestamp Scope

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`PortfolioRealizedTaxSummary:v1` selected realized-tax evidence rows through an explicit
withholding-tax or other-interest-deduction predicate, but its `latest_evidence_timestamp` came from
the broader transaction ledger window. A non-tax transaction updated later in the same window could
therefore make the tax-summary evidence timestamp look fresher than the actual tax evidence, while
also forcing the timestamp query to scan a broader predicate than the product needed.

## Change

Added a repository method for the latest realized-tax evidence timestamp and routed the service to
the same explicit tax-evidence predicate used by the tax evidence row query.

## Impact

This keeps realized-tax runtime metadata aligned to source-owned tax evidence and narrows the
timestamp query to the product evidence scope while preserving source transaction counts, currency
aggregation, reporting-currency restatement, empty-evidence posture, response shape, and API
contract.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal product metadata correctness and query-scope
hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_transaction_repository.py tests/unit/services/query_service/services/test_transaction_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
