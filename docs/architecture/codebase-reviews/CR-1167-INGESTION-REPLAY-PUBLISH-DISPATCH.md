# CR-1167 Ingestion Replay Publish Dispatch

## Objective

Make progress on GitHub issue #446 by reducing the event replay ingestion operations route hotspot
around replay payload publishing while preserving retry and DLQ replay behavior.

## Issue Triage

Issue #446 is valid and in scope. The route module still contains operationally sensitive replay,
retry, DLQ, audit, and response-mapping logic. This slice addresses one bounded hotspot:
`_replay_job_payload(...)`.

## Baseline Risk

`_replay_job_payload(...)` used a long endpoint `if` chain that mixed endpoint support policy,
request DTO validation, payload-field selection, ingestion-service method dispatch, and unsupported
endpoint error behavior. That made it harder to review replay publish behavior independently from
the route orchestration around it.

## Change

- Added `_ReplayPayloadPublisher`, a small immutable endpoint publisher descriptor.
- Added `_REPLAY_PAYLOAD_PUBLISHERS`, a declarative endpoint-to-request-model/publish-method map.
- Routed `_replay_job_payload(...)` through the publisher table.
- Added direct tests for list-field publish dispatch, whole-model portfolio-bundle dispatch, and
  unsupported endpoint rejection.

## Expected Improvement

- `_replay_job_payload(...)` is reduced from `B (9)` to `A (2)`.
- The route module maintainability improves to `B (17.01)`.
- Endpoint publish policy is visible in one declarative table.
- Future endpoint additions can be reviewed as table entries instead of adding branching.

## Compatibility And Behavior

Existing behavior is preserved:

- supported endpoints still validate through their existing request DTOs,
- list-backed endpoints still publish the DTO list field,
- portfolio bundles still publish the whole request model,
- unsupported endpoints still raise `ValueError("Retry not supported ...")`.

No API route, OpenAPI response shape, database schema, data product, or downstream contract changed.

## Tests Added

Extended `tests/unit/services/event_replay_service/test_ingestion_operations.py` with focused replay
publish dispatch tests.

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

- focused ingestion operations helper tests: `10 passed`
- event replay app integration/OpenAPI tests: `10 passed`
- Ruff lint passed
- Ruff format check passed
- `_replay_job_payload(...)` reports `A (2)`
- `_ReplayPayloadPublisher` reports `A (3)`
- module maintainability reports `B (17.01)`
- `make quality-complexity-gate` passed
- `make quality-maintainability-gate` passed

## Residual Issue Scope

Issue #446 should remain open after this slice. Remaining candidates include DLQ replay candidate
selection, retry payload shaping, and additional operator response assembly extraction.

## Documentation Decision

Updated the codebase review ledger, quality scorecard, and refactor health report. No README or wiki
update was needed because this is internal replay dispatch refactoring with no operator-facing
workflow or supported-capability change.
