# CR-557: Lineage Valuation Job Lateral Lookup

Date: 2026-05-31

## Scope

Query-service operations support repository lineage key listing.

## Finding

`OperationsRepository.get_lineage_keys(...)` projected four latest valuation-job fields for every
lineage key: valuation date, job id, status, and correlation id. Each field used its own correlated
scalar subquery against `portfolio_valuation_jobs` with the same portfolio, normalized-security,
epoch, optional timestamp fence, ordering, and one-row limit.

That kept the SQL truthful, but it made the support-plane lineage listing perform four equivalent
latest-job probes per `PositionState` row. On large reprocessing backlogs this directly increases
read amplification in the operator path that is used to triage replay and artifact gaps.

## Change

1. Replaced the four scalar latest valuation-job subqueries with one lateral latest-job subquery.
2. Projected valuation date, job id, status, and correlation id from that single one-row lookup.
3. Preserved portfolio, normalized-security, epoch, `created_at`/`updated_at` as-of fencing,
   valuation-date/id ordering, artifact-gap priority semantics, pagination, and output labels.
4. Strengthened lineage query-shape coverage to require one `portfolio_valuation_jobs` source and
   a left lateral join.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
5. `python -m ruff format --check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
6. `git diff --check`

Results:

1. Focused operations repository proof passed.
2. Alembic reported a single current head.
3. Migration SQL contract smoke passed.
4. Touched-surface ruff passed.
5. Touched-surface format check passed.
6. Whitespace check passed.

## Closure

Status: Hardened.

No database migration, API route shape, wiki source, or platform contract change was required. The
existing valuation-job lookup indexes continue to match the lateral lookup predicates and ordering.
