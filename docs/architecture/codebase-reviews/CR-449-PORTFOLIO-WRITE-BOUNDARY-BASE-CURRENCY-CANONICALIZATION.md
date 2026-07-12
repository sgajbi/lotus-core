# CR-449: Portfolio Write-Boundary Base-Currency Canonicalization

Date: 2026-05-28

## Scope

Portfolio ingestion DTOs, shared portfolio event validation, and persistence-service portfolio
upsert preparation.

## Finding

Portfolio base currency is the authoritative aggregation currency for valuation, P&L, reporting,
FX readiness, cash, tax, analytics, and supportability evidence. The write path accepted
`base_currency` as raw caller text, so padded or lower-case values could enter Kafka and
persistence, creating avoidable non-canonical portfolio master data.

## Change

Reused the shared portfolio-common currency-code normalizer at portfolio write boundaries:

1. ingestion `Portfolio` DTO validation before Kafka payload construction,
2. shared `PortfolioEvent` validation before persistence processing,
3. existing persistence repository proof now confirms canonical base currency reaches database
   model construction.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_currency_codes.py tests/unit/services/persistence_service/repositories/test_persistence_portfolio_repository.py -q`
2. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q -k "ingest_portfolios_endpoint"`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/events.py src/services/ingestion_service/app/DTOs/portfolio_dto.py tests/unit/libs/portfolio-common/test_currency_codes.py tests/unit/services/persistence_service/repositories/test_persistence_portfolio_repository.py tests/integration/services/ingestion_service/test_ingestion_routers.py`
4. `python -m pytest tests/unit/libs/portfolio-common -q`
5. `python -m pytest tests/unit/services/persistence_service -q`
6. `python -m pytest tests/unit/services/ingestion_service/services -q`
7. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q`
8. `git diff --check`

Results:

1. Focused currency/persistence pytest: `13 passed`
2. Focused ingestion router pytest: `1 passed, 206 deselected`
3. Touched-surface ruff: passed
4. Portfolio-common unit pack: `336 passed`
5. Persistence-service unit pack: `14 passed`
6. Ingestion-service unit service pack: `39 passed`
7. Ingestion router integration pack: `207 passed`
8. Diff hygiene: passed

## Closure

Status: Hardened.

No route, OpenAPI schema shape, wiki source, or platform contract change was required. The
ingestion API behavior is intentionally stricter: portfolio base currency is canonicalized when
possible and invalid non-three-letter values are rejected before publication.
