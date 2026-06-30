# CR-1188 Ingestion Idempotency Full Fingerprint

Date: 2026-06-30

## Objective

Fix GitHub issue #675 by separating ingestion idempotency conflict identity from source-safe payload
evidence. Idempotency conflict checks must detect same-key/different-payload submissions even when
the changed values are sensitive and redacted in durable diagnostics.

## Change

- Added nullable `ingestion_jobs.request_payload_fingerprint`.
- Added an index on `idempotency_key, request_payload_fingerprint`.
- New ingestion jobs persist a non-reversible SHA-256 fingerprint of the full canonical request
  payload before redaction.
- Durable `request_payload` evidence remains source-safe/redacted.
- Idempotency conflict checks now prefer the full request fingerprint when available and retain the
  legacy source-safe comparison only for historical rows with no stored full fingerprint.

## Expected Improvement

Same endpoint and idempotency key reuse now detects sensitive-value changes, such as changed
authorization fields, while avoiding raw sensitive payload retention. This restores idempotency
correctness without weakening the redacted diagnostic payload posture from CR-1176.

## Tests Added

- New jobs persist redacted request payload evidence plus a full canonical request fingerprint.
- Same idempotency key and same full payload replays.
- Same idempotency key and different non-sensitive payload conflicts.
- Same idempotency key and different sensitive payload conflicts even though source-safe fingerprints
  match after redaction.

## Validation Evidence

- `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_payload_evidence.py -q`
  passed with 8 tests.
- `python -m alembic heads` reported single head `c1005f6a7b8c9`.
- `python -m ruff check ...` passed for the touched ingestion lifecycle, evidence helper, model,
  migration, and focused test files.
- `python -m ruff format --check ...` passed for the touched ingestion lifecycle, evidence helper,
  model, migration, and focused test files.
- `git diff --check` passed.

## Downstream Compatibility

No route path, response DTO, Kafka topic, request DTO, durable redacted request-payload evidence
shape, or same-key/same-payload replay behavior changed. The intentional behavior change is that
same endpoint and idempotency key reuse with different sensitive payload values now returns the
existing deterministic idempotency conflict instead of replaying the previous job.

The database schema intentionally changes by adding nullable `request_payload_fingerprint` and an
idempotency lookup index.

## Documentation And Wiki Decision

This architecture record, the codebase review ledger, and quality/refactor scorecards were updated.
No wiki update is required because no operator-facing command, published API shape, or wiki-authored
runbook changed.

## Remaining Follow-Up

- Backfill historical `request_payload_fingerprint` only if raw or encrypted original payloads become
  available under an approved retention policy; redacted historical payloads cannot reconstruct
  sensitive-value identity.
- Continue the broader #559 payload retention/encryption/replay policy work separately.
- Add route-level OpenAPI 409 documentation for the existing deterministic conflict response under
  the broader idempotency policy backlog.
