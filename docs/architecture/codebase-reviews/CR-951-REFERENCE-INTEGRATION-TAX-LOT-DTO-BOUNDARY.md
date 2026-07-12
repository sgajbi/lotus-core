# CR-951: Reference Integration Tax Lot DTO Boundary

Date: 2026-06-05

## Scope

Move the portfolio tax-lot window DTO family out of `reference_integration_dto.py` without changing
public DTO class names, router imports, service imports, OpenAPI component names, validation
behavior, request/response fields, examples, or source-data product identity metadata.

## Finding

`reference_integration_dto.py` still owned the portfolio tax-lot page request, window request
validation, tax-lot record DTO, supportability DTO, and response DTO inline. This kept another DPM
source-data product contract family coupled to the broad shared reference integration DTO module.

## Action

Extracted `reference_integration_portfolio_tax_lot_dto.py` with:

- `PortfolioTaxLotPageRequest`
- `PortfolioTaxLotWindowRequest`
- `PortfolioTaxLotRecord`
- `PortfolioTaxLotWindowSupportability`
- `PortfolioTaxLotWindowResponse`

The original `reference_integration_dto.py` keeps compatibility re-exports after shared paging
DTOs are defined, preserving existing service, router, and test imports. The moved request
validator now delegates to a named security-id normalization helper.

## Result

`reference_integration_dto.py` shrank from 3,078 SLOC to 2,922 SLOC and improved from `C (4.62)`
to `C (6.70)` under Radon maintainability. The extracted portfolio tax-lot DTO module reports
`A (41.65)`. `reference_integration_dto.py` remains an active C-ranked hotspot, with remaining
B-ranked validator pressure concentrated in DPM source readiness and instrument eligibility DTO
families.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_portfolio_tax_lot_window.py tests\unit\services\query_service\services\test_dpm_source_readiness.py -q`
  => 52 passed
- `python -m pytest tests\integration\services\query_control_plane_service\test_control_plane_app.py -q`
  => 39 passed
- `python -m ruff check src\services\query_service\app\dtos\reference_integration_dto.py src\services\query_service\app\dtos\reference_integration_portfolio_tax_lot_dto.py tests\unit\services\query_service\services\test_portfolio_tax_lot_window.py tests\unit\services\query_service\services\test_dpm_source_readiness.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\dtos\reference_integration_dto.py src\services\query_service\app\dtos\reference_integration_portfolio_tax_lot_dto.py tests\unit\services\query_service\services\test_portfolio_tax_lot_window.py tests\unit\services\query_service\services\test_dpm_source_readiness.py`
  => 4 files already formatted
- `python -m radon raw src\services\query_service\app\dtos\reference_integration_dto.py src\services\query_service\app\dtos\reference_integration_portfolio_tax_lot_dto.py`
  => `reference_integration_dto.py` 2,922 SLOC; portfolio tax-lot DTO module 177 SLOC
- `python -m radon mi src\services\query_service\app\dtos\reference_integration_dto.py src\services\query_service\app\dtos\reference_integration_portfolio_tax_lot_dto.py -s`
  => main DTO `C (6.70)`, portfolio tax-lot DTO `A (41.65)`
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal DTO module boundary extraction that preserves
public API class names, OpenAPI component names, source-data product identity, validation behavior,
and operator-facing documentation truth.
