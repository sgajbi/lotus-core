# CR-521: Reference Status Helper Dead Path Cleanup

Date: 2026-05-31

## Scope

Query-service reference-data repository lifecycle status predicates.

## Finding

The prior source-data index hardening slices moved DPM model, mandate, client, benchmark, and index
reference reads away from `lower(trim(...))` predicates and onto governed stored lifecycle values.
After CR-520, `_reference_status_expr(...)` no longer had any call sites. Keeping the helper around
made the repository look as if function-wrapped lifecycle status predicates were still an approved
pattern for new hot-path reads.

## Change

Removed `_reference_status_expr(...)` from
`src/services/query_service/app/repositories/reference_data_repository.py`. The surviving
`_normalize_reference_status(...)` helper remains because benchmark and index status request values
are still normalized at the boundary before direct stored-value comparison.

## Evidence

Commands:

1. `rg "_reference_status_expr\(" src tests -n`
2. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q`
3. `python -m ruff check src/services/query_service/app/repositories/reference_data_repository.py tests/unit/services/query_service/repositories/test_reference_data_repository.py`
4. `python -m ruff format --check src/services/query_service/app/repositories/reference_data_repository.py tests/unit/services/query_service/repositories/test_reference_data_repository.py`
5. `git diff --check`

Results:

1. Dead helper search now finds no runtime or test references.
2. Reference-data repository proof passed.
3. Touched-surface ruff passed.
4. Touched-surface format check passed.
5. Whitespace check passed.

## Closure

Status: Hardened.

No API route shape, database migration, wiki source, or platform contract change was required. This
cleanup removes stale predicate guidance after the lifecycle-status index hardening series.
