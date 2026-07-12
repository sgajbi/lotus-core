# CR-453: Benchmark Definition Write-Boundary Currency Canonicalization

Date: 2026-05-28

## Scope

Benchmark definition reference-data ingestion DTOs, reference-data upsert preparation, and
route-level persistence behavior.

## Finding

Benchmark definitions anchor performance comparison, mandate-policy evidence, reporting
alignment, and model-governance workflows. `benchmark_currency` was accepted as raw caller text in
the reference-data write path, so padded or lower-case values could become authoritative benchmark
master data and create avoidable downstream normalization work in performance and advisory
products.

## Change

Reused the shared portfolio-common currency-code normalizer at benchmark definition write
boundaries:

1. `BenchmarkDefinitionRecord` validates and canonicalizes `benchmark_currency` before route
   handling,
2. `ReferenceDataIngestionService.upsert_benchmark_definitions(...)` canonicalizes direct service
   input before constructing the database upsert,
3. the full-contract benchmark definition route test now proves padded lower-case input persists
   as canonical `USD`.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/ingestion_service/test_reference_data_dto.py -q -k benchmark_definition_normalizes_benchmark_currency`
2. `python -m pytest tests/unit/services/ingestion_service/test_reference_data_ingestion_service.py -q -k "benchmark_definitions_normalizes_benchmark_currency or upsert_benchmark_definitions"`
3. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q -k ingest_benchmark_definitions_returns_ack_and_persists_full_contract`
4. `python -m ruff check src/services/ingestion_service/app/DTOs/reference_data_dto.py src/services/ingestion_service/app/services/reference_data_ingestion_service.py tests/unit/services/ingestion_service/test_reference_data_dto.py tests/unit/services/ingestion_service/test_reference_data_ingestion_service.py tests/integration/services/ingestion_service/test_ingestion_routers.py`
5. `python -m pytest tests/unit/services/ingestion_service -q`
6. `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -q`
7. `git diff --check`

Results:

1. Focused DTO pytest: `1 passed, 24 deselected`
2. Focused reference-data service pytest: `2 passed, 19 deselected`
3. Focused ingestion router pytest: `1 passed, 207 deselected`
4. Touched-surface ruff: passed
5. Ingestion-service unit pack: `102 passed`
6. Ingestion router integration pack: `208 passed`
7. Diff hygiene: passed

## Closure

Status: Hardened.

No route shape, database migration, wiki source, or platform contract change was required. The
ingestion API behavior is intentionally stricter: valid benchmark currency values are canonicalized
and invalid non-three-letter values are rejected before persistence.
