# CR-950: Reference Integration Market Data DTO Boundary

Date: 2026-06-05

## Scope

Move the market-data coverage DTO family out of `reference_integration_dto.py` without changing
public DTO class names, router imports, service imports, OpenAPI component names, validation
behavior, request/response fields, examples, or source-data product identity metadata.

## Finding

`reference_integration_dto.py` still owned market-data coverage request validation, currency-pair
normalization, price/FX coverage record DTOs, supportability DTOs, and response DTOs inline. This
kept a source-data product contract family coupled to a broad shared DTO module and left
`reference_integration_dto.py` as an active C-ranked hotspot after CR-949.

## Action

Extracted `reference_integration_market_data_coverage_dto.py` with:

- `MarketDataCurrencyPair`
- `MarketDataCoverageRequest`
- `MarketDataPriceCoverageRecord`
- `MarketDataFxCoverageRecord`
- `MarketDataCoverageSupportability`
- `MarketDataCoverageWindowResponse`

The original `reference_integration_dto.py` keeps compatibility re-exports before
`DpmSourceReadinessRequest`, preserving existing service, router, and test imports while allowing
downstream DPM readiness DTOs to continue referencing `MarketDataCoverageRequest`.

## Result

`reference_integration_dto.py` shrank from 3,264 SLOC to 3,078 SLOC and improved from `C (1.33)`
to `C (4.62)` under Radon maintainability. The extracted market-data coverage DTO module reports
`A (35.77)`. `reference_integration_dto.py` remains an active C-ranked hotspot, but the remaining
B-ranked DTO validators are now concentrated in instrument eligibility, portfolio tax lot, and DPM
source readiness families.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_market_data_coverage.py tests\unit\services\query_service\services\test_dpm_source_readiness.py -q`
  => 48 passed
- `python -m pytest tests\integration\services\query_control_plane_service\test_control_plane_app.py -q`
  => 39 passed
- `python -m ruff check src\services\query_service\app\dtos\reference_integration_dto.py src\services\query_service\app\dtos\reference_integration_market_data_coverage_dto.py tests\unit\services\query_service\services\test_market_data_coverage.py tests\unit\services\query_service\services\test_dpm_source_readiness.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\dtos\reference_integration_dto.py src\services\query_service\app\dtos\reference_integration_market_data_coverage_dto.py tests\unit\services\query_service\services\test_market_data_coverage.py tests\unit\services\query_service\services\test_dpm_source_readiness.py`
  => 4 files already formatted
- `python -m radon raw src\services\query_service\app\dtos\reference_integration_dto.py src\services\query_service\app\dtos\reference_integration_market_data_coverage_dto.py`
  => `reference_integration_dto.py` 3,078 SLOC; market-data coverage DTO module 208 SLOC
- `python -m radon mi src\services\query_service\app\dtos\reference_integration_dto.py src\services\query_service\app\dtos\reference_integration_market_data_coverage_dto.py -s`
  => main DTO `C (4.62)`, market-data coverage DTO `A (35.77)`
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal DTO module boundary extraction that preserves
public API class names, OpenAPI component names, source-data product identity, validation behavior,
and operator-facing documentation truth.
