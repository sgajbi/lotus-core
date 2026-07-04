# Domain State Transition Policy

Lifecycle state transitions in `lotus-core` are domain rules. They must be modeled as pure domain
policies before API handlers, workers, repositories, ORM rows, or infrastructure clients mutate
durable status fields.

## Required Shape

Each lifecycle policy must define:

1. the canonical status vocabulary for the workflow,
2. named transitions rather than ad hoc string comparisons,
3. allowed source statuses for each transition,
4. target status, or `None` when the transition only changes metadata,
5. terminal or immutable statuses,
6. retryable or repairable statuses,
7. required audit, failure-evidence, or operator-evidence metadata,
8. conflict behavior when the durable row no longer matches the expected source state.

Persistence models store status values. They do not own transition rules.

## Layering Rule

- Domain policy modules define transition vocabulary and rules.
- Application services choose the transition that matches the use case and map conflicts to stable
  operator/API errors.
- Repositories and lifecycle persistence helpers use policy-derived expected statuses in
  compare-and-set mutations.
- API DTOs, ORM rows, Kafka payloads, and downstream response models must not be imported into
  domain policy modules.

## Implemented Policies

The governed implementations are:

```text
src/services/ingestion_service/app/domain/ingestion_job_lifecycle_policy.py
src/services/financial_reconciliation_service/app/domain/reconciliation_run_lifecycle_policy.py
```

The ingestion policy defines ingestion job statuses, transition names, source states, target
states, replay-audit requirements, failure-evidence requirements, retry metadata requirements, and
explicit terminal-state posture for ingestion job lifecycle mutations.

The reconciliation policy defines reconciliation run statuses, completion transition metadata,
terminal statuses, retryable statuses, and automatic-bundle outcome policy for failed runs and
error-finding replay posture.

## Test Requirements

For each lifecycle policy, add direct unit tests that cover:

- valid transitions,
- invalid source states,
- terminal-state behavior,
- retry or repair behavior when the workflow supports it,
- audit or failure-evidence metadata requirements.

Persistence tests should separately prove that durable mutations consume policy-derived expected
states instead of duplicating string status sets.
