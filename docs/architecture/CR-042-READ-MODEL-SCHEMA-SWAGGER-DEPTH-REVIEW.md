# CR-042 Read Model Schema Swagger Depth Review

Date: 2026-03-10
Status: Hardened

## Scope

Deepen the shared read-model schema contracts used by `query_service` Swagger/OpenAPI:

- `PortfolioRecord`
- `PortfolioQueryResponse`
- `MarketPriceRecord`
- `MarketPriceResponse`
- `FxRateRecord`
- `FxRateResponse`
- `LookupItem`
- `LookupResponse`

## Findings

- Router-level Swagger depth had improved significantly, but several shared DTO schemas still had
  field definitions with little or no description/example depth.
- That left Swagger partially informative at the endpoint level while still underspecified at the
  component-schema level.
- The weakest remaining schemas were the simpler reference/read DTOs where field meaning is not
  always obvious from the name alone.

## Actions Taken

- Added field-level descriptions/examples to the shared market-price, FX-rate, and lookup DTOs.
- Tightened the response container description for portfolio query results.
- Added an OpenAPI integration assertion that locks the richer shared read-model schema depth in
  place.

## Follow-up

- Continue the same schema-depth pass wherever a router is already strong but the shared component
  schemas are still thin.
- Prefer field-level examples on compact read models so Swagger users can infer valid values quickly.

## Evidence

- `src/services/query_service/app/dtos/portfolio_dto.py`
- `src/services/query_service/app/dtos/price_dto.py`
- `src/services/query_service/app/dtos/fx_rate_dto.py`
- `src/services/query_service/app/dtos/lookup_dto.py`
- `tests/integration/services/query_service/test_main_app.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
