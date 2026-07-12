# CR-1183 Replay Audit Infrastructure Error

## Objective

Begin GitHub issue #650 by replacing generic replay audit persistence failures with a typed
infrastructure error carrying safe diagnostic reason codes.

## Expected Improvement

- Replay audit persistence no longer raises a plain `RuntimeError`.
- Missing DB session and persistence failures are distinguishable by safe reason code.
- Concrete persistence exceptions are preserved as causes without becoming the public error type.
- Infrastructure error taxonomy guidance now exists for future adapter slices.

## Changes

- Added `InfrastructureAuditWriteFailed` in `ingestion_service.app.services.infrastructure_errors`.
- Updated `record_consumer_dlq_replay_audit_response(...)` to raise typed errors for:
  - no yielded session: `audit_session_unavailable`;
  - persistence failure: `audit_persistence_failed`.
- Added focused tests for successful audit writes, no-session failure, and persistence failure.
- Added `infrastructure-error-taxonomy.md` documenting the initial typed error and mapping guidance.

## Compatibility

Successful replay audit persistence behavior is unchanged: replay ID shape, DB row fields, metrics,
timestamps, and response callers are preserved. Failure paths now expose a typed subclass of
`RuntimeError`, so existing broad exception handling remains compatible while new code can branch on
`InfrastructureAuditWriteFailed.reason_code`.

## Validation

- `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_replay_audits.py -q`
- `python -m ruff check src/services/ingestion_service/app/services/infrastructure_errors.py src/services/ingestion_service/app/services/ingestion_replay_audits.py tests/unit/services/ingestion_service/services/test_ingestion_replay_audits.py`
- `python -m ruff format --check src/services/ingestion_service/app/services/infrastructure_errors.py src/services/ingestion_service/app/services/ingestion_replay_audits.py tests/unit/services/ingestion_service/services/test_ingestion_replay_audits.py`
- `git diff --check`

## Documentation And Wiki Decision

Updated this CR evidence note, `infrastructure-error-taxonomy.md`, the codebase review ledger, and
quality scorecard/health report because infrastructure error handling policy changed. No wiki
source update is required because no operator workflow or public API contract changed.

## Follow-Up

Issue #650 remains open for database adapter, Kafka/event-publisher adapter, HTTP/client, cache,
storage, and configuration error translation slices, plus application/API error mapping guidance.
