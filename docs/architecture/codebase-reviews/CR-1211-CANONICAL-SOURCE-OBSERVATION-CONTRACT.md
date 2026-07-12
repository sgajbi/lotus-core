# CR-1211: Canonical Source Observation Contract

Date: 2026-06-30

## Objective

Keep reference-data ingestion public contracts aligned to RFC-0083 temporal vocabulary while
preserving legacy source payload compatibility.

## Change

- Recorded the focused reference-data DTO families as migrated from public `source_timestamp`
  fields to canonical `observed_at` via shared `SourceObservationLineage`.
- Preserved legacy input compatibility through the existing `source_timestamp` validation alias.
- Kept persistence mapping to existing database `source_timestamp` columns unchanged.
- Updated OpenAPI and router integration assertions to verify canonical API fields and expanded
  DLQ/replay diagnostics.
- Promoted `runtime_settings.py` as an approved typed settings module in the config access guard.

## Compatibility

Legacy clients may still submit `source_timestamp`; normalized API/application records expose
`observed_at`. Database column names and persistence-service mapping remain unchanged.

## Validation

- `make lint`
- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py tests/integration/services/ingestion_service/test_ingestion_routers.py tests/unit/scripts/test_source_contract_guards.py tests/unit/scripts/test_temporal_vocabulary_guard.py tests/unit/services/ingestion_service/test_reference_data_dto.py -q`
- `git diff --check`

No wiki update required; this records repository-local API governance truth and tests, not an
operator runbook change.
