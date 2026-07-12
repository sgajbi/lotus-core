# CR-447: Transaction Write-Boundary Currency Canonicalization

Date: 2026-05-28

## Scope

Transaction ingestion DTOs, shared transaction event validation, persistence-service transaction
upsert preparation, and shared currency-code normalization support.

## Finding

Transaction currency fields are core calculation inputs for cost, cash, valuation, FX, tax,
analytics, and reporting. The write path accepted transaction currency values as raw caller text,
including required trade/ledger currencies and optional FX-pair, bought/sold, and synthetic-flow
currencies. Padded or lower-case values could enter Kafka and persistence, creating avoidable
non-canonical transaction economics and forcing downstream calculation consumers to defend against
source formatting drift.

## Change

Extended shared portfolio-common currency-code support with `normalize_optional_currency_code(...)`
and reused it at transaction write boundaries:

1. ingestion `Transaction` DTO validation before Kafka payload construction,
2. shared `TransactionEvent` validation before persistence processing,
3. persistence `TransactionDBRepository.create_or_update_transaction(...)` proof that canonical
   values are what reach database model construction.

Canonicalized fields:

1. `trade_currency`
2. `currency`
3. `pair_base_currency`
4. `pair_quote_currency`
5. `buy_currency`
6. `sell_currency`
7. `synthetic_flow_currency`

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_currency_codes.py tests/unit/services/persistence_service/repositories/test_transaction_db_repository.py -q`
2. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q -k "ingest_transactions_endpoint"`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/currency_codes.py src/libs/portfolio-common/portfolio_common/events.py src/services/ingestion_service/app/DTOs/transaction_dto.py tests/unit/libs/portfolio-common/test_currency_codes.py tests/unit/services/persistence_service/repositories/test_transaction_db_repository.py tests/integration/services/ingestion_service/test_ingestion_routers.py`
4. `python -m pytest tests/unit/libs/portfolio-common -q`
5. `python -m pytest tests/unit/services/persistence_service -q`
6. `python -m pytest tests/unit/services/ingestion_service/services -q`
7. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q`
8. `git diff --check`

Results:

1. Focused currency/persistence pytest: `11 passed`
2. Focused ingestion router pytest: `2 passed, 205 deselected`
3. Touched-surface ruff: passed
4. Portfolio-common unit pack: `334 passed`
5. Persistence-service unit pack: `13 passed`
6. Ingestion-service unit service pack: `39 passed`
7. Ingestion router integration pack: `207 passed`
8. Diff hygiene: passed

## Closure

Status: Hardened.

No route, OpenAPI schema shape, wiki source, or platform contract change was required. The
ingestion API behavior is intentionally stricter: transaction currency values are canonicalized
when possible and invalid non-three-letter values are rejected before publication.
