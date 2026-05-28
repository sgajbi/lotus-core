# CR-448: Instrument Write-Boundary Currency Canonicalization

Date: 2026-05-28

## Scope

Instrument ingestion DTOs, shared instrument event validation, and persistence-service instrument
upsert preparation.

## Finding

Instrument currency fields are source-owned calculation inputs for valuation, allocation,
eligibility, liquidity, analytics, reporting, and FX contract interpretation. The write path
accepted instrument currency values as raw caller text, including instrument trading/settlement
currency and optional FX-pair bought/sold currencies. Padded or lower-case values could enter Kafka
and persistence, creating avoidable non-canonical instrument master data.

## Change

Reused the shared portfolio-common currency-code normalizer at instrument write boundaries:

1. ingestion `Instrument` DTO validation before Kafka payload construction,
2. shared `InstrumentEvent` validation before persistence processing,
3. persistence `InstrumentRepository.create_or_update_instrument(...)` proof that canonical values
   reach database model construction.

Canonicalized fields:

1. `currency`
2. `pair_base_currency`
3. `pair_quote_currency`
4. `buy_currency`
5. `sell_currency`

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_currency_codes.py tests/unit/services/persistence_service/repositories/test_instrument_repository.py -q`
2. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q -k "ingest_instruments_endpoint"`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/events.py src/services/ingestion_service/app/DTOs/instrument_dto.py tests/unit/libs/portfolio-common/test_currency_codes.py tests/unit/services/persistence_service/repositories/test_instrument_repository.py tests/integration/services/ingestion_service/test_ingestion_routers.py`
4. `python -m pytest tests/unit/libs/portfolio-common -q`
5. `python -m pytest tests/unit/services/persistence_service -q`
6. `python -m pytest tests/unit/services/ingestion_service/services -q`
7. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q`
8. `git diff --check`

Results:

1. Focused currency/persistence pytest: `12 passed`
2. Focused ingestion router pytest: `1 passed, 206 deselected`
3. Touched-surface ruff: passed
4. Portfolio-common unit pack: `335 passed`
5. Persistence-service unit pack: `14 passed`
6. Ingestion-service unit service pack: `39 passed`
7. Ingestion router integration pack: `207 passed`
8. Diff hygiene: passed

## Closure

Status: Hardened.

No route, OpenAPI schema shape, wiki source, or platform contract change was required. The
ingestion API behavior is intentionally stricter: instrument currency values are canonicalized when
possible and invalid non-three-letter values are rejected before publication.
