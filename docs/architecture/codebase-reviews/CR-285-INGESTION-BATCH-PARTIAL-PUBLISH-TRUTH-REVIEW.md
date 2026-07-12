# CR-285: Ingestion batch partial publish truth

Date: 2026-03-14

## Summary
- Hardened ingestion batch publish failures so runtime and operator evidence now reflect the
  full unpublished tail of a batch, not just the single record that threw first.

## Problem
- `IngestionService` batch publish loops raised `IngestionPublishError` with only the first
  failing key.
- In a mid-batch Kafka publish failure, earlier records may already have been published and
  later records were never attempted.
- The prior contract therefore under-described the real failure shape:
  - operators could not tell where the batch stopped
  - ingestion job failure history persisted only one key even when multiple records were left
    unpublished

## Change
- Extended `IngestionPublishError` with `published_record_count`.
- Added shared batch failure construction in `IngestionService` so batch publish methods now:
  - preserve the original failing key in the message
  - report how many earlier records were already published
  - include the full remaining unpublished tail in `failed_record_keys`
- Applied this to:
  - business dates
  - portfolios
  - transactions
  - instruments
  - market prices
  - fx rates
- Clarified the ingestion job failure DTO description so `failed_record_keys` explicitly covers
  records left unpublished after a mid-batch failure.

## Why this matters
- This is not atomic publish, and it does not pretend to be.
- It makes partial failure truthful.
- That is materially better for:
  - operator triage
  - replay targeting
  - ingestion-job failure diagnosis

## Evidence
- Unit proof:
  - `tests/unit/services/ingestion_service/services/test_ingestion_service.py`
  - proves a three-transaction batch that fails on the second publish reports:
    - `failed_record_keys == ["T2", "T3"]`
    - `published_record_count == 1`
- Integration proof:
  - `tests/integration/services/ingestion_service/test_ingestion_routers.py`
  - proves failure history for a real failed ingestion job stores the remaining unpublished tail
    of the batch, not just the first failing key

## Validation
- `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_service.py tests/integration/services/ingestion_service/test_ingestion_routers.py -q`
- `python -m ruff check src/services/ingestion_service/app/services/ingestion_service.py src/services/ingestion_service/app/DTOs/ingestion_job_dto.py tests/unit/services/ingestion_service/services/test_ingestion_service.py tests/integration/services/ingestion_service/test_ingestion_routers.py`

## Follow-up
- If we want to go further later, the next meaningful step would be explicit batch-progress
  telemetry or structured job failure metadata for:
  - published count before failure
  - remaining unpublished count
- That would be an incremental observability improvement, not a prerequisite for this fix.
