# CR-059 Instrument Ingestion Schema Swagger Review

## Scope

- `src/services/ingestion_service/app/DTOs/instrument_dto.py`
- `tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py`

## Findings

- The instrument ingestion router had already been hardened at the operational response layer.
- The shared instrument component schema still looked like an early scaffold:
  - sparse field examples
  - weak descriptions on important issuer and FX-contract fields
  - request wrapper lacked a described example-backed collection field

## Actions taken

- Added field-level descriptions/examples across the live `Instrument` fields
- Added a described, example-backed `instruments` collection field to `InstrumentIngestionRequest`
- Added ingestion app OpenAPI assertions to lock the richer schema contract in place

## Result

- The instrument write-plane component schema now matches the surrounding router depth much more closely.

## Evidence

- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py -q`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
