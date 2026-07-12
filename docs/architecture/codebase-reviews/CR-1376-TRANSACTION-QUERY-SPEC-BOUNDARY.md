# CR-1376 Transaction Query Spec Boundary

Date: 2026-07-05

## Objective

Fix GitHub issue #537 by moving transaction ledger filter, sort, and as-of query policy out of
`TransactionRepository` and into an application-owned query specification.

## Change

- Added `query_service.app.application.transaction_query` with:
  - `TransactionLedgerFilters`
  - `TransactionSortSpec`
  - `TransactionLedgerQuerySpec`
- Updated transaction read orchestration to build the query spec before repository access.
- Updated `TransactionRepository` to translate typed query specs and filters to SQL instead of
  accepting raw API/query parameters.
- Made transaction default business-calendar selection explicit in the service date policy by
  passing `DEFAULT_BUSINESS_CALENDAR_CODE` into the repository query.

## Expected Improvement

The transaction repository now has a narrower responsibility: SQL translation and persistence
reads. API/query semantics, sort validation, as-of cutoff selection, and ledger filter shape are
application-layer concerns with focused tests. This reduces design-time complexity and prevents the
same silent-fallback/API-policy-in-repository pattern fixed in issue #525 from returning through
filter or as-of paths.

## Tests Added Or Updated

- Added `tests/unit/services/query_service/application/test_transaction_query.py`.
- Updated transaction repository tests to assert SQL translation from `TransactionLedgerQuerySpec`.
- Updated transaction read/service/date tests to assert typed filter/spec handoff and explicit
  business-calendar selection.

## Validation Evidence

- `python -m pytest tests/unit/services/query_service/application/test_transaction_query.py tests/unit/services/query_service/repositories/test_transaction_repository.py tests/unit/services/query_service/services/test_transaction_reads.py tests/unit/services/query_service/services/test_transaction_dates.py tests/unit/services/query_service/services/test_transaction_service.py tests/unit/services/query_service/test_dependencies.py -q`
  - Result: 80 passed.
- `python -m ruff check ...`
  - Result: passed for changed source/test files.
- `python -m ruff format --check ...`
  - Result: passed for changed source/test files.
- `make typecheck`
  - Result: passed.
- `make architecture-guard`
  - Result: passed.
- `make quality-wiki-docs-gate`
  - Result: passed.
- `make openapi-gate`
  - Result: passed.
- `make api-route-catalog-guard`
  - Result: passed.
- `make api-vocabulary-gate`
  - Result: passed.
- `git diff --check`
  - Result: passed.

## Compatibility

No public route path, request parameter name, response DTO, OpenAPI field, database schema, or
runtime deployable topology changed. This is an internal boundary refactor preserving transaction
ledger behavior.

## Same-Pattern Scan

The active transaction ledger read path no longer passes raw `sort_by`, `sort_order`, filter fields,
or as-of date parameters directly into repository methods. Related cost-curve and performance
economics repository methods remain source-data evidence reads with their own bounded query
contracts and are not API transaction-ledger filter policy.

## Documentation And Wiki Decision

Repository context and the codebase review ledger are updated in this slice. No wiki source change
is required because the public API and operator workflow did not change.

No platform skill change is required for this slice: the existing backend governance and
codebase-review skills already direct API/query policy out of repositories. The durable lesson is
repo-specific transaction ledger guidance, so it belongs in `REPOSITORY-ENGINEERING-CONTEXT.md`.
