# CR-057 Business Date Shared Schema Swagger Review

## Scope

- `src/services/ingestion_service/app/DTOs/business_date_dto.py`
- `tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py`

## Findings

- The `business_dates` ingestion router had already been hardened at the operational response layer.
- The shared DTO schema was still weaker than the rest of the write plane:
  - field examples were missing
  - the request wrapper had no field-level description
  - Swagger users could see the route, but not a strong reusable component contract

## Actions taken

- Added field-level descriptions/examples to `BusinessDate`
- Added a described, example-backed `business_dates` collection field to `BusinessDateIngestionRequest`
- Added an ingestion app OpenAPI contract assertion to lock the richer shared-schema behavior in place

## Result

- The business-date write plane now has both:
  - operational router error-contract depth
  - shared component-schema depth

## Evidence

- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py -q`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
