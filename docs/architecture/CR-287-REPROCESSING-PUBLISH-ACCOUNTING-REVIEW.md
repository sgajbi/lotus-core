# CR-287: Reprocessing publish accounting

Date: 2026-03-14

## Summary
- Hardened transaction reprocessing publish semantics so direct reprocessing requests and
  ingestion-job retry replay now share the same partial-failure and flush-timeout accounting.

## Problem
- `/reprocess/transactions` and the event-replay ingestion retry path published directly to Kafka
  with a local loop plus `flush(timeout=5)`.
- That left two real truth gaps:
  - mid-loop synchronous publish failure marked the whole request with all transaction ids instead
    of the real unpublished tail
  - `flush(...)` timeout results were ignored, so delivery-confirmation failure could slip through
    without becoming an explicit ingestion publish failure
- Those semantics were also duplicated across the write path and the replay path.

## Change
- Added `IngestionService.publish_reprocessing_requests(...)`.
- This shared helper now:
  - preserves the unpublished tail of transaction ids on mid-loop publish failure
  - treats positive `flush(timeout=5)` results as an explicit failure
  - increments Kafka publish metrics consistently
- Updated:
  - `src/services/ingestion_service/app/routers/reprocessing.py`
  - `src/services/event_replay_service/app/routers/ingestion_operations.py`
  to use the same helper.

## Why this matters
- Reprocessing is a runtime control path, not a best-effort convenience endpoint.
- Operators and replay flows now get one consistent failure model for:
  - direct reprocessing requests
  - ingestion-job retry replay of reprocessing requests
- That reduces drift and makes failure evidence more trustworthy.

## Evidence
- Unit proofs:
  - `tests/unit/services/ingestion_service/services/test_ingestion_service.py`
  - proves:
    - unpublished-tail reporting on partial reprocessing publish failure
    - explicit failure on flush timeout
- Integration proof:
  - `tests/integration/services/ingestion_service/test_ingestion_routers.py`
  - proves failed reprocessing jobs store only the remaining unpublished transaction ids after a
    mid-loop publish failure

## Validation
- `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_service.py tests/integration/services/ingestion_service/test_ingestion_routers.py -q`
- `python -m ruff check src/services/ingestion_service/app/services/ingestion_service.py src/services/ingestion_service/app/routers/reprocessing.py src/services/event_replay_service/app/routers/ingestion_operations.py tests/unit/services/ingestion_service/services/test_ingestion_service.py tests/integration/services/ingestion_service/test_ingestion_routers.py`

## Follow-up
- If we want to go further later, the next meaningful step is richer replay audit detail for flush
  timeout outcomes so operations can distinguish:
  - synchronous publish failure
  - callback-less delivery uncertainty
