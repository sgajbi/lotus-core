# CR-637: Benchmark Coverage Candidate Dates

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Benchmark coverage assembly expanded every active benchmark component segment into each calendar
date in the requested window before intersecting with price and benchmark-return evidence. Broad
windows with long-lived components therefore performed component-by-day expansion even though only
dates with both benchmark returns and index price evidence can become observed coverage dates.

## Change

Changed benchmark coverage assembly to build price evidence by date, intersect that with benchmark
return dates, and evaluate active component membership only for those candidate evidence dates.

## Impact

This reduces in-memory date expansion for broad benchmark coverage reports while preserving
component effective-window semantics, observed-date behavior, quality counts, latest evidence
timestamp handling, and response shape.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal repository response-assembly performance
hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
