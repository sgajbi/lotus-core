# CR-343 Load-Run Progress Composition Boundary Review

Date: 2026-05-27

## Scope

Reviewed `OperationsService.get_load_run_progress(...)` as the next operations support-plane
composition target after CR-342.

## Findings

The service method mixed the repository read with deterministic operator-progress policy,
scheduler dispatch math, completion-gap derivation, coverage ratios, tail-latency calculations,
handoff-pressure classification, and `LoadRunProgressResponse` assembly. That made the operations
service larger than necessary and kept reusable load-run progress logic attached to a broad service
class.

## Actions Taken

Extracted deterministic load-run progress composition into
`src/services/query_service/app/services/load_run_progress_builder.py`.

The operations service now owns:

1. timestamp capture,
2. repository retrieval,
3. not-found classification for empty load runs,
4. delegation to the load-run progress builder.

The builder now owns:

1. run-state derivation,
2. operator progress classification,
3. scheduler dispatch lower-bound math,
4. completion and remaining-work counts,
5. coverage ratios,
6. handoff-pressure classification,
7. tail-latency and age calculations,
8. final `LoadRunProgressResponse` assembly.

Added focused unit coverage for derived metrics, bounded empty ratios, terminal/stale operator
states, and handoff-pressure paths.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/query_service/services/test_load_run_progress_builder.py tests/unit/services/query_service/services/test_portfolio_readiness_builder.py tests/unit/services/query_service/services/test_operations_service.py -q
60 passed

python -m ruff check src/services/query_service/app/services/load_run_progress_builder.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/services/test_load_run_progress_builder.py tests/unit/services/query_service/services/test_operations_service.py
All checks passed
```

## Follow-Up

Continue extracting deterministic operations support-plane DTO construction where it materially
shrinks `OperationsService` and improves direct testability. No wiki source change is required for
this slice because the API response shape and operator workflow did not change.
