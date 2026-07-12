# CR-454: Reference Market Series Write-Boundary Currency Canonicalization

Date: 2026-05-28

## Scope

Index definition, index price series, index return series, benchmark return series, and risk-free
series reference-data ingestion DTOs, upsert preparation, and route-level persistence behavior.

## Finding

Reference market data feeds benchmark construction, performance comparison, risk-free excess
return calculations, advisory evidence, and reporting alignment. `index_currency` and
`series_currency` fields were accepted as raw caller text in the reference-data write path, so
padded or lower-case values could become authoritative market-reference data and create avoidable
downstream normalization work in performance and advisory products.

## Change

Reused the shared portfolio-common currency-code normalizer across reference market-data write
boundaries:

1. `IndexDefinitionRecord` canonicalizes `index_currency` before route handling,
2. index price, index return, benchmark return, and risk-free series DTOs canonicalize
   `series_currency` before route handling,
3. `ReferenceDataIngestionService` now uses a shared `_normalize_currency_field(...)` helper for
   currency-bearing reference-data upserts, including earlier cash account, model portfolio, and
   benchmark definition paths,
4. full-contract route tests now prove padded lower-case market-reference currencies persist as
   canonical `USD`.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/ingestion_service/test_reference_data_dto.py -q -k "reference_market_series_records_normalize_currency or benchmark_definition_normalizes_benchmark_currency or model_portfolio_definition_normalizes_base_currency"`
2. `python -m pytest tests/unit/services/ingestion_service/test_reference_data_ingestion_service.py -q -k "reference_market_series_upserts_normalize_currency or upsert_indices or upsert_index_price_series or upsert_index_return_series or upsert_benchmark_return_series or upsert_risk_free_series"`
3. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q -k "ingest_indices_returns_ack_and_persists_full_contract or ingest_index_price_series_returns_ack_and_persists_full_contract or ingest_index_return_series_returns_ack_and_persists_full_contract or ingest_benchmark_return_series_returns_ack_and_persists_full_contract or ingest_risk_free_series_returns_ack_and_persists_full_contract"`
4. `python -m ruff check src/services/ingestion_service/app/DTOs/reference_data_dto.py src/services/ingestion_service/app/services/reference_data_ingestion_service.py tests/unit/services/ingestion_service/test_reference_data_dto.py tests/unit/services/ingestion_service/test_reference_data_ingestion_service.py tests/integration/services/ingestion_service/test_ingestion_routers.py`
5. `python -m pytest tests/unit/services/ingestion_service -q`
6. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q`
7. `git diff --check`

Results:

1. Focused DTO pytest: `7 passed, 23 deselected`
2. Focused reference-data service pytest: `10 passed, 16 deselected`
3. Focused ingestion router pytest: `5 passed, 203 deselected`
4. Touched-surface ruff: passed
5. Ingestion-service unit pack: `112 passed`
6. Ingestion router integration pack: `208 passed`
7. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. The
ingestion API behavior is intentionally stricter: valid index and market-reference series
currency values are canonicalized and invalid non-three-letter values are rejected before
persistence.
