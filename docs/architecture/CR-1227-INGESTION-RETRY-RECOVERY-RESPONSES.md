# CR-1227 Ingestion Retry Recovery Responses

Date: 2026-07-01

## Objective

Fix GitHub issue #598 by standardizing ingestion job retry failure responses into a governed
recovery detail shape. The slice promotes the reusable platform pattern that operator recovery
endpoints must classify outcomes and remediation guidance instead of returning raw downstream
exception text as the primary client message.

## Change

- Added a centralized ingestion-job retry recovery detail builder with stable `outcome`,
  `remediation`, and `recovery_path` fields.
- Routed retry not-found, unsupported retry, unsupported partial retry, retry blocked, duplicate
  blocked, publish failed, bookkeeping failed, and audit-write failed paths through the governed
  detail shape.
- Changed retry publish failure from raw exception propagation to a controlled HTTP 500
  `INGESTION_RETRY_PUBLISH_FAILED` response after recording replay audit evidence and marking the
  job failed.
- Kept raw downstream failure text in durable audit/job failure state, but removed it from the
  primary client-facing publish/bookkeeping failure message.
- Updated OpenAPI examples to include the publish-failure outcome and the richer recovery detail
  fields.

## Expected Improvement

Operators now receive consistent recovery outcomes for the ingestion retry endpoint:
`not_found`, `retry_unsupported`, `partial_retry_unsupported`, `retry_blocked`,
`duplicate_blocked`, `publish_failed`, `bookkeeping_failed`, and `audit_write_failed`.

This makes replay incident handling safer because clients can key off stable `code` and `outcome`
values while support teams get durable audit/job-state evidence for the underlying failure. It also
reduces information exposure by preventing raw downstream exception strings from becoming the main
client message.

## Tests Added

- Retry not-found governed recovery detail.
- Retry unsupported durable-payload recovery detail.
- Partial retry unsupported recovery detail.
- Retry blocked recovery detail.
- Duplicate retry blocked recovery detail and audit side effect.
- Retry publish failure recovery detail, replay audit side effect, and failed-job side effect.
- Retry bookkeeping failure recovery detail with sanitized primary message.
- OpenAPI publish-failure example coverage.
- Integration assertions for retry not-found, unsupported, partial unsupported, blocked, and
  bookkeeping-failure recovery fields.

## Validation Evidence

- Focused unit and OpenAPI tests passed:
  `python -m pytest tests\unit\services\event_replay_service\test_ingestion_operations.py tests\integration\services\event_replay_service\test_event_replay_app.py -q`.
- Focused retry/OpenAPI integration selection passed:
  `python -m pytest tests\unit\services\event_replay_service\test_ingestion_operations.py tests\integration\services\event_replay_service\test_event_replay_app.py tests\integration\services\ingestion_service\test_ingestion_routers.py -q -k "ingestion_job_retry or event_replay_openapi"`.
- Scoped Ruff lint passed:
  `python -m ruff check src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_ingestion_operations.py tests\integration\services\event_replay_service\test_event_replay_app.py tests\integration\services\ingestion_service\test_ingestion_routers.py`.
- Scoped Ruff format check passed:
  `python -m ruff format --check src\services\event_replay_service\app\routers\ingestion_operations.py tests\unit\services\event_replay_service\test_ingestion_operations.py tests\integration\services\event_replay_service\test_event_replay_app.py tests\integration\services\ingestion_service\test_ingestion_routers.py`.

- Repository lint gate passed:
  `make lint`.
- Type checking passed:
  `make typecheck`.
- OpenAPI gate passed:
  `make openapi-gate`.
- API vocabulary gate passed:
  `make api-vocabulary-gate`.
- Wiki/documentation gate passed:
  `make quality-wiki-docs-gate`.
- Whitespace diff check passed:
  `git diff --check`.

## Downstream Compatibility

The route path, HTTP status codes, success DTO, replay audit persistence, job failure persistence,
and existing application `code` values are preserved. The intentional contract expansion is the
addition of `outcome`, `remediation`, and `recovery_path` fields in ingestion-job retry failure
details, plus the new explicit `INGESTION_RETRY_PUBLISH_FAILED` code for retry publish failures.

The publish failure path previously re-raised the downstream exception; it now returns a governed
HTTP 500 response after preserving durable audit and job-failure side effects.

No database schema, Kafka topic, service topology, or success response model changed.

## Documentation And Wiki Decision

Updated this architecture record, the codebase review ledger, operations runbook, repository
context, quality scorecard, and refactor health report. No repo-local wiki update is required
because the operator-facing retry recovery truth is summarized in `docs/operations-runbook.md` and
the API route remains unchanged.

## Remaining Follow-Up

- Keep issue #598 open for PR/CI/QA evidence and Docker-backed retry workflow proof.
- Apply the same governed outcome/remediation detail pattern to adjacent recovery endpoints when
  their issue-backed slices are selected.
