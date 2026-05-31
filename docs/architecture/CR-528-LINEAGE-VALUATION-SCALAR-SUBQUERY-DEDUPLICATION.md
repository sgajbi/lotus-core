# CR-528: Lineage Valuation Scalar Subquery Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository lineage-key reads.

## Finding

`OperationsRepository.get_lineage_keys(...)` built the same latest-valuation-job correlated subquery
four times to retrieve valuation date, job id, status, and correlation id. Each copy repeated the
same portfolio/security/epoch correlation, optional as-of guards, latest-date/id ordering, limit,
and `PositionState` correlation.

That duplication made an internal support hot path harder to maintain and increased the chance that
future changes to lineage valuation evidence would update one scalar projection but leave the others
on a different predicate or ordering shape.

## Change

1. Added a shared `_latest_valuation_job_scalar(...)` helper for latest valuation job scalar
   projections correlated to `PositionState`.
2. Replaced the four duplicated scalar subquery blocks in `get_lineage_keys(...)` with calls to the
   shared helper.
3. Preserved the existing SQL predicate shape, as-of guards, ordering, labels, and response fields.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
3. `python -m ruff format --check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
4. `git diff --check`

Results:

1. Focused operations repository proof passed.
2. Touched-surface ruff passed.
3. Touched-surface format check passed.
4. Whitespace check passed.

## Closure

Status: Hardened.

No database migration, API route shape, wiki source, or platform contract change was required. This
is a maintainability hardening slice that keeps lineage valuation evidence projections tied to one
governed correlated query shape.
