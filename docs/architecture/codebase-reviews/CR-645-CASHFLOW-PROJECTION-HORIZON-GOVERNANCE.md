# CR-645: Cashflow Projection Horizon Governance

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`PortfolioCashflowProjection:v1` emits one point per calendar day. The router previously allowed a
3,650-day horizon while the service had no direct-call horizon guard, which made the endpoint capable
of returning very large operational-read payloads and left direct service callers outside the route
constraint. The router also mapped every `ValueError` to `404`, which would misclassify resolution
errors that are not missing portfolios.

## Change

Bounded the projection horizon to one operational year (`1..366`) in both the service and OpenAPI
query contract, added a documented `400` response for non-portfolio resolution errors, and kept
portfolio-not-found errors mapped to `404`.

## Impact

This makes the endpoint response-size posture explicit and keeps cashflow projection aligned with
the adjacent liquidity-ladder operational horizon while preserving booked/projected daily point
semantics, source metadata, portfolio-not-found behavior, and response shape for valid requests.

Repo-local README and wiki source were updated because the public source-data product capability
truth changed. Published wiki drift remains expected until this branch is merged to `main`.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_cashflow_projection_service.py tests/unit/services/query_service/routers/test_cashflow_projection_router.py tests/integration/services/query_service/test_main_app.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`
