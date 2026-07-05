# CR-1177 Ingestion Idempotency Payload Conflict

## Objective

Begin GitHub issue #554 by preventing silent replay when the same ingestion idempotency key is
reused for the same endpoint with a different payload.

## Expected Improvement

- Same endpoint plus same idempotency key plus same source-safe canonical payload continues to
  return the existing ingestion job acknowledgement.
- Same endpoint plus same idempotency key plus different source-safe canonical payload now fails
  with a deterministic conflict instead of silently returning unrelated prior job evidence.
- The conflict response uses a stable `409` problem shape with endpoint and idempotency-key context.
- The comparison reuses CR-1176 source-safe fingerprints so secret-like value changes do not require
  durable retention of the original secret values.

## Changes

- Added `source_safe_payload_fingerprint(...)` to the ingestion payload evidence helper.
- Added `IngestionIdempotencyConflictError` and payload-conflict detection in
  `create_or_get_job_result(...)`.
- Added an ingestion app exception handler that maps idempotency conflicts to
  `409 INGESTION_IDEMPOTENCY_CONFLICT`.
- Added focused tests for same-key/same-payload replay, same-key/different-payload conflict, and
  the deterministic 409 response body.

## Compatibility

No database schema, route path, Kafka topic, DTO success response, or normal duplicate replay
contract changed. This is an intentional behavior change for conflicting requests only: a reused
idempotency key with a different source-safe canonical payload now returns 409 instead of replaying
the first job.

## Validation

- `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_payload_evidence.py tests/unit/services/ingestion_service/services/test_ingestion_record_status.py -q`
- `python -m ruff check src/services/ingestion_service/app/services/ingestion_payload_evidence.py src/services/ingestion_service/app/services/ingestion_job_lifecycle.py src/services/ingestion_service/app/main.py tests/unit/services/ingestion_service/services/test_ingestion_payload_evidence.py`
- `python -m ruff format --check src/services/ingestion_service/app/services/ingestion_payload_evidence.py src/services/ingestion_service/app/services/ingestion_job_lifecycle.py src/services/ingestion_service/app/main.py tests/unit/services/ingestion_service/services/test_ingestion_payload_evidence.py`

## Documentation And Wiki Decision

Updated this ledger entry, the quality scorecard/health report, and repo-local Ingestion Service
wiki source. CR-1380 completes the route-level OpenAPI response metadata, concurrent keyed-create
guard, lifecycle replay policy tests, and diagnostics classification.

## Follow-Up

Issue #554 remains open pending PR, GitHub CI, QA evidence, merge to `main`, and post-merge closure.
Retention/expiry policy remains a future operational policy slice because no expiry mechanism is
implemented today.
