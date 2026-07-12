# CR-340 Cashflow Projection External-Movement Contract Truth

## Scope

Review `GET /portfolios/{portfolio_id}/cashflow-projection` against `lotus-core#316`.

## Finding

The implementation and the endpoint audit evidence already converged on the intended domain rule:

1. booked mode returns booked portfolio cashflows,
2. projected mode adds future settlement-dated external cash movements,
3. projected mode does not claim to forecast all future transaction settlements.

The remaining defect was contract truth drift:

1. some schema examples and dependency-test fixtures still said "future transactions",
2. the route parameter description for `include_projected` was broader than the repository query,
3. the GitHub issue remained open even though the endpoint audit already recorded fresh live proof
   for the future withdrawal case.

## Actions Taken

1. tightened the `include_projected` parameter description to explicitly say projected future-dated
   external cash movements such as deposits and withdrawals,
2. updated cashflow-projection notes/examples to use the same wording,
3. added a repository SQL-shape proof that projected settlement queries are limited to
   `DEPOSIT` / `WITHDRAWAL`, constrained by settlement date window, and gated to transactions
   booked before the projection start date.

## Why This Matters

This closes the gap between domain behavior and published contract:

1. downstream consumers can now understand that projected mode is an operational liquidity view,
   not a generic future-transaction settlement forecast,
2. the future-withdrawal case from `#316` remains covered truthfully,
3. a quiet regression from external-cash projection into broader transaction-settlement semantics
   now has an explicit test fence.

## Evidence

- `src/services/query_service/app/routers/cashflow_projection.py`
- `src/services/query_service/app/dtos/cashflow_projection_dto.py`
- `tests/unit/services/query_service/repositories/test_query_cashflow_repository.py`
- `tests/unit/services/query_service/services/test_cashflow_projection_service.py`
- `tests/integration/services/query_service/test_cashflow_projection_router_dependency.py`
- `tests/integration/services/query_service/test_main_app.py`
- `pytest tests/unit/services/query_service/repositories/test_query_cashflow_repository.py -q`
- `pytest tests/unit/services/query_service/services/test_cashflow_projection_service.py -q`
- `pytest tests/integration/services/query_service/test_cashflow_projection_router_dependency.py -q`
- `pytest tests/integration/services/query_service/test_main_app.py -k cashflow_projection_contract_examples -q`
