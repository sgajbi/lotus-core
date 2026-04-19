# Event Replay Service

## Purpose

The event replay service is the replay, remediation, and ingestion-operations control plane inside
`lotus-core`.

It exists so operators can inspect ingestion health, DLQ evidence, replay posture, and reprocessing
queues through governed APIs instead of relying on ad hoc Kafka or database intervention.

## What it handles

The current runtime centers on:

- ingestion job listing, filtering, and failure inspection
- backlog, SLO, error-budget, operating-band, and capacity diagnostics
- stalled-job and consumer-lag views
- consumer DLQ event listing and correlated replay
- durable replay audit history
- reprocessing queue and operations-mode visibility

This makes the service an operational control plane, not a write-ingress surface.

## Runtime role

For replay and remediation workflows, the service:

1. reads canonical ingestion-job and operational state
2. exposes health, backlog, and saturation signals for operators and automation
3. lets operators inspect consumer DLQ evidence with topic, group, and correlation context
4. replays canonical ingestion payloads through governed recovery routes
5. records durable replay audit rows and failure posture for later review

The key design rule is that replay is controlled and evidence-backed. It is not a generic message
republisher.

## Data it owns

Primary durable surfaces include:

- `ingestion_jobs`
- `ingestion_job_failures`
- `ingestion_ops_control`
- consumer DLQ evidence and replay-audit tables
- reprocessing queue health and related operations state

These outputs feed:

- operator triage
- support and incident investigation
- governed replay and remediation decisions
- automated ingestion-health monitoring

## Why it matters

If replay and remediation are weak:

- operators are forced into unsafe direct Kafka or database intervention
- DLQ evidence can be disconnected from the original ingestion payload lineage
- replay can happen without durable auditability
- backlog and consumer pressure can be misread until downstream failures become visible elsewhere

That is why the replay service is a distinct control plane inside core rather than a hidden toolset.

## Boundary rules

- canonical write ingress remains in `ingestion_service`
- event replay owns replay, DLQ, backlog, ops-mode, and ingestion-health control APIs
- replay routes must preserve idempotency semantics and durable audit evidence
- this service supports operators and automation; it does not replace calculator or persistence
  ownership

## Operational hints

Check this service when:

- ingestion jobs are piling up and you need backlog or saturation diagnostics
- consumer DLQ pressure is rising
- a failed ingestion payload needs governed replay
- operators need replay audit history or reprocessing-queue health
- ops mode or replay guardrails are in question

Check beyond this service when:

- the issue is initial request validation or canonical ingest acceptance itself
- downstream calculator state is wrong after ingress has already completed successfully

## Related references

- [Ingestion Service](Ingestion-Service)
- [System Data Flow](System-Data-Flow)
- [Operations Runbook](Operations-Runbook)
- [Troubleshooting](Troubleshooting)
- [Lotus Core Microservice Boundaries and Trigger Matrix](../docs/architecture/microservice-boundaries-and-trigger-matrix.md)
