# CR-445: FX Rate Write-Boundary Currency Canonicalization

Date: 2026-05-28

## Scope

FX-rate ingestion DTOs, shared raw FX-rate event validation, and persistence-service FX-rate
upsert preparation.

## Finding

The query side now tolerates non-canonical persisted FX currency codes, but the write path still
accepted and published caller-supplied FX currency values as-is. Lower-case or padded currency
codes could therefore enter Kafka and persistence, creating avoidable duplicates, non-canonical
operator evidence, and slower defensive read queries.

That is a data-product quality risk because FX rates are a shared calculation input for valuation,
performance, reporting, analytics timeseries, and integration exports.

## Change

Added a shared portfolio-common currency-code normalizer that trims, uppercases, and enforces
three-letter ISO 4217-style currency codes. Applied it at both FX write boundaries:

1. ingestion `FxRate` DTO validation before Kafka publish key and payload construction,
2. shared `FxRateEvent` validation before persistence consumers and repositories process raw
   FX-rate events.

Added tests proving padded FX currency input is published and persisted as canonical `USD`, `SGD`,
`EUR`, and `USD` values, and invalid currency values fail validation before entering durable
calculation input state.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_currency_codes.py tests/unit/services/persistence_service/repositories/test_fx_rate_repository.py -q`
2. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q -k "ingest_fx_rates_endpoint"`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/currency_codes.py src/libs/portfolio-common/portfolio_common/events.py src/services/ingestion_service/app/DTOs/fx_rate_dto.py tests/unit/libs/portfolio-common/test_currency_codes.py tests/unit/services/persistence_service/repositories/test_fx_rate_repository.py tests/integration/services/ingestion_service/test_ingestion_routers.py`
4. `python -m pytest tests/unit/libs/portfolio-common -q`
5. `python -m pytest tests/unit/services/persistence_service -q`
6. `python -m pytest tests/unit/services/ingestion_service/services -q`
7. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q`

Results:

1. Focused currency/persistence pytest: `8 passed`
2. Focused ingestion router pytest: `1 passed, 206 deselected`
3. Touched-surface ruff: passed
4. Portfolio-common unit pack: `331 passed`
5. Persistence-service unit pack: `11 passed`
6. Ingestion-service unit service pack: `39 passed`
7. Ingestion router integration pack: `207 passed`

## Closure

Status: Hardened.

No route, OpenAPI schema shape, wiki source, or platform contract change was required. The
ingestion API behavior is intentionally stricter: FX currency codes are canonicalized when possible
and invalid non-three-letter values are rejected before publication.
