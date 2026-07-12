# CR-072 Empty Transaction Batch Contract Review

## Scope
Resolve the regression where `POST /ingest/transactions` rejected an empty transaction list with `422`, while the API contract and E2E expectation treat an empty batch as a valid no-op submission.

## Findings
- `TransactionIngestionRequest.transactions` still had `min_length=1`.
- The publish path itself already handled an empty list safely, so the rejection happened purely at request validation.
- This created a contract mismatch between the API surface and the implementation.

## Changes
1. Removed the `min_length=1` constraint from `TransactionIngestionRequest.transactions`.
2. Updated the schema description/examples to make empty-batch semantics explicit.
3. Added direct ingestion router coverage proving an empty transaction batch returns `202` and does not publish Kafka messages.
4. Updated the ingestion OpenAPI contract test to match the new example set.

## Validation
- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q -k "ingest_transactions_endpoint"`
- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py -q`
- `python -m pytest tests/e2e/test_ingestion_service_api.py -q -x`
- `python -m ruff check src/services/ingestion_service/app/DTOs/transaction_dto.py tests/integration/services/ingestion_service/test_ingestion_routers.py tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py tests/e2e/test_ingestion_service_api.py`

## Residual Risk
- None for the empty-batch path. The behavior is now directly covered below E2E and aligned with the API contract.
