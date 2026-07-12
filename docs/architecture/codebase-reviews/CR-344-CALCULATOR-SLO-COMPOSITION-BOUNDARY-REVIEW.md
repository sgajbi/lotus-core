# CR-344 Calculator SLO Composition Boundary Review

Date: 2026-05-27

## Scope

Reviewed `OperationsService.get_calculator_slos(...)` after extracting support overview,
portfolio readiness, and load-run progress composition.

## Findings

The method mixed repository orchestration with deterministic SLO bucket construction and backlog-age
derivation. The logic was smaller than the previous extraction targets, but it was the same
support-plane composition pattern and kept DTO construction inside the broad operations service.

## Actions Taken

Extracted deterministic calculator SLO composition into
`src/services/query_service/app/services/calculator_slo_builder.py`.

The operations service now owns:

1. portfolio existence validation,
2. timestamp capture,
3. repository retrieval for latest business date and health summaries,
4. delegation to the builder.

The builder now owns:

1. valuation SLO bucket assembly,
2. aggregation SLO bucket assembly,
3. reprocessing SLO bucket assembly,
4. backlog-age derivation using latest business date or generated UTC date fallback,
5. final `CalculatorSloResponse` assembly.

Added direct tests for business-date-backed backlog ages and generated-date fallback behavior.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/query_service/services/test_calculator_slo_builder.py tests/unit/services/query_service/services/test_load_run_progress_builder.py tests/unit/services/query_service/services/test_portfolio_readiness_builder.py tests/unit/services/query_service/services/test_operations_service.py -q
62 passed

python -m ruff check src/services/query_service/app/services/calculator_slo_builder.py src/services/query_service/app/services/load_run_progress_builder.py src/services/query_service/app/services/portfolio_readiness_builder.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/services/test_calculator_slo_builder.py tests/unit/services/query_service/services/test_load_run_progress_builder.py tests/unit/services/query_service/services/test_portfolio_readiness_builder.py tests/unit/services/query_service/services/test_operations_service.py
All checks passed
```

## Follow-Up

Continue reviewing operations support-plane list endpoints and record builders for repeated
job-record or page-response construction patterns. No wiki source change is required for this slice
because the endpoint contract and operator workflow did not change.
