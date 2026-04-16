# RFC-0083 Endpoint Consolidation Disposition

This document records the RFC-0083 Slice 8 endpoint watchlist disposition for `lotus-core`.

This slice changes OpenAPI metadata for selected pre-live convenience routes, but it does not remove
runtime handlers, persistence, DTOs, or response shapes. Route removal is deferred until affected
consumers are migrated to named source-data products and the platform evidence proves no active
surface depends on the old route shape.

## Consolidation Principle

`lotus-core` should expose durable source-data products, not consumer-specific convenience shapes.

When a route still has tested local callers or likely downstream integration value, the safe pre-live
move is:

1. mark the route as deprecated in OpenAPI,
2. name the target source-data product in the route description,
3. keep the route family registry stable,
4. require consumer migration evidence before removal.

## Deprecated Convenience Routes

| Route | Current family | Target product | Disposition |
| --- | --- | --- | --- |
| `POST /reporting/income-summary/query` | Operational Read | `TransactionLedgerWindow` | Deprecated in OpenAPI; current internal downstream scans show no active direct consumer, but keep handler until merged or external consumer truth allows retirement |
| `POST /reporting/activity-summary/query` | Operational Read | `TransactionLedgerWindow` | Deprecated in OpenAPI; current internal downstream scans show no active direct consumer, but keep handler until merged or external consumer truth allows retirement |

These routes remain operational reads while present. They must not absorb report composition,
performance interpretation, or risk interpretation.

## Kept Watchlist Routes

| Route family | Disposition | Guardrail |
| --- | --- | --- |
| `POST /reporting/assets-under-management/query` | Keep | Portfolio source summary; do not add narrative/report-generation behavior |
| `POST /reporting/asset-allocation/query` | Keep | Core-held allocation source truth only |
| `POST /reporting/portfolio-summary/query` | Keep | Source summary only; no analytics narrative |
| `GET /portfolios/{portfolio_id}/cashflow-projection` | Keep | Core-derived cashflow state only; no performance forecasting |
| `GET /simulation-sessions/{session_id}/projected-summary` | Keep | Deterministic projected state only; no advisory recommendation logic |
| `POST /integration/advisory/proposals/simulate-execution` | Keep | Core execution projection only; suitability and recommendation logic stay in `lotus-advise` |
| `POST /integration/instruments/enrichment-bulk` | Keep | Instrument/reference source data only; no advisory suitability enrichment |
| benchmark/index/risk-free integration routes | Keep | Analytics-safe source-data products with lineage, paging, and quality metadata |

## Removal Preconditions

A deprecated route may be removed only when:

1. the replacement source-data product route or DTO is implemented,
2. affected repo tests in `lotus-gateway`, `lotus-report`, `lotus-risk`, `lotus-performance`, and
   any other consumer are updated where applicable,
3. RFC-0067 no-alias governance is preserved,
4. the route contract-family registry is updated in the same slice,
5. OpenAPI/vocabulary checks pass,
6. platform evidence is captured when gateway or Workbench behavior changes.

## Validation

Slice 8 validation is:

1. `python -m pytest tests/integration/services/query_service/test_main_app.py -q`,
2. `python -m ruff check src/services/query_service/app/routers/reporting.py tests/integration/services/query_service/test_main_app.py --ignore E501,I001`,
3. `python -m ruff format --check src/services/query_service/app/routers/reporting.py tests/integration/services/query_service/test_main_app.py`,
4. `make route-contract-family-guard`,
5. `make lint`,
6. `git diff --check`.
