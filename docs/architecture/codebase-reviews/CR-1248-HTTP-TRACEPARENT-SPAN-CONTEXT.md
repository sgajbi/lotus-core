# CR-1248 HTTP Traceparent Span Context

Date: 2026-07-01

## Objective

Fix GitHub issue #492 by replacing the fixed synthetic HTTP `traceparent` span id with a reusable
W3C-compatible trace-context helper.

## Change

- Added shared span-id normalization and generation in `portfolio_common.logging_utils`.
- Tightened trace-context normalization so all-zero trace ids and all-zero span ids are rejected.
- Updated `traceparent_from_trace_id(...)` to create a fresh non-zero span id when a valid
  `X-Trace-Id` is present without an incoming `traceparent`.
- Removed the hard-coded `0000000000000001` fallback from standard HTTP bootstrap.
- Preserved inbound valid `traceparent` exactly and continued deriving `X-Trace-Id` from it.

## Expected Improvement

HTTP responses no longer advertise a repeated synthetic span id as distributed trace context.
Downstream services, gateways, and observability tooling receive valid W3C-shaped context with a
fresh server-side span id when the request only carries a trace id or no trace headers.

## Tests Added Or Updated

- Shared logging utility tests for all-zero trace/span rejection, supplied span preservation,
  generated span ids, and generated `traceparent` shape.
- Shared HTTP bootstrap tests for generated health-app trace context, inbound `traceparent`
  preservation, and `X-Trace-Id` to `traceparent` derivation.
- Query-service HTTP middleware regression test updated to reject the former fixed span id.

## Validation Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_logging_utils.py tests\unit\libs\portfolio-common\test_http_app_bootstrap.py -q --tb=short`
  -> 22 passed.
- `python -m pytest tests\integration\services\query_service\test_main_app.py -k "middleware or metrics" -q --tb=short`
  -> 6 passed, 24 deselected.
- `python -m pytest tests\unit\libs\portfolio-common\test_outbox_repository.py tests\unit\libs\portfolio-common\test_events.py tests\unit\libs\portfolio-common\test_event_supportability.py tests\unit\libs\portfolio-common\test_kafka_consumer.py tests\unit\services\ingestion_service\services\test_ingestion_service.py -q --tb=short`
  -> 88 passed.
- Scoped Ruff lint and format checks passed for touched Python files.
- `make typecheck` passed.
- `make quality-wiki-docs-gate` passed.
- `git diff --check` passed with line-ending warnings only.
- `Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` reported expected unpublished wiki drift
  for this branch's `Operations-Runbook.md` update plus existing `Outbox-Events.md` drift; publish
  is intentionally deferred until after merge.

## Downstream Compatibility

No route paths, response bodies, event schemas, Kafka topics, or existing correlation headers
changed. HTTP responses still include `X-Correlation-ID`, `X-Request-Id`, `X-Trace-Id`, and
`traceparent`; the only intentional behavior change is replacing the fixed fallback span id with a
fresh non-zero W3C span id.

## Documentation And Wiki Decision

Updated this architecture record, observability docs, operations runbook, wiki source, repository
context, quality scorecard, and refactor health report because the supported HTTP tracing contract
changed. The wiki source change must be checked before PR merge and published after merge.

## Remaining Follow-Up

Lotus Core now provides W3C-compatible trace context propagation. It still does not claim full
OpenTelemetry span export, sampling policy, collector configuration, or APM backend integration.

Stranded-truth reconciliation on 2026-07-01 found open Dependabot PRs #688 and #689 as active
dependency-update branches. Both are behind `main` and carry stale older documentation diffs
alongside dependency/workflow updates; they require separate Dependabot PR rebase/update handling
and are not cherry-picked into this issue slice.
