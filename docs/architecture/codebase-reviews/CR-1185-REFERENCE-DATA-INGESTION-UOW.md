# CR-1185 Reference Data Ingestion Unit Of Work

Date: 2026-06-30

## Objective

Fix GitHub issue #668 by moving reference-data ingestion commit ownership out of the low-level
PostgreSQL upsert builder and into explicit application unit-of-work methods.

## Change

- Added `ReferenceDataUpsertOperation` as the explicit operation envelope for reference-data table
  upserts.
- Kept `_upsert_many(...)` as the staging helper that builds and executes the PostgreSQL
  `ON CONFLICT DO UPDATE` statement without committing.
- Added `_commit_upsert_many(...)` for existing single-table endpoint behavior.
- Added `upsert_source_batch(...)` so multiple reference-data table upserts can commit once or roll
  back together when a later operation fails.

## Expected Improvement

Reference-data ingestion now has a clear transaction boundary. Single-table endpoints keep their
existing success behavior, while future source-batch orchestration can stage multiple table updates
and preserve atomicity across the batch.

## Tests Added

- Source-batch success commits once after all staged table operations complete.
- Source-batch failure after an earlier staged table operation rolls back and does not commit.
- Existing endpoint delegation tests now assert delegation to the single-table unit-of-work wrapper.

## Validation Evidence

- `python -m pytest tests/unit/services/ingestion_service/test_reference_data_ingestion_service.py -q`
  passed with 33 tests.

## Downstream Compatibility

No route path, request DTO, response DTO, database schema, table, conflict key, update-column list,
normalization behavior, or successful single-table endpoint commit behavior changed. The intentional
internal behavior change is that source-batch orchestration can now own one commit across multiple
reference-data table upserts.

## Documentation And Wiki Decision

This architecture record, the codebase review ledger, and quality/refactor scorecards were updated.
No repo wiki update is required because no operator-facing command, published API contract, or
wiki-authored operating procedure changed.

## Remaining Follow-Up

- Wire a router/application source-batch endpoint only when the source-batch contract is approved.
- Add lineage/audit fields for any future multi-table batch envelope rather than inferring lineage
  from individual table records.
- Consider a broader transaction-boundary guard for ingestion helpers that execute SQL directly.
