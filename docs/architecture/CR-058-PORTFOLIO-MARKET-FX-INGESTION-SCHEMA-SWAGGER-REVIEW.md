# CR-058 Portfolio, Market Price, and FX Rate Ingestion Schema Swagger Review

## Scope

- `src/services/ingestion_service/app/DTOs/portfolio_dto.py`
- `src/services/ingestion_service/app/DTOs/market_price_dto.py`
- `src/services/ingestion_service/app/DTOs/fx_rate_dto.py`
- `tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py`

## Findings

- These three DTO families were still below the rest of the write-plane Swagger standard.
- They relied on sparse examples or top-level model examples rather than field-level component documentation.
- That made the ingestion write plane uneven:
  - router contracts were strong
  - shared component schemas were not yet equally usable for schema-first clients

## Actions taken

- Added field-level descriptions/examples to:
  - `Portfolio`
  - `MarketPrice`
  - `FxRate`
- Added described request-wrapper collection fields with explicit examples to:
  - `PortfolioIngestionRequest`
  - `MarketPriceIngestionRequest`
  - `FxRateIngestionRequest`
- Added ingestion app OpenAPI assertions to lock the richer shared-schema behavior in place

## Result

- Portfolio master, market price, and FX rate write-plane component schemas now match the surrounding router depth much more closely.

## Evidence

- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py -q`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
