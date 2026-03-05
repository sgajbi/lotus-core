# DIVIDEND Slice 5 - Query and Observability Supportability

## Scope
Slice 5 extends existing query/supportability surfaces for DIVIDEND linkage fields without adding dedicated endpoints.

## Implemented Changes
1. Existing transaction query response contract already includes:
 - `cash_entry_mode`
 - `external_cash_transaction_id`
2. Query tests now validate these fields are preserved end-to-end in:
 - router response serialization
 - service DTO mapping from database models
3. API governance checks were executed after DTO contract updates:
 - OpenAPI quality gate
 - API vocabulary inventory generation and validation
4. Cashflow consumer logs for DIVIDEND external mode include linkage metadata:
 - `transaction_id`
 - `external_cash_transaction_id`
 - `economic_event_id`
 - `linked_transaction_group_id`

## No Dedicated Endpoint Confirmation
DIVIDEND queryability is delivered by extending existing `/portfolios/{portfolio_id}/transactions` response fields. No DIVIDEND-specific endpoint was introduced.

## Test and Gate Evidence
1. `tests/integration/services/query_service/test_transactions_router.py`
2. `tests/unit/services/query_service/services/test_transaction_service.py`
3. `python scripts/openapi_quality_gate.py`
4. `python scripts/api_vocabulary_inventory.py --validate-only`
5. `python scripts/api_vocabulary_inventory.py --output docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json`
