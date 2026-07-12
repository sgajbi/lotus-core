# CR-961: Reference Data Instrument Eligibility DTO Boundary

Date: 2026-06-05

## Scope

Move instrument eligibility profile DTO records and their ingestion request wrapper into a dedicated
instrument eligibility DTO module without changing request fields, validation semantics, schema
names, router imports, or public compatibility imports from `reference_data_dto.py`.

## Finding

`reference_data_dto.py` remained a C-ranked maintainability hotspot after CR-960. Instrument
eligibility records are DPM shelf/compliance contracts with bounded buy/sell supportability
validation, but still lived inline with model-portfolio, benchmark, income-needs, and liquidity DTO
families.

## Action

Added `reference_data_instrument_eligibility_dto.py` to own:

- `InstrumentEligibilityProfileRecord`
- `InstrumentEligibilityProfileIngestionRequest`

Kept compatibility assignments from `reference_data_dto.py` so existing routers, tests, OpenAPI
schema names, and downstream imports continue to resolve through the original module.

## Result

`reference_data_dto.py` shrank from 1,376 SLOC to 1,282 SLOC and improved from `C (6.43)` to
`B (9.31)` under Radon maintainability. The extracted instrument eligibility DTO module reports
`A (40.98)` maintainability. This removes `reference_data_dto.py` from the active non-generated
C-ranked source hotspot list.

## Evidence

- `python -m pytest tests\unit\services\ingestion_service\test_reference_data_dto.py -q`
  => 35 passed
- `python -m ruff check src\services\ingestion_service\app\DTOs\reference_data_dto.py src\services\ingestion_service\app\DTOs\reference_data_client_preference_dto.py src\services\ingestion_service\app\DTOs\reference_data_instrument_eligibility_dto.py src\services\ingestion_service\app\DTOs\reference_data_tax_dto.py tests\unit\services\ingestion_service\test_reference_data_dto.py`
  => all checks passed
- `python -m ruff format --check src\services\ingestion_service\app\DTOs\reference_data_dto.py src\services\ingestion_service\app\DTOs\reference_data_client_preference_dto.py src\services\ingestion_service\app\DTOs\reference_data_instrument_eligibility_dto.py src\services\ingestion_service\app\DTOs\reference_data_tax_dto.py tests\unit\services\ingestion_service\test_reference_data_dto.py`
  => 5 files already formatted
- `make monetary-float-guard`
  => passed
- `python -m radon raw src\services\ingestion_service\app\DTOs\reference_data_dto.py src\services\ingestion_service\app\DTOs\reference_data_instrument_eligibility_dto.py`
  => `reference_data_dto.py` 1,282 SLOC; `reference_data_instrument_eligibility_dto.py` 103 SLOC
- `python -m radon mi src\services\ingestion_service\app\DTOs\reference_data_dto.py src\services\ingestion_service\app\DTOs\reference_data_instrument_eligibility_dto.py src\services\ingestion_service\app\DTOs\reference_data_client_preference_dto.py src\services\ingestion_service\app\DTOs\reference_data_tax_dto.py -s`
  => `reference_data_dto.py` `B (9.31)`; extracted DTO modules all A-ranked
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal DTO module boundary extraction that preserves
public request contracts, OpenAPI schema names, router behavior, and operator-facing documentation
truth.
