# CR-1457: Worker Runtime Component Task Identity

Date: 2026-07-10
Issue: #468
Status: Hardened locally

## Objective

Make combined-worker readiness and failure supervision identify which consumer or runtime component
exited, without exposing unbounded errors or business identifiers.

## Defect

`run_kafka_worker_runtime()` created consumer, dispatcher, and health-server tasks without names.
Asyncio therefore assigned generic identities such as `Task-17`. The shared readiness layer could
correctly mark `worker_runtime` failed, but supervision logs and internal snapshots could not tell
whether the live consumer, replay consumer, outbox dispatcher, or health server exited.

This becomes materially worse after calculator consolidation because several responsibilities share
one process and one readiness dependency.

## Change

- `BaseConsumer` now exposes its immutable consumer group through a read-only `group_id` property;
- each Kafka task is named `kafka-consumer:<group_id>:<topic>`;
- the dispatcher task is named `outbox-dispatcher`;
- the embedded server task is named `health-server`;
- dynamic task-name components are stripped, source-safe, and bounded; unavailable identities fall
  back to a stable indexed name.

The target pair therefore identifies
`portfolio_transaction_processing_group/transactions.persisted` separately from
`portfolio_transaction_replay_request_group/transactions.reprocessing.requested`.

## Security And Observability

Task names contain only transport topology, not payloads, portfolio/security/client IDs,
correlation/trace IDs, exception text, credentials, or connection strings. Component identity is
available to supervision logs and internal snapshots. Public readiness remains the bounded
`worker_runtime` status and does not expose exception details.

## Compatibility

Consumer topics, groups, offsets, processing behavior, concurrency, APIs, schemas, metrics, images,
and deployment manifests are unchanged. All web-backed Core workers gain clearer task identity.

README and public API docs do not change. The operations runbook, observability guide, repo context,
and wiki now carry the reusable worker-task naming rule.

## Validation

- focused worker runtime, readiness, supervision, target manager, and target composition pack:
  25 passed;
- exact component names, unsafe-character normalization, length bound, and fallback behavior tested;
- `worker_runtime.py` MyPy passed;
- Ruff and diff checks passed;
- `kafka_consumer.py` retains ten pre-existing full-file MyPy findings outside this slice; no new
  finding was introduced.
