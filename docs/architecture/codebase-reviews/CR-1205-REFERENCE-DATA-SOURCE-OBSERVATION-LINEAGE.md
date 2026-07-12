# CR-1205 Reference-Data Source Observation Lineage

Date: 2026-06-30

## Objective

Start fixing GitHub issue #557 by standardizing source-observation lineage for benchmark, index,
risk-free, and classification reference-data ingestion DTOs without breaking existing persistence
columns or legacy payloads.

## Change

- Added shared `SourceObservationLineage` DTO fields for `source_system`, `source_record_id`,
  `observed_at`, and normalized `quality_status`.
- Applied the shared lineage contract to benchmark definitions, benchmark compositions, benchmark
  return series, index definitions, index price/return series, risk-free series, and classification
  taxonomy records.
- Kept legacy input aliases `source_vendor` and `source_timestamp` accepted for compatibility.
- Added a reference-data ingestion storage mapper that translates canonical DTO dumps back to the
  existing legacy database columns `source_vendor` and `source_timestamp`.

## Expected Improvement

Reference-data ingestion now has one reusable source-observation pattern for market/reference
families while preserving downstream and storage compatibility. OpenAPI schemas expose canonical
`source_system` and `observed_at` fields for the newly migrated families, and legacy callers can keep
submitting `source_vendor` and `source_timestamp` during transition.

## Validation

- `python -m pytest tests/unit/services/ingestion_service/test_reference_data_dto.py tests/unit/services/ingestion_service/test_reference_data_ingestion_service.py -q` -> 72 passed.
- Scoped `python -m ruff check ...` -> passed.
- Scoped `python -m ruff format --check ...` -> passed.
- `make openapi-gate` -> passed.
- `make api-vocabulary-gate` -> passed.
- `make typecheck` -> passed with no issues in 50 source files.
- `make quality-wiki-docs-gate` -> passed.
- `git diff --check` -> passed.
- `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` -> failed on known published-wiki drift for `Data-Models.md`, `Event-Replay-Service.md`, `Financial-Reconciliation.md`, `Ingestion-Service.md`, `Mesh-Data-Products.md`, `Operations-Runbook.md`, `Outbox-Events.md`, and `Validation-and-CI.md`.

## Compatibility

No route path, request family name, database table, database column, upsert conflict key, or response
shape changed. The intentional additive API-contract change is that migrated ingestion DTO schemas
now present canonical source-observation fields while still accepting the previous legacy field names
as input aliases.

## Documentation

Updated the codebase review ledger, quality scorecard, refactor health report, repository
engineering context, and RFC-0083 ingestion source-lineage target model. No repo-local wiki page
changed because this slice does not add an operator command or runbook; OpenAPI remains the
published API contract surface for the DTO field names.
