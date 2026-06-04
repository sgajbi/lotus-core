# CR-960: Reference Data Client Preference DTO Boundary

Date: 2026-06-05

## Scope

Move client restriction and sustainability preference DTO records plus their ingestion request
wrappers into a dedicated client preference DTO module without changing request fields, validation
semantics, schema names, router imports, or public compatibility imports from `reference_data_dto.py`.

## Finding

`reference_data_dto.py` remained a C-ranked maintainability hotspot after CR-959. Client
restriction and sustainability preference records were cohesive suitability/preference contracts,
but still lived inline with unrelated income-needs, liquidity, instrument eligibility, and
model-portfolio DTO families.

## Action

Added `reference_data_client_preference_dto.py` to own:

- `ClientRestrictionProfileRecord`
- `SustainabilityPreferenceProfileRecord`
- `ClientRestrictionProfileIngestionRequest`
- `SustainabilityPreferenceProfileIngestionRequest`

Kept compatibility assignments from `reference_data_dto.py` so existing routers, tests, OpenAPI
schema names, and downstream imports continue to resolve through the original module.

## Result

`reference_data_dto.py` shrank from 1,511 SLOC to 1,376 SLOC and improved from `C (1.05)` to
`C (6.43)` under Radon maintainability. The extracted client preference DTO module reports
`A (32.04)` maintainability. `reference_data_dto.py` remains an active C-ranked hotspot because
instrument eligibility and model-portfolio DTO families still live inline.

## Evidence

- `python -m pytest tests\unit\services\ingestion_service\test_reference_data_dto.py -q`
  => 35 passed
- `python -m ruff check src\services\ingestion_service\app\DTOs\reference_data_dto.py src\services\ingestion_service\app\DTOs\reference_data_client_preference_dto.py src\services\ingestion_service\app\DTOs\reference_data_tax_dto.py tests\unit\services\ingestion_service\test_reference_data_dto.py`
  => all checks passed
- `python -m ruff format --check src\services\ingestion_service\app\DTOs\reference_data_dto.py src\services\ingestion_service\app\DTOs\reference_data_client_preference_dto.py src\services\ingestion_service\app\DTOs\reference_data_tax_dto.py tests\unit\services\ingestion_service\test_reference_data_dto.py`
  => 4 files already formatted
- `make monetary-float-guard`
  => passed
- `python -m radon raw src\services\ingestion_service\app\DTOs\reference_data_dto.py src\services\ingestion_service\app\DTOs\reference_data_client_preference_dto.py`
  => `reference_data_dto.py` 1,376 SLOC; `reference_data_client_preference_dto.py` 142 SLOC
- `python -m radon mi src\services\ingestion_service\app\DTOs\reference_data_dto.py src\services\ingestion_service\app\DTOs\reference_data_client_preference_dto.py src\services\ingestion_service\app\DTOs\reference_data_tax_dto.py -s`
  => `reference_data_dto.py` `C (6.43)`; `reference_data_client_preference_dto.py` `A (32.04)`; `reference_data_tax_dto.py` `A (29.60)`
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal DTO module boundary extraction that preserves
public request contracts, OpenAPI schema names, router behavior, and operator-facing documentation
truth.
