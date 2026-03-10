# CR-066 Write-Plane Acknowledgement Schema Swagger Review

## Scope

- `src/services/ingestion_service/app/DTOs/ingestion_ack_dto.py`
- `src/services/ingestion_service/app/DTOs/reprocessing_dto.py`
- `tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py`

## Findings

- The large write-plane DTO families were already materially stronger after CR-054 through CR-065.
- The smaller shared acknowledgement and replay-request DTOs were still acceptable, but their wording lagged behind the newer standard for operational API contracts.

## Actions taken

- Tightened the idempotency-key wording in `IngestionAcceptedResponse`.
- Tightened the `job_id` description in `BatchIngestionAcceptedResponse` so it reflects polling, replay, and operational support use.
- Tightened the `transaction_ids` description in `ReprocessingRequest` to make the canonical replay contract explicit.
- Added an ingestion app OpenAPI assertion to lock those shared contract descriptions in place.

## Result

- The shared acknowledgement and replay-request DTOs now align with the stronger operational language used elsewhere in the write plane.

## Evidence

- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py -q`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
