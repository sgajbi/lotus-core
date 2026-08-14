# CR-1176 Ingestion Payload Evidence Redaction

## Objective

Begin GitHub issue #559 by reducing durable ingestion request-payload exposure without changing
current replay contracts or database schema.

## Expected Improvement

- Ingestion job creation uses one source-safe payload evidence boundary before durable persistence.
- Sensitive request-payload keys and credential-bearing text are redacted before values are stored
  in `ingestion_jobs.request_payload`.
- Non-sensitive ingestion payloads retain their shape for existing replay and record-status flows.
- A canonical SHA-256 payload fingerprint helper is available for the follow-up schema-backed
  idempotency/conflict slice.

## Changes

- Added `ingestion_payload_evidence.py` with:
  - `PAYLOAD_EVIDENCE_POLICY_VERSION`,
  - canonical payload serialization,
  - deterministic `sha256:` payload fingerprinting,
  - source-safe request-payload redaction using the shared `portfolio_common.logging_utils`
    sensitivity policy.
- Routed `create_or_get_job_result(...)` through `source_safe_request_payload(...)` before creating
  the durable `IngestionJob` row.
- Added focused tests proving canonical fingerprint stability, no input mutation, redaction of
  sensitive payload fields, and redacted persistence through the ingestion job lifecycle helper.

## Compatibility

No API route shape, DTO response shape, Kafka topic, database schema, migration, or replay route
contract changed. Existing replay behavior remains compatible for ordinary non-sensitive ingestion
payloads. If callers submit secret-like fields such as authorization tokens, account numbers,
client email addresses, database URLs, or credentials, those values are intentionally not retained
in durable replay payload storage.

## Retention And Access-Control Posture

This slice does not claim full payload minimization or retention closure. The existing
`request_payload` column remains the replay source for replayable families, but new persisted
payload values pass through source-safe redaction first. Follow-up work should add schema-backed
fingerprints, endpoint-level retention/replay policy, payload expiry posture, and explicit replay
behavior when a payload is absent or expired.

## Validation

- `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_payload_evidence.py tests/unit/services/ingestion_service/services/test_ingestion_record_status.py -q`
- `python -m ruff check src/services/ingestion_service/app/services/ingestion_payload_evidence.py src/services/ingestion_service/app/services/ingestion_job_lifecycle.py tests/unit/services/ingestion_service/services/test_ingestion_payload_evidence.py`
- `python -m ruff format --check src/services/ingestion_service/app/services/ingestion_payload_evidence.py src/services/ingestion_service/app/services/ingestion_job_lifecycle.py tests/unit/services/ingestion_service/services/test_ingestion_payload_evidence.py`

## Documentation And Wiki Decision

Updated this ledger entry, the quality scorecard/health report, and repo-local Event Replay Service
wiki source. No generated OpenAPI or database-schema documentation changed because this slice does
not add columns or route fields.

## Follow-Up

Issue #559 remains open pending PR, GitHub CI, and QA evidence. Further slices should add
schema-backed payload fingerprints, endpoint retention policy declarations, and conflict handling
for the same idempotency key with different canonical payloads.

## 2026-08-14 Governed Evidence Tranche

The follow-up implementation replaces the original uniform redacted-body posture with a versioned,
endpoint-owned policy registry covering all 35 job-creating ingestion families:

- every new job retains the deterministic SHA-256 fingerprint of the complete original request;
- restricted, confidential, or unsupported replay families retain no request body;
- only approved reference-data families retain a source-safe replay body, with a 24-hour technical
  expiry distinct from the legal retention/hold/deletion authority tracked by #708;
- historical bodies outside the approved families are purged by migration, while legacy redacted
  rows remain explicitly non-replayable because they cannot prove full request identity;
- job, operator-retry, and consumer-DLQ paths fail closed for missing/legacy policy, ineligible or
  wrong representation, absent payload/expiry, expired authority, or unauthorized partial replay;
- job responses publish policy version, classification, representation, replay eligibility, expiry,
  and retention authority without publishing the retained body;
- durable failures use one source-safe projection: arbitrary exception text, request/client data,
  nested unknown fields, credentials, and arbitrary headers are removed; only stable product
  messages, allowlisted recovery fields, and numeric `Retry-After` survive initial response and
  idempotent replay;
- `X-Idempotency-Key` is a bounded opaque identifier, and operator diagnostics expose only a full
  SHA-256 reference while the deprecated raw-key field is always null.

Focused evidence includes 73 replay/evidence/migration tests, 65 failure/lifecycle/command tests,
31 idempotency-boundary/diagnostic tests, OpenAPI gate success, and regenerated API-vocabulary
parity. Issue #559 remains in progress until migration integration, full local/remote gates, PR,
exact-main validation, and verified issue closure are complete.
