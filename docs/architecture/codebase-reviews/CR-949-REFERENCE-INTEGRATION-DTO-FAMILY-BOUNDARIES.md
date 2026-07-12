# CR-949: Reference Integration DTO Family Boundaries

Date: 2026-06-05

## Scope

Move cohesive query-control-plane DTO families out of the monolithic
`reference_integration_dto.py` module without changing public DTO class names, router imports,
service imports, OpenAPI component names, validation behavior, request/response fields, examples,
or source-data product identity metadata.

## Finding

`reference_integration_dto.py` still grouped many unrelated source-data product DTO families in one
large module. The transaction-cost curve and benchmark market-series models each carried request
validators and response DTOs inline, increasing the size and maintainability pressure of the
shared reference integration DTO module.

## Action

Extracted two cohesive DTO modules:

- `reference_integration_transaction_cost_dto.py`
  - `TransactionCostCurvePageRequest`
  - `TransactionCostCurveRequest`
  - `TransactionCostCurvePoint`
  - `TransactionCostCurveSupportability`
  - `TransactionCostCurveResponse`
- `reference_integration_benchmark_market_series_dto.py`
  - `BenchmarkMarketSeriesRequest`
  - `SeriesPoint`
  - `ComponentSeriesResponse`
  - `BenchmarkMarketSeriesResponse`

The original `reference_integration_dto.py` keeps compatibility re-exports after shared paging
DTOs are defined, so existing services, routers, and tests continue importing from the existing
module path.

## Result

`reference_integration_dto.py` shrank from 3,637 SLOC to 3,264 SLOC and improved from `C (0.00)`
to `C (1.33)` under Radon maintainability. The extracted transaction-cost DTO module reports
`A (37.79)` and the extracted benchmark market-series DTO module reports `A (38.91)`. The moved
validator logic now sits behind named normalization helpers, reducing the moved C-ranked
transaction-cost request validator to B-ranked helper complexity. `reference_integration_dto.py`
remains an active C-ranked hotspot and needs additional DTO-family extractions.

## Evidence

- `python -m pytest tests\unit\services\query_service\dtos\test_reference_integration_dto.py tests\unit\services\query_service\services\test_transaction_cost_curve.py tests\unit\services\query_service\services\test_benchmark_market_series.py -q`
  => 53 passed
- `python -m pytest tests\integration\services\query_control_plane_service\test_control_plane_app.py -q`
  => 39 passed
- `python -m ruff check src\services\query_service\app\dtos\reference_integration_dto.py src\services\query_service\app\dtos\reference_integration_transaction_cost_dto.py src\services\query_service\app\dtos\reference_integration_benchmark_market_series_dto.py tests\unit\services\query_service\dtos\test_reference_integration_dto.py tests\unit\services\query_service\services\test_transaction_cost_curve.py tests\unit\services\query_service\services\test_benchmark_market_series.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\dtos\reference_integration_dto.py src\services\query_service\app\dtos\reference_integration_transaction_cost_dto.py src\services\query_service\app\dtos\reference_integration_benchmark_market_series_dto.py tests\unit\services\query_service\dtos\test_reference_integration_dto.py tests\unit\services\query_service\services\test_transaction_cost_curve.py tests\unit\services\query_service\services\test_benchmark_market_series.py`
  => 6 files already formatted
- `python -m radon raw src\services\query_service\app\dtos\reference_integration_dto.py src\services\query_service\app\dtos\reference_integration_transaction_cost_dto.py src\services\query_service\app\dtos\reference_integration_benchmark_market_series_dto.py`
  => `reference_integration_dto.py` 3,264 SLOC; transaction-cost DTO module 224 SLOC; benchmark market-series DTO module 216 SLOC
- `python -m radon mi src\services\query_service\app\dtos\reference_integration_dto.py src\services\query_service\app\dtos\reference_integration_transaction_cost_dto.py src\services\query_service\app\dtos\reference_integration_benchmark_market_series_dto.py -s`
  => main DTO `C (1.33)`, transaction-cost DTO `A (37.79)`, benchmark market-series DTO `A (38.91)`
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal DTO module boundary extraction that preserves
public API class names, OpenAPI component names, source-data product identity, validation behavior,
and operator-facing documentation truth.
