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
- `X-Idempotency-Key` is a bounded opaque identifier, and operator diagnostics expose only a
  purpose-bound, key-versioned HMAC-SHA-256 pseudonym while the deprecated raw-key field is always
  null. Non-local profiles fail startup without a separate, non-local reference key of at least 32
  characters; JWT and auth-context signing keys are not reused.

Focused evidence includes 73 replay/evidence/migration tests, 65 failure/lifecycle/command tests,
31 idempotency-boundary/diagnostic tests, OpenAPI gate success, and regenerated API-vocabulary
parity. A dedicated PostgreSQL database on the existing Core local stack passed full-history
upgrade to `c157b2c3d524`, verified all seven governed payload-evidence columns and nullability,
downgraded to `c156b2c3d523`, and re-applied `c157b2c3d524`. The exact temporary database was then
removed; the shared `portfolio_db` remained at `c156b2c3d523` and every Core application container
remained healthy. Issue #559 is fixed locally and remains open until protected-PR, exact-main,
wiki-publication, and verified closure evidence are complete.

Protected CI then exposed two test-boundary gaps and both were fixed forward. SQLAlchemy's default
JSON binding encoded Python `None` as JSON `null`, which violated the database invariant requiring
fingerprint-only rows to retain no request body and made absent failure detail/header evidence look
durably present. All three nullable JSON evidence columns now use `JSON(none_as_null=True)`, and
the migration normalizes historical JSON literal nulls to SQL `NULL` before it classifies retained
payload authority. Model, migration, and isolated real-PostgreSQL guards prove that absent request
payload, failure detail, and failure headers remain SQL `NULL`. The operations harness
also retained raw fixture bodies and legacy exception assertions after production had become
policy-aware and source-safe. It now builds evidence through the production registry, derives
record replayability only from the durable representation, uses `/ingest/instruments` for positive
retry and matching instrument-DLQ proofs, keeps restricted transaction evidence explicitly
non-replayable, and verifies that diagnostics contain only non-reversible idempotency-key
references. Repository-native `make test-ops-contract` passed all 318 cases; the focused
payload/retry/DLQ cohort passed 45 cases; the database-model cohort passed 54 cases; MyPy passed all
318 source files; and the full architecture guard passed. Exact-head and exact-main CI evidence is
recorded on GitHub rather than inferred from these local results.

PR review found two further authority-boundary defects. Record-status responses could continue to
advertise replayable record keys after the 24-hour authority expired, and both retry command paths
could cross expiry while awaiting permission or duplicate controls. Record projection now uses the
same evidence authorization as replay, and ingestion-job plus consumer-DLQ commands recheck a fresh
UTC observation immediately before dry-run acknowledgement or dispatch. Race tests expire the
actual shared context during awaited controls and prove fail-closed outcomes without publication.
Review also showed that an unkeyed SHA-256 reference allowed dictionary confirmation of accepted
low-entropy idempotency keys. Diagnostics now use an explicitly injected, domain-separated
HMAC-SHA-256 reference with a visible key id; stale OpenAPI examples no longer disclose synthetic
raw keys.
