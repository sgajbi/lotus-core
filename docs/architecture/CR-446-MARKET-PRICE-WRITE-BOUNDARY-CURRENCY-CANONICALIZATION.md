# CR-446: Market Price Write-Boundary Currency Canonicalization

Date: 2026-05-28

## Scope

Market-price ingestion DTOs, shared raw/persisted market-price event validation, persistence-service
market-price upsert preparation, query-service currency-normalizer compatibility, and the unit
warning-gate test module naming fix required after the FX write-boundary slice.

## Finding

Market-price currency is a source-owned calculation input for valuation, reporting, analytics, and
portfolio state. The write path accepted market-price currency values as raw caller text, so padded
or lower-case currency codes could enter Kafka, persistence, and downstream persisted-event
payloads. That creates avoidable non-canonical data-product keys and forces defensive cleanup in
calculation consumers.

## Change

Reused the shared portfolio-common currency-code normalizer for market-price write boundaries:

1. ingestion `MarketPrice` DTO validation before Kafka payload construction,
2. shared `MarketPriceEvent` validation before persistence processing,
3. shared `MarketPricePersistedEvent` validation before outbox payload publication,
4. query-service repository `normalize_currency_code(...)` compatibility now delegates to the
   shared portfolio-common normalizer,
5. renamed the persistence FX-rate repository test to a unique basename so the CI warning gate can
   collect it beside the query-service FX-rate repository test without pytest import-file mismatch.

Added tests proving padded market-price currency input is published and persisted as canonical
`USD`.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_currency_codes.py tests/unit/services/persistence_service/repositories/test_market_price_repository.py -q`
2. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q -k "ingest_market_prices_endpoint"`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/events.py src/services/ingestion_service/app/DTOs/market_price_dto.py src/services/query_service/app/repositories/currency_codes.py tests/unit/libs/portfolio-common/test_currency_codes.py tests/unit/services/persistence_service/repositories/test_market_price_repository.py tests/integration/services/ingestion_service/test_ingestion_routers.py`
4. `python -m pytest tests/unit/libs/portfolio-common -q`
5. `python -m pytest tests/unit/services/persistence_service -q`
6. `python -m pytest tests/unit/services/ingestion_service/services -q`
7. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q`
8. `python scripts/warning_budget_gate.py --suite unit --max-warnings 0 --quiet`

Results:

1. Focused currency/persistence pytest: `9 passed`
2. Focused ingestion router pytest: `1 passed, 206 deselected`
3. Touched-surface ruff: passed
4. Portfolio-common unit pack: `332 passed`
5. Persistence-service unit pack: `12 passed`
6. Ingestion-service unit service pack: `39 passed`
7. Ingestion router integration pack: `207 passed`
8. Unit warning gate: `2238 passed, 9 deselected`; `warnings=0`

## Closure

Status: Hardened.

No route, OpenAPI schema shape, wiki source, or platform contract change was required. The
ingestion API behavior is intentionally stricter: market-price currency values are canonicalized
when possible and invalid non-three-letter values are rejected before publication.
