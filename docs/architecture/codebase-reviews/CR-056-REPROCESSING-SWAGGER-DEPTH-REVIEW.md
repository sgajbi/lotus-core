# CR-056 Reprocessing Swagger Depth Review

## Scope
- Reprocessing router and shared ingestion acknowledgment / reprocessing DTOs

## Findings
- The reprocessing endpoint already had the right business description, but lacked explicit operational error examples.
- The shared `ReprocessingRequest` schema was minimal and the acknowledgment components relied on descriptions without explicit required-field declarations in the field definitions.

## Actions Taken
- Added explicit examples to `ReprocessingRequest.transaction_ids`.
- Added explicit required field markers on shared ingestion acknowledgment DTO fields.
- Added `409`, `429`, and `503` response examples to the reprocessing router.
- Added an OpenAPI integration assertion to lock the richer reprocessing and acknowledgment contract in place.

## Follow-up
- Continue the write-plane Swagger pass on the next weakest ingestion router or shared ingestion DTO surface.

## Evidence
- `src/services/ingestion_service/app/DTOs/ingestion_ack_dto.py`
- `src/services/ingestion_service/app/DTOs/reprocessing_dto.py`
- `src/services/ingestion_service/app/routers/reprocessing.py`
- `tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
