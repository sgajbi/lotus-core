# CR-294: Preserve ingress truth after queue bookkeeping failure

Date: 2026-03-14

## Summary
- Hardened ingestion write routers so a successful publish or durable persist is no longer flattened
  into job status `failed` when only the later `mark_queued(...)` bookkeeping step fails.

## Problem
- Batch ingestion routers used one broad `try/except` across:
  - the real work
    - Kafka publish for write-ingress endpoints
    - durable persist for reference-data endpoints
  - then `ingestion_job_service.mark_queued(job_id)`
- If the real work succeeded but `mark_queued(...)` failed, routers still:
  - called `mark_failed(...)`
  - returned an error path that implied the publish/persist itself failed
- That misreported durable truth and could leave operators treating an already-emitted request as if it
  never happened.

## Change
- Added `IngestionJobService.record_failure_observation(...)` to persist a failure row without flipping
  the job into terminal `failed` status.
- Added shared router helper:
  - `raise_post_publish_bookkeeping_failure(...)`
- Updated write-ingress routers to split execution into two phases:
  - publish/persist phase
  - queue-bookkeeping phase
- If the publish/persist phase fails:
  - existing `mark_failed(...)` behavior stays unchanged
- If `mark_queued(...)` fails after the real work already succeeded:
  - we record a non-terminal failure observation with phase:
    - `queue_bookkeeping`
    - `persist_bookkeeping` for reference data
  - return explicit HTTP 500 with code:
    - `INGESTION_JOB_BOOKKEEPING_FAILED`
  - do not falsely mark the job itself as `failed`

## Why this matters
- Operators need to distinguish:
  - work that never got out
  - work that got out but whose local bookkeeping failed afterward
- This keeps ingress job state closer to durable truth and avoids false failure classification after
  successful publish/persist.

## Evidence
- Integration proof:
  - `tests/integration/services/ingestion_service/test_ingestion_routers.py`
  - proves a transaction ingest request with forced `mark_queued(...)` failure:
    - returns `INGESTION_JOB_BOOKKEEPING_FAILED`
    - leaves the job in non-terminal `accepted`
    - records failure history with `failure_phase="queue_bookkeeping"`
- Unit proofs:
  - `tests/unit/services/ingestion_service/services/test_ingestion_job_service_state_transitions.py`
  - proves `record_failure_observation(...)` records failure rows without issuing a job status update
  - `tests/unit/services/ingestion_service/routers/test_job_bookkeeping.py`
  - proves the shared helper records a non-terminal failure observation and raises the explicit HTTP
    bookkeeping contract

## Validation
- `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_job_service_state_transitions.py tests/unit/services/ingestion_service/routers/test_job_bookkeeping.py tests/integration/services/ingestion_service/test_ingestion_routers.py -k "bookkeeping or mark_queued or record_failure_observation" -q`
- `python -m ruff check src/services/ingestion_service/app/routers/job_bookkeeping.py src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/routers/transactions.py src/services/ingestion_service/app/routers/portfolios.py src/services/ingestion_service/app/routers/instruments.py src/services/ingestion_service/app/routers/market_prices.py src/services/ingestion_service/app/routers/fx_rates.py src/services/ingestion_service/app/routers/business_dates.py src/services/ingestion_service/app/routers/portfolio_bundle.py src/services/ingestion_service/app/routers/reprocessing.py src/services/ingestion_service/app/routers/reference_data.py tests/unit/services/ingestion_service/services/test_ingestion_job_service_state_transitions.py tests/unit/services/ingestion_service/routers/test_job_bookkeeping.py tests/integration/services/ingestion_service/test_ingestion_routers.py`
- `python scripts/openapi_quality_gate.py`

## Follow-up
- The next worthwhile move is to add one DB-backed proof for the same post-persist bookkeeping failure
  on the reference-data path, so we have runtime evidence for both Kafka-backed and durable-persist
  ingress variants.
