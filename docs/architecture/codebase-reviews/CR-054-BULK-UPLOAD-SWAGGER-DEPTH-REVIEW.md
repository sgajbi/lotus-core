# CR-054 Bulk Upload Swagger Depth Review

## Scope
- Ingestion bulk upload router and shared upload DTOs

## Findings
- The upload endpoints already exposed the correct basic contracts, but parameter descriptions and operational error examples were still thin.
- The shared upload DTOs also lacked field-level descriptions/examples, leaving Swagger more useful at the route level than at the reusable component level.

## Actions Taken
- Added field-level descriptions/examples to `UploadRowError`, `UploadPreviewResponse`, and `UploadCommitResponse`.
- Added upload router examples and richer parameter docs for:
  - `entity_type`
  - `sample_size`
  - `allow_partial`
- Added explicit `400`, `410`, `429`, and `503` response examples for the upload endpoints.
- Added an OpenAPI integration assertion to lock the richer upload contract in place.

## Follow-up
- Continue the write-plane Swagger pass on the next weakest ingestion router or shared ingestion DTO surface.

## Evidence
- `src/services/ingestion_service/app/DTOs/upload_dto.py`
- `src/services/ingestion_service/app/routers/uploads.py`
- `tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
