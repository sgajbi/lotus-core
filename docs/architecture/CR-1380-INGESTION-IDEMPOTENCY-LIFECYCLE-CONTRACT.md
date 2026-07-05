# CR-1380 Ingestion Idempotency Lifecycle Contract

## Objective

Complete GitHub issue #554 by making ingestion job idempotency a durable endpoint/key/payload
lifecycle contract instead of only a local conflict check.

## Expected Improvement

- Concurrent requests with the same endpoint and `X-Idempotency-Key` are serialized before the
  select/create decision, preventing duplicate job creation races.
- Same endpoint plus same idempotency key plus same canonical payload replays the existing job
  acknowledgement across accepted, queued, and failed lifecycle states.
- Same endpoint plus same idempotency key plus different canonical payload returns deterministic
  `409 INGESTION_IDEMPOTENCY_CONFLICT`.
- OpenAPI now documents the idempotency conflict response on job-backed ingestion and reprocessing
  routes.
- Idempotency diagnostics now distinguish cross-endpoint key reuse from historical same-endpoint
  conflicting payload fingerprints.

## Changes

- Added a transaction-scoped PostgreSQL advisory lock before keyed ingestion job lookup/create.
- Extended idempotency diagnostics with `payload_fingerprint_count`,
  `max_payload_fingerprints_per_endpoint`, `payload_conflict_detected`, and
  `reuse_classification`.
- Added shared OpenAPI response helpers for `INGESTION_IDEMPOTENCY_CONFLICT` and reused them across
  job-backed ingestion command routes.
- Preserved the existing reprocessing policy-conflict example while adding idempotency-conflict
  evidence under the same `409` response.

## Compatibility

No route path, success DTO, database table, Kafka topic, event payload, metric name, or runtime
topology changed. Missing idempotency keys keep creating independent jobs. The only intentional
behavioral contract is stricter keyed replay: same endpoint/key must match the canonical payload
fingerprint, and concurrent keyed submissions are serialized.

## Validation

Focused validation for this slice:

- `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_payload_evidence.py tests/unit/services/ingestion_service/services/test_ingestion_job_service_guardrails.py::test_get_idempotency_diagnostics_counts_collisions_and_sorts_endpoints tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py::test_openapi_describes_reprocessing_parameters_and_shared_schema tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py::test_openapi_describes_ingestion_idempotency_conflict_response -q`
- scoped Ruff lint and format checks for touched source/test files.
- documentation/wiki guards before commit.

## Documentation And Wiki Decision

Updated this architecture note, the codebase review ledger, repo-local engineering context, and
Ingestion Service wiki source. No platform-wide skill update is needed: the durable rule is
repo-local ingestion ownership, not a cross-repo workflow change.

## Follow-Up

Issue #554 remains pending PR CI/QA, merge to `main`, and post-merge issue closure. Retention/expiry
policy remains a future operational policy slice because there is no current idempotency expiry
mechanism to truthfully document or enforce.
