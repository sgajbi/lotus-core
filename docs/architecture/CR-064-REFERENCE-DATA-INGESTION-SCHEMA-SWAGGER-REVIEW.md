# CR-064 Reference Data Ingestion Schema Swagger Review

## Scope

- `src/services/ingestion_service/app/DTOs/reference_data_dto.py`
- `tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py`

## Findings

- The reference-data router layer was already operationally well documented.
- The weaker part was the shared component-schema layer:
  - request wrappers still had thin collection-field descriptions
  - several provenance timestamps lacked strong examples
  - schema-first clients could inspect the endpoints but still lacked rich reusable examples for catalog and time-series ingestion payloads

## Actions taken

- Tightened reusable provenance-field descriptions/examples for reference-data records.
- Added described, example-backed request-wrapper collection fields for:
  - benchmark assignments
  - benchmark definitions
  - benchmark compositions
  - index definitions
  - index price series
  - index return series
  - benchmark return series
  - risk-free series
  - classification taxonomy
- Added ingestion app OpenAPI assertions to lock the richer shared-schema behavior in place.

## Result

- The reference-data ingestion schemas now read as first-class reusable contracts instead of thin wrappers around already-strong router definitions.

## Evidence

- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py -q`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
