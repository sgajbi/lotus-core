# CR-533: Portfolio Control Stage Scope Deduplication

Date: 2026-05-31

## Scope

Query-service operations support repository portfolio-control stage count and list queries.

## Finding

`OperationsRepository.get_portfolio_control_stages_count(...)` and
`OperationsRepository.get_portfolio_control_stages(...)` both maintained the same support scope:

1. portfolio ownership,
2. `portfolio-stage:%` support-stage discriminator,
3. as-of support evidence guard,
4. stage id,
5. stage name,
6. business date,
7. governed stored status predicate.

Duplicating that scope made support pagination vulnerable to future count/list drift when adding
or correcting operational stage filters.

## Change

1. Added `_apply_portfolio_control_stage_scope(...)` as the shared portfolio-control stage filter
   helper.
2. Reused that helper from both stage count and list queries.
3. Preserved existing direct stored-status comparisons, portfolio-stage discriminator, ordering,
   offset/limit semantics, and response shape.

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
is a maintainability hardening slice that keeps portfolio-control stage support pagination aligned
to one governed filter scope.
