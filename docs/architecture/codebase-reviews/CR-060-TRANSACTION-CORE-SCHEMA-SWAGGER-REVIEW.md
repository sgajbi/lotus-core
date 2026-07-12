# CR-060 Transaction Core Schema Swagger Review

## Scope

- `src/services/ingestion_service/app/DTOs/transaction_dto.py`
- `tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py`

## Findings

- `transaction_dto.py` already carried many examples, but the most important core ledger fields still lacked strong field-level descriptions.
- The wrapper request model was also too thin for schema-first clients.
- This was the largest remaining active ingestion schema surface, so the highest-value first step was to harden the canonical core fields before taking the longer specialized tail.

## Actions taken

- Added field-level descriptions to the core transaction ledger fields:
  - identifiers
  - type/date
  - quantity/price/gross amount
  - currencies
  - trade fee
  - settlement date
  - created-at lineage timestamp
- Added a described, example-backed `transactions` collection field to `TransactionIngestionRequest`
- Added ingestion app OpenAPI assertions to lock the richer core-schema contract in place

## Result

- The highest-visibility part of the transaction write-plane schema now matches the rest of the hardened ingestion surface much more closely.

## Evidence

- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py -q`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
