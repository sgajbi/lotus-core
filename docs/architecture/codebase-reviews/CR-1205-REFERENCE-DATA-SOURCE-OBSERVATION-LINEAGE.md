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

## 2026-08-14 Follow-Up Tranche

- Reused the same contract for 11 ordinary reference families that had duplicated the identical
  optional lineage shape: mandate bindings, model definitions and targets, instrument eligibility,
  client restrictions, sustainability preferences, tax profiles and rule sets, income-needs
  schedules, liquidity reserves, and planned withdrawals.
- Removed the duplicate field declarations while retaining canonical serialization and legacy
  `source_vendor`/`source_timestamp` input aliases.
- Changed the shared upsert boundary so an omitted/null source identity or observation value cannot
  erase existing `source_system`, `source_vendor`, `source_record_id`, `observed_at`, or
  `source_timestamp` authority. Ordinary nullable business fields keep their existing overwrite
  semantics, and an incoming populated lineage value still replaces the previous value.
- Focused validation: 119 DTO, registry, and persistence tests passed; Ruff and diff checks passed.

The registry explicitly declares every lineage field required, optional, or not applicable across
all 25 reference-data families. Benchmark assignment keeps its processing timestamp separate from
source observation; cash-account and look-through families truthfully declare unavailable
observation/quality fields rather than fabricating authority. Source-batch identity remains an
envelope-level design and is not invented per record.

Portfolio party-role assignments declare `source_system`, `source_record_id`, and `observed_at` as
required, matching their strict request DTO. Their governed quality status and assignment version
retain their documented defaults, so the registry declares those two fields optional rather than
misstating the endpoint contract.

## 2026-08-14 Query And Validation Closure

- Shared validation now rejects a supplied `observed_at` without an explicit timezone offset under
  stable code `INVALID_OBSERVED_AT`; omission remains valid for families whose registry policy
  declares observation time optional.
- A supplied `quality_status` must be a non-blank string before normalization. Omission alone uses
  the documented `accepted` default; explicit null, boolean, numeric, object, and list values fail
  under stable code `INVALID_QUALITY_STATUS` instead of being promoted or stringified.
- Query records now publish canonical `source_system`, `source_record_id`, `observed_at`, and
  `quality_status` for index price/return, benchmark return, risk-free, classification taxonomy,
  client restriction, sustainability preference, client tax profile/rule, income need, liquidity
  reserve, planned withdrawal, model target, and instrument-eligibility evidence.
- SQL adapters retain stored source system and quality evidence through persistence-independent
  domain records. Missing instrument eligibility explicitly returns null source identity/time and
  `MISSING` quality; it does not fabricate upstream authority.
- Existing benchmark and index definition products retain their versioned legacy
  `source_vendor`/`source_timestamp` response properties for downstream compatibility; their
  source evidence was already preserved rather than discarded. Canonical naming applies to new
  and migrated contracts until a separately versioned removal is downstream-safe.

Closure validation: 14 initial query-lineage tests, 49 client/DPM application and adapter tests,
and the combined 134-test DTO/query regression slice passed. Ruff, diff checks,
`make openapi-gate`, and `make api-vocabulary-gate` passed. The API vocabulary was regenerated.
No database migration, route, topic, partition, dependency, or runtime-topology change was needed.
