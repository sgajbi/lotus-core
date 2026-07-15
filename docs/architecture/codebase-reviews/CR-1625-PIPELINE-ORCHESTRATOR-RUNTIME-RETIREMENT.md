# CR-1625: Pipeline Orchestrator Runtime Retirement

Date: 2026-07-15
Issue: [#712](https://github.com/sgajbi/lotus-core/issues/712)
Status: Fixed locally; PR, exact-main validation, and wiki publication pending

## Objective

Retire the generic pipeline coordinator after every surviving transition has a capability owner.
Reduce runtime and design-time complexity without changing downstream event or support contracts.

## Finding

The pipeline runtime had become a distributed relay:

1. atomic transaction processing already owned cost, cashflow, position, and readiness;
2. portfolio aggregation could stage its reconciliation request in the same transaction as
   aggregation completion;
3. financial reconciliation could persist its own control outcome and stage the controls event in
   the same transaction as reconciliation completion.

Keeping the relay added three consumer groups, extra outbox-to-consumer failure windows, duplicate
runtime/bootstrap code, one image and health API, and ownership indirection without an independent
scaling, security, data, or operational boundary.

## Decision

Assign each transition to the capability that owns the resulting state:

| Transition | Owner |
| --- | --- |
| transaction financial effects to valuation readiness | `portfolio_transaction_processing_service` |
| aggregation completion to reconciliation request | `portfolio_aggregation_service` |
| reconciliation completion to durable controls decision | `financial_reconciliation_service` |

Delete the pipeline application, domain, ports/adapters, repositories, consumers, worker package,
Dockerfile, Compose service, CI image target, health/OpenAPI/security registration, scrape target,
and dashboard topology membership.

## Layering

The new direct paths follow the governed dependency direction:

1. Kafka consumer maps the governed event to a domain record.
2. Application use case coordinates a typed evidence repository and event-staging port.
3. Domain policy owns severity merge, blocking classification, and latest-epoch emission rules.
4. SQLAlchemy and outbox implementations remain in capability-owned infrastructure adapters.

No domain/application module imports SQLAlchemy models, Kafka clients, FastAPI objects, or
downstream response DTOs.

## Before/After Scorecard

| Measure | Before | After |
| --- | ---: | ---: |
| Generic pipeline deployables/images | 1 | 0 |
| Pipeline consumer groups | 3 | 0 |
| Cross-runtime relay hops for the three reviewed transitions | 3 | 0 |
| Pipeline business/application source roots | 1 deployable tree | 0 |
| Capability-owned atomic transitions | 0 of 3 | 3 of 3 |
| Pipeline health/OpenAPI/security/scrape surfaces | 1 each | 0 |

The bounded retirement commits removed the obsolete code/runtime surface and added only
capability-owned domain, application, port, infrastructure, regression-test, and current-truth
artifacts.

## Correctness And Resilience

- Transaction readiness is staged only after all financial effects succeed in one transaction.
- Aggregation completion and reconciliation request share one DB/outbox transaction.
- Reconciliation control evidence, completion, and controls publication share one DB/outbox
  transaction.
- Repeated control outcomes merge monotonically (`COMPLETED` < `REQUIRES_REPLAY` < `FAILED`).
- Older epochs persist support evidence but cannot emit a stale controls decision.
- Existing idempotency, correlation, trace, epoch, retry, and outbox contracts remain in force.

## Compatibility

No Kafka topic, event type, schema field, aggregate identity, correlation behavior, public route,
OpenAPI request/response schema, or database schema changed.

`transactions.cost.processed`, `cashflows.calculated`,
`portfolio_day.aggregation.completed`, and `portfolio_day.reconciliation.completed` remain emitted
compatibility facts. Their active in-repo relay consumers are removed. QCP continues to read the
same durable `FINANCIAL_RECONCILIATION` rows.

## Database Decision

Do not rename or delete `pipeline_stage_state` in this slice. Transaction readiness still writes
the table and QCP support APIs still read it. A table split/rename would add migration and rollback
risk without being necessary to retire the runtime. Any later schema change requires retention,
historical-row, backfill, read-cutover, rollback, and downstream support evidence.

## Security And Observability

The change removes an unused trust/runtime surface rather than adding one. The retired image,
health API, security-control registry entry, version endpoint, Prometheus scrape target, and
dashboard service membership are deleted. Capability-owned events retain correlation and shared
outbox observability.

## Validation

- 99 focused financial-reconciliation/pipeline/event tests passed for direct control ownership.
- 3 PostgreSQL control-evidence tests passed for monotonic status and latest epoch.
- 91 focused dead-stack/architecture tests and 2 affected QCP PostgreSQL scenarios passed.
- 110 runtime, event, OpenAPI, workflow, readiness, and observability tests passed.
- Focused MyPy passed across all new/touched direct-control source modules.
- Ruff, diff, Compose config, JSON parsing, architecture, mapping, event-runtime, OpenAPI, security,
  supported-feature, repository-shape, image-provenance, and workflow-governance checks passed.
- Wiki check identified exactly the five authored branch pages awaiting post-merge publication:
  Architecture, cost, cashflow, operations, and timeseries/aggregation.

Branch-wide and CI evidence is recorded separately before merge; exact-main validation and wiki
publication remain required before issue closure.

## Same-Pattern Prevention

- `tests/unit/test_retired_pipeline_runtime.py` prohibits restoration of the service root, runtime
  ID, image name, and active inventory entries.
- Event supportability catalog ownership now names aggregation and reconciliation directly.
- Repository context tells agents to place transitions with the capability owning resulting state.
- Runtime-boundary governance must reject a replacement deployable without measured independent
  scaling, failure-isolation, security, SLO, or operational ownership evidence.

## Remaining Work

1. Merge and exact-main validate this bounded #712 batch.
2. Publish repo-local wiki source after merge.
3. Close #712 only after lifecycle evidence is recorded.
4. Track compatibility-event retirement and any shared-table redesign as separately reversible
   work backed by downstream consumer and retention evidence.
