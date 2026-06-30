# CR-1168 Consumer DLQ Replay Candidate Boundary

## Objective

Continue GitHub issue #446 by reducing the consumer-DLQ replay candidate selection hotspot in the
event replay ingestion operations route.

## Issue Triage

Issue #446 remains valid and in scope. CR-1167 reduced replay publish dispatch; this slice addresses
the next measured B-ranked helper, `_consumer_dlq_replay_candidate_or_response(...)`.

## Baseline Risk

`_consumer_dlq_replay_candidate_or_response(...)` mixed correlated job lookup, job-id extraction,
replay context loading, deterministic fingerprint construction, missing-payload not-replayable
response recording, and replayable tuple construction. That made the DLQ replay gate harder to
review and test independently.

## Change

Extracted focused helpers:

- `_replay_job_id(...)`
- `_consumer_dlq_replay_fingerprint(...)`
- `_consumer_dlq_missing_payload_response(...)`

Added direct tests for:

- no correlated job response recording,
- correlated job without durable payload response recording,
- replayable context and fingerprint tuple return.

## Expected Improvement

- `_consumer_dlq_replay_candidate_or_response(...)` is reduced from `B (8)` to `A (4)`.
- The route module maintainability remains bounded at `B (16.86)`.
- DLQ replay candidate policy is easier to inspect without changing public route behavior.

## Compatibility And Behavior

Existing behavior is preserved:

- no correlated job still records and returns `not_replayable`,
- missing durable replay payload still records and returns `not_replayable`,
- replayable context still returns `(job_id, context, fingerprint)`,
- deterministic fingerprint inputs remain unchanged.

No API route, OpenAPI response shape, database schema, data product, or downstream contract changed.

## Tests Added

Extended `tests/unit/services/event_replay_service/test_ingestion_operations.py` with direct
consumer-DLQ replay candidate tests.

## Validation

```powershell
python -m pytest tests\unit\services\event_replay_service\test_ingestion_operations.py -q
python -m pytest tests\integration\services\event_replay_service\test_event_replay_app.py -q
python -m ruff check src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_ingestion_operations.py
python -m ruff format --check src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_ingestion_operations.py
python -m radon cc src\services\event_replay_service\app\routers\ingestion_operations.py -s
python -m radon mi src\services\event_replay_service\app\routers\ingestion_operations.py -s
make quality-complexity-gate
make quality-maintainability-gate
```

Observed:

- focused ingestion operations helper tests: `13 passed`
- event replay app integration/OpenAPI tests: `10 passed`
- Ruff lint passed
- Ruff format check passed
- `_consumer_dlq_replay_candidate_or_response(...)` reports `A (4)`
- module maintainability reports `B (16.86)`
- `make quality-complexity-gate` passed
- `make quality-maintainability-gate` passed

## Residual Issue Scope

Issue #446 should remain open. Remaining candidates include retry payload shaping, job field
normalization consolidation, and additional operator response assembly extraction.

## Documentation Decision

Updated the codebase review ledger, quality scorecard, and refactor health report. No README or wiki
update was needed because this is internal replay candidate policy refactoring with no
operator-facing workflow or supported-capability change.
