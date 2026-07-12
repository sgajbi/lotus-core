# CR-426: Source Data Product Security-ID Normalization

Date: 2026-05-28

## Scope

Query-service source data product reads for instrument eligibility, portfolio tax lots,
transaction-cost curves, and market-data coverage.

## Finding

Several bank-facing source data products normalized request identifiers but still filtered,
keyed, or reported supportability using raw persisted `security_id` values. Whitespace drift in
reference, lot-state, transaction, or price rows could therefore make available evidence look
missing, split one real security across multiple returned groups, or emit padded identifiers in
downstream product records.

That failure mode weakens DPM readiness, market-data coverage, tax-lot evidence, and transaction
cost supportability because downstream consumers could receive false incomplete states even when
the bank has the required source evidence.

## Change

Reused the shared query-service security identifier normalizer across the affected source data
product paths. Repository filters now compare trimmed persisted security identifiers for
instrument eligibility, latest market prices, portfolio tax lots, and transaction-cost evidence.
Integration-service response assembly now normalizes returned row keys and supportability
missing-list comparisons, and `InstrumentEligibilityBulkRequest` now rejects blank or duplicate
security identifiers after normalization.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py tests/unit/services/query_service/repositories/test_buy_state_repository.py tests/unit/services/query_service/repositories/test_transaction_repository.py -q`
3. `python -m pytest tests/unit/services/query_service/services -q`
4. `python -m pytest tests/unit/services/query_service/repositories -q`
5. `python -m ruff check src/services/query_service/app/dtos/reference_integration_dto.py src/services/query_service/app/repositories/reference_data_repository.py src/services/query_service/app/repositories/buy_state_repository.py src/services/query_service/app/repositories/transaction_repository.py src/services/query_service/app/services/integration_service.py tests/unit/services/query_service/services/test_integration_service.py tests/unit/services/query_service/repositories/test_reference_data_repository.py tests/unit/services/query_service/repositories/test_buy_state_repository.py tests/unit/services/query_service/repositories/test_transaction_repository.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a
source-data-product correctness slice that prevents false missing evidence and padded identifiers
from propagating into DPM readiness, tax-lot, transaction-cost, and market-data supportability.
