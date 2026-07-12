# CR-530: Support Job Health Summary Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository valuation and aggregation job health summary queries.

## Finding

`OperationsRepository.get_valuation_job_health_summary(...)` and
`OperationsRepository.get_aggregation_job_health_summary(...)` both built the same support health
summary query shape:

1. open pending/processing job counts,
2. processing and stale-processing counts,
3. failed and recent-failed counts,
4. oldest open business date,
5. oldest open job identity ordered by business date, update timestamp, and job id.

The only real differences were the job table, business-date column, and valuation-only security id
projection. Keeping the aggregate and oldest-open-job SQL fragments duplicated made support
diagnostics vulnerable to count/list drift when future status or stale-window semantics change.

## Change

1. Added `_support_job_health_aggregate(...)` to build the shared aggregate summary over a prepared
   job base subquery.
2. Added `_oldest_open_support_job(...)` to build the shared oldest-open-job selector while allowing
   valuation to project its security id.
3. Reused those helpers from both valuation and aggregation job health summaries while preserving
   existing portfolio predicates, superseded valuation filtering, as-of guards, stale/recent-failed
   windows, ordering, and response fields.

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
is a maintainability hardening slice that keeps valuation and aggregation support job health
summaries aligned to one governed aggregate and oldest-open-job query shape.
