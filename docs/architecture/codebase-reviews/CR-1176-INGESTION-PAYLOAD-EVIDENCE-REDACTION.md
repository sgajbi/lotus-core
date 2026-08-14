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

- every new job retains a deterministic, key-versioned HMAC-SHA-256 fingerprint of the complete
  original request under a request-payload-specific cryptographic domain;
- malformed active or retained-key configuration never publishes supplied secret material in
  fallback logs;
- retry and consumer-DLQ replay failures persist and return only bounded, code-owned reasons;
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
- migration replaces historical job and failure-history reason text with one bounded safe message
  and purges historical detail and header bodies, because legacy free-form evidence cannot be
  proven safe after capture; stable failure codes and failed-record keys remain available for
  recovery;
- `X-Idempotency-Key` is a bounded opaque identifier. Idempotency diagnostics and operational job
  list, detail, retry, and evidence projections expose only a purpose-bound, key-versioned
  HMAC-SHA-256 pseudonym while the deprecated raw-key field is null. The originating ingestion
  acknowledgement may still echo the caller's own key. Non-local profiles fail startup without a
  separate, non-local reference key of at least 32
  characters; JWT and auth-context signing keys are not reused. Payload fingerprints share the
  governed ingestion-evidence key authority under a distinct domain; retained prior keys allow
  deterministic equality checks during rotation, and the migration removes historical unkeyed
  fingerprints that could confirm guessable restricted inputs.

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
raw keys. A later review applied the same threat model to complete request fingerprints: every new
fingerprint is now a purpose-bound, key-versioned HMAC; active and retained prior keys preserve
same-payload equality through rotation; unknown keys fail closed; and migration `c157b2c3d524`
removes historical unkeyed request fingerprints that cannot be securely converted without their
original inputs. The downgrade clears c157 HMAC fingerprints because the prior application cannot
convert or compare them truthfully under its legacy unkeyed algorithm.
Historical failed replay-audit reasons are replaced during c157 migration because prior dispatcher
exceptions could contain broker credentials, connection URIs, or private request values.
The final same-pattern review extended that boundary to post-publish bookkeeping failures: both
ingestion-job retry and consumer-DLQ replay now project a bounded code-owned reason before audit
persistence and response publication, and c157 scrubs both `failed` and
`replayed_bookkeeping_failed` historical rows in the mapped `consumer_dlq_replay_audit` table.
Protected CI caught and corrected an earlier plural table-name typo before merge; the executable
migration guard now pins the singular mapped table and both unsafe historical statuses.
The two strong source-authority families retain required source identity, observation, and version
posture, but now declare `quality_status` and `source_batch_id` not applicable because their current
DTO/domain contracts do not capture those fields; lifecycle status remains separately represented
by `assignment_status` or `fact_status`. All reference-data policies declare `source_batch_id` not
applicable until a governed envelope contract validates and persists batch authority instead of
silently ignoring caller input. Ordinary families likewise declare `source_version` not applicable;
only benchmark assignments and the two strong-authority families declare version posture because
their DTOs validate and persist it. This removes false registry guarantees without weakening any
validated source authority or changing a request/response shape.

PR #948 rebase-merged to `main` as `43c8933fd40d5e45a1097619623878d3d41bfec4` after all
23 exact-head merge-gate jobs passed. The first exact-main Integration Full execution then exposed
two older migration fixtures that inserted directly into the current `ingestion_jobs` table without
the seven mandatory c157 policy fields. Fix-forward PR #950 uses one schema-aware fixture contract:
older schemas omit fields they do not own, the complete c157 schema receives the exact restricted,
fingerprint-only, non-replayable policy, and a partial evidence schema fails closed. Both migration
proofs now run in the protected `unit-db` lane as well as Integration Full, preventing the same
fixture drift from reaching main again. Mutable run, merge, wiki-parity, and verified issue-closure
evidence remains in #559 rather than being duplicated in this review record.
