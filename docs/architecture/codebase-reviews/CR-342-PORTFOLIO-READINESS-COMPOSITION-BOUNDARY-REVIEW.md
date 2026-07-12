# CR-342 Portfolio Readiness Composition Boundary Review

Date: 2026-05-27

## Scope

Reviewed `OperationsService.get_portfolio_readiness(...)` after CR-336 extracted support overview
composition. The same structural pattern remained: repository orchestration, readiness policy,
supportability metric emission, reason-code construction, and DTO assembly were all mixed in one
large service method.

## Findings

`OperationsService` was carrying portfolio-readiness domain composition that does not require
database access. That made readiness behavior harder to test directly, increased the size of the
operations service, and kept supportability metric label posture tied to a broad service test file
instead of a focused composition boundary.

The public API shape was already well described and no endpoint contract change was required.

## Actions Taken

Extracted portfolio-readiness composition into
`src/services/query_service/app/services/portfolio_readiness_builder.py`.

The operations service now remains responsible for:

1. portfolio existence validation,
2. support overview retrieval,
3. repository reads for booked transaction/snapshot dates,
4. snapshot valuation coverage lookup,
5. missing historical FX prerequisite lookup.

The new builder now owns:

1. readiness reason-code construction,
2. holdings/pricing/transactions/reporting bucket status derivation,
3. blocking-reason flattening,
4. supportability state and freshness derivation,
5. bounded `lotus_core_portfolio_supportability_total` metric emission,
6. final `PortfolioReadinessResponse` assembly.

Added direct unit tests for:

1. fully ready portfolio posture,
2. empty/no-activity posture,
3. pending backlog and snapshot-lag posture,
4. blocking historical-FX/control posture,
5. bounded metric-label contract preservation.

## Validation

Targeted validation:

```text
python -m pytest tests/unit/services/query_service/services/test_portfolio_readiness_builder.py tests/unit/services/query_service/services/test_operations_service.py -q
57 passed

python -m ruff check src/services/query_service/app/services/portfolio_readiness_builder.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/services/test_portfolio_readiness_builder.py
All checks passed
```

## Follow-Up

Continue using this pattern for operations support-plane composition where service methods still
mix repository orchestration with deterministic DTO construction. No wiki source change is required
for this slice because the public endpoint shape and operator workflow did not change.
