# CR-293: Replay publish truth after bookkeeping failure

Date: 2026-03-14

## Summary
- Hardened the ingestion replay endpoints so a replay that already published to Kafka is no longer
  flattened into generic `failed` if later retry-state or audit bookkeeping fails.

## Problem
- Both replay paths in `ingestion_operations.py` used one broad `try/except` around:
  - `_replay_job_payload(...)`
  - `mark_retried(...)`
  - `mark_queued(...)`
  - `record_consumer_dlq_replay_audit(..., replay_status="replayed")`
- If Kafka replay succeeded but a later bookkeeping step failed, the code:
  - recorded replay audit status as `failed`
  - treated the retry as a normal publish failure
  - and, for ingestion-job retry, marked the job failed again
- That under-reported what really happened: the replay was already published.
- It also left duplicate-blocking blind to that published replay, because successful replay lookup
  only recognized `replayed`.

## Change
- Added a distinct replay audit status:
  - `replayed_bookkeeping_failed`
- Split both replay flows into two phases:
  - publish phase
  - post-publish bookkeeping phase
- If publish fails:
  - behavior stays on the true publish-failure path
- If publish succeeds but bookkeeping fails:
  - we best-effort record `replayed_bookkeeping_failed`
  - return an explicit 500 contract error
  - and do not flatten the outcome into plain publish failure
- Updated replay-success lookup to treat both:
  - `replayed`
  - `replayed_bookkeeping_failed`
  as already-published outcomes for duplicate blocking.
- Updated replay-audit DTO vocabulary and failure metrics to include the new truthful status.

## Why this matters
- Operators need to know whether a replay actually reached Kafka.
- After this change, the audit trail distinguishes:
  - replay never published
  - replay published but post-publish state persistence failed
- That reduces accidental double replay and makes incident triage materially sharper.

## Evidence
- Integration proofs:
  - `tests/integration/services/ingestion_service/test_ingestion_routers.py`
  - proves:
    - ingestion-job retry returns `INGESTION_RETRY_BOOKKEEPING_FAILED` after a real publish when
      queue-state bookkeeping fails
    - consumer DLQ replay returns `INGESTION_DLQ_REPLAY_BOOKKEEPING_FAILED` after a real publish
      when queue-state bookkeeping fails
    - both flows record replay audit status `replayed_bookkeeping_failed`
    - a second replay is duplicate-blocked because publish already happened
- Unit proofs:
  - `tests/unit/services/ingestion_service/services/test_ingestion_job_service_guardrails.py`
  - proves replay bookkeeping failure increments failure metrics under the new status

## Validation
- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -k "bookkeeping_failure or replay_audit or replay_consumer_dlq_event" -q`
- `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_job_service_guardrails.py -k "replay_audit" -q`
- `python -m ruff check src/services/event_replay_service/app/routers/ingestion_operations.py src/services/ingestion_service/app/DTOs/ingestion_job_dto.py src/services/ingestion_service/app/services/ingestion_job_service.py tests/integration/services/ingestion_service/test_ingestion_routers.py tests/unit/services/ingestion_service/services/test_ingestion_job_service_guardrails.py`
- `python scripts/openapi_quality_gate.py`

## Follow-up
- The next worthwhile move is to keep looking for recovery paths where Kafka publish success and
  later bookkeeping are still flattened into one outcome, especially around operator-facing replay
  and remediation flows.
