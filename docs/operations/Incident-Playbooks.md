# lotus-core Incident Playbooks

This page is the operator-facing index for executable `lotus-core` incident playbooks.

Canonical playbook detail lives in
`contracts/operations/incident-playbooks.v1.json` and is enforced by:

```powershell
make incident-playbook-guard
```

The contract requires every playbook to define symptoms, dashboards or metrics, API checks,
database-safe checks, expected response fields, containment actions, escalation path, and
post-incident evidence. It also rejects destructive database or shell commands.

## Standard Triage Order

1. Confirm the running service/image with `GET /version` when a deploy mismatch is possible.
2. Check `/health/ready` before using business or operator routes.
3. Prefer support, replay, reconciliation, and lineage APIs before database inspection.
4. Use only read-only database checks during triage.
5. Use governed retry, replay, requeue, or repair endpoints only when the playbook says the action
   is supported by durable evidence.
6. Preserve correlation IDs, job IDs, run IDs, event IDs, audit IDs, and response bodies needed for
   post-incident evidence.

## Playbook Index

| ID | Incident | First checks | Primary containment |
| --- | --- | --- | --- |
| `ingestion-stuck-failed` | Ingestion stuck or failed | `GET /ingestion/jobs`, `GET /ingestion/jobs/{job_id}/failures`, load-run support API | Pause new affected submissions; avoid blind replay when `retry_safe` is false. |
| `dlq-growth` | Consumer DLQ growth | DLQ event list/detail APIs, consumer outcome metrics | Stop replay attempts until the error family is classified. |
| `replay-failure` | Replay failure | Replay audit API, governed replay response | Do not repeat replay commands without audit evidence. |
| `outbox-backlog` | Outbox backlog | failed outbox event and recovery-audit support APIs | Use governed requeue only for eligible terminal failed events. |
| `valuation-aggregation-lag` | Valuation or aggregation lag | support overview and readiness APIs | Avoid reseeding or replaying until lag is classified. |
| `stale-source-data` | Stale source data | source-data coverage/readiness products | Keep degraded or unavailable posture visible; do not fabricate evidence. |
| `reconciliation-failure` | Reconciliation failure | reconciliation runs and findings APIs | Keep supportability degraded until findings are explained or remediated. |
| `readiness-failure` | Readiness failure | `/health/ready`, `/version` | Do not route traffic to failed-ready services. |
| `database-connectivity` | Database connectivity | `/health/ready`, `python -m alembic current` after connectivity returns | Do not run migrations or repair commands during instability. |
| `kafka-connectivity` | Kafka connectivity | ingestion health, topic-creator logs, consumer metrics | Pause replay and bulk ingestion during publish/commit failures. |
| `security-audit-denial-spikes` | Security or audit denial spikes | `/version`, `/health/ready`, bounded denial reason counts | Do not disable production security controls to clear denials. |

## Evidence Boundary

Incident notes should include bounded evidence only:

- service name and image/version metadata,
- request correlation IDs, trace IDs, job IDs, event IDs, run IDs, and audit IDs,
- source-safe API responses,
- bounded metric or status counts,
- read-only database query outputs when API evidence is insufficient,
- operator action, actor, reason, and outcome.

Do not copy raw DLQ payloads, customer-sensitive payload fields, secrets, bearer tokens, database
connection strings, or unredacted stack traces into incident notes.

## Contract Maintenance

When adding an incident family:

1. add it to `contracts/operations/incident-playbooks.v1.json`,
2. add it to this page and the wiki runbook path,
3. run `make incident-playbook-guard`,
4. run `make quality-wiki-docs-gate`.
