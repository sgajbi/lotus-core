# CR-1126 Holdings Cash Weight Source Evidence

Date: 2026-06-21

## Scope

`HoldingsAsOf:v1` cash-balance source product exposed by
`GET /portfolios/{portfolio_id}/cash-balances`.

## Finding

`lotus-idea` high-cash source-adapter work needs a Core-owned cash-weight fact. The existing
cash-balances response exposed cash-account balances and cash totals, but not a source-owned cash
weight. Without this field, downstream consumers would have to reconstruct Core-owned portfolio
facts from cash totals and AUM locally, creating methodology drift and weakening source-product
ownership.

## Action Taken

Added `source_reported_cash_weight` to `CashBalancesTotals` as a decimal ratio, calculated from:

`total_balance_portfolio_currency / source_reported_cash_weight_denominator_portfolio_currency`

The denominator is the sum of Core-owned `daily_position_snapshots.market_value` values for the
same portfolio and resolved as-of date. The response now also publishes:

- `source_reported_cash_weight_denominator_portfolio_currency`,
- `source_reported_cash_weight_supportability`.

If denominator evidence is missing, zero or negative, or stale relative to the resolved as-of date,
the weight and denominator return null with an explicit blocked supportability posture. The route
does not invent liquidity advice, idle-cash recommendations, deployment actions, or downstream
analytics claims.

`lotus-idea` is now declared as an approved consumer of `HoldingsAsOf:v1` in the repo-native domain
data product declaration and source-data product catalog.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\query_service\services\test_cash_balance_service.py tests\integration\services\query_service\test_cash_balances_router.py tests\integration\services\query_service\test_main_app.py::test_openapi_describes_reporting_and_enhanced_discovery_contracts tests\integration\services\query_service\test_main_app.py::test_openapi_exposes_holdings_as_of_runtime_supportability_metadata tests\unit\test_domain_data_product_contracts.py tests\unit\scripts\test_source_data_product_contract_guard.py -q`
- Result: `39 passed`

Focused static proof:

- `python -m ruff check ...`
- Result: passed for the touched DTO, service, router, catalog, and tests

Contract proof:

- `make openapi-gate`
- `make api-vocabulary-gate`
- `make domain-product-validate`
- Result: all passed

## Residual Risk

This change expands the Core producer contract only. `lotus-idea` still needs its own consumer-side
adapter change and validation before high-cash or idle-liquidity evidence can be claimed in that
application. That downstream work is tracked in `sgajbi/lotus-idea#22`. Gateway or UI casing
transformations, if needed, belong in their owning layers and must preserve this source-owned field
and supportability posture.

## Bank-Buyable Control Movement

This slice improves:

- source-owned methodology and supportability for a downstream cash-weight fact,
- OpenAPI and domain-product truth for the expanded `HoldingsAsOf:v1` contract,
- deterministic tests for populated, missing, zero, stale, and precision behavior.

It does not claim full bank-buyable readiness for `lotus-core` or `lotus-idea`.
