# CR-952: Reference Integration DPM Eligibility DTO Boundaries

Date: 2026-06-05

## Scope

Move the instrument eligibility and DPM source-readiness DTO families out of
`reference_integration_dto.py` without changing public DTO class names, router imports, service
imports, OpenAPI component names, validation behavior, request/response fields, examples, or
source-data product identity metadata.

## Finding

`reference_integration_dto.py` still owned instrument eligibility request validation, eligibility
records, eligibility supportability, DPM readiness request validation, family readiness rows,
readiness supportability, and readiness response DTOs inline. After CR-951 the module was close to
the maintainability threshold but remained an active C-ranked hotspot.

## Action

Extracted `reference_integration_instrument_eligibility_dto.py` with:

- `InstrumentEligibilityBulkRequest`
- `InstrumentEligibilityRecord`
- `InstrumentEligibilitySupportability`
- `InstrumentEligibilityBulkResponse`

Extracted `reference_integration_dpm_source_readiness_dto.py` with:

- `DpmSourceFamilyState`
- `DpmSourceReadinessRequest`
- `DpmSourceFamilyReadiness`
- `DpmSourceReadinessSupportability`
- `DpmSourceReadinessResponse`

The original `reference_integration_dto.py` keeps compatibility re-exports, preserving existing
service, router, and test imports. The moved request validators now delegate identifier
normalization to named helpers, while DPM readiness imports `MarketDataCurrencyPair` from the
market-data coverage DTO module.

## Result

`reference_integration_dto.py` shrank from 2,922 SLOC to 2,639 SLOC and improved from `C (6.70)`
to `B (11.49)` under Radon maintainability, removing it from the active non-generated C-ranked
source hotspot list. The extracted instrument eligibility DTO module reports `A (41.20)`, and the
extracted DPM source-readiness DTO module reports `A (42.75)`.

Active non-generated C-ranked source hotspots are now limited to ingestion source files:
`reference_data_dto.py` and `ingestion_job_service.py`.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_instrument_eligibility.py tests\unit\services\query_service\services\test_dpm_source_readiness.py -q`
  => 44 passed
- `python -m pytest tests\integration\services\query_control_plane_service\test_control_plane_app.py -q`
  => 39 passed
- `python -m ruff check src\services\query_service\app\dtos\reference_integration_dto.py src\services\query_service\app\dtos\reference_integration_instrument_eligibility_dto.py src\services\query_service\app\dtos\reference_integration_dpm_source_readiness_dto.py tests\unit\services\query_service\services\test_instrument_eligibility.py tests\unit\services\query_service\services\test_dpm_source_readiness.py tests\unit\services\query_service\services\test_integration_service.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\dtos\reference_integration_dto.py src\services\query_service\app\dtos\reference_integration_instrument_eligibility_dto.py src\services\query_service\app\dtos\reference_integration_dpm_source_readiness_dto.py tests\unit\services\query_service\services\test_instrument_eligibility.py tests\unit\services\query_service\services\test_dpm_source_readiness.py tests\unit\services\query_service\services\test_integration_service.py`
  => 6 files already formatted
- `python -m radon raw src\services\query_service\app\dtos\reference_integration_dto.py src\services\query_service\app\dtos\reference_integration_instrument_eligibility_dto.py src\services\query_service\app\dtos\reference_integration_dpm_source_readiness_dto.py`
  => `reference_integration_dto.py` 2,639 SLOC; instrument eligibility DTO module 139 SLOC; DPM
  source-readiness DTO module 180 SLOC
- `python -m radon mi src\services\query_service\app\dtos\reference_integration_dto.py src\services\query_service\app\dtos\reference_integration_instrument_eligibility_dto.py src\services\query_service\app\dtos\reference_integration_dpm_source_readiness_dto.py -s`
  => main DTO `B (11.49)`, instrument eligibility DTO `A (41.20)`, DPM source-readiness DTO
  `A (42.75)`
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal DTO module boundary extraction that preserves
public API class names, OpenAPI component names, source-data product identity, validation behavior,
and operator-facing documentation truth.
