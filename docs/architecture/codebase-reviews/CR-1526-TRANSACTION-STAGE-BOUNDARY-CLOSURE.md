# CR-1526: Transaction Stage Boundary Closure

Date: 2026-07-11
Issue: #468
Status: Reconciled candidate; release validation pending

## Objective

Close the calculator and orchestrator stage-boundary contract after cost, cashflow, and position
became one transaction-processing deployable, without weakening the independent module boundaries
or claiming that local evidence is a production rollout.

## Acceptance Matrix

| Issue requirement | Local evidence |
| --- | --- |
| Stage owners linked to code packages | `microservice-boundaries-and-trigger-matrix.md` maps each stage to its deployable, application owner, package boundary, ports/adapters, state, and read model. |
| Inputs, outputs, idempotency, and replay are explicit | The enforced stage contract table and reliability rules identify the trigger, emitted contract, semantic/transport fence, epoch or job identity, replay behavior, and produced state for every transaction-to-controls stage. |
| CI prevents obvious cross-stage dependencies | `architecture_boundary_guard.py` blocks the unified transaction package from orchestrator/query internals and blocks orchestrators from both retired calculator and unified transaction internals. The guard runs in Feature Lane, PR Merge Gate, and Main Releasability. |
| Runtime decisions use evidence | The runtime-boundary standard, decision catalog, calculator decision, and issues #712-#714 require workload, backfill, failure-isolation, ownership, data, rollback, and SLO evidence before further merge/split decisions. |

## Implementation Outcome

- Cost, cashflow, and position are separately named domain/application/infrastructure modules under
  `portfolio_transaction_processing_service`.
- One live consumer and one replay-request consumer invoke one combined use case and SQLAlchemy unit
  of work. Cost, cashflow, position, semantic idempotency, and compatibility outbox effects commit
  or roll back together.
- Every transaction emitted by cost traverses position and cashflow exactly once before commit.
  This includes generated settlement cash legs and rebuilt epochs; see CR-1545 for the focused
  reconciliation decision and proof.
- The three legacy calculator source roots, standalone consumers, packages, images, Compose
  services, CI service inventory, and Kubernetes scalers are retired locally.
- Position valuation remains a separate job-driven runtime. Pipeline, valuation, timeseries, and
  aggregation boundary reviews remain evidence-gated under #712, #713, and #714 rather than being
  folded into this issue without operational proof.

## Validation Evidence

- Reconciled focused adapter, image-package, and architecture-guard cohort: `31 passed`.
- Complete target-owned transaction unit/domain suite: `447 passed`.
- Repository-native PostgreSQL transaction-processing contract: `51 passed`.
- Strict architecture boundary guard: passed.
- Complete repository architecture gate: passed.
- Target-file Ruff and MyPy: passed.
- The source branch previously recorded broader unit, PostgreSQL, deployment, image, and capacity
  evidence. Those results are not claimed as current reconciliation evidence until rerun against
  this history.

## Compatibility

No API path, DTO, Kafka topic, event payload, consumer-visible header, metric name, database table,
deployed column, or downstream response contract was intentionally changed by source retirement.
Compatibility cost and cashflow events remain published from the unified outbox until downstream
contract retirement is separately approved and evidenced.

## Documentation Decision

README, architecture decision, boundary matrix, repository context, codebase review ledger, and
authored wiki describe the unified owner. CR-1545 additionally records the generated-leg traversal
in repository context and the cashflow wiki. No separate operator runbook change is required because
cutover and rollback commands did not change.

## Remaining Release Work

Fixed-local is not merged-main or production-complete. Image build/import, deployment and cutover
gates, capacity evidence, registry publication, release
artifact verification, server-side Kubernetes validation, controlled rollout,
shutdown/pool-pressure proof, canonical platform QA, rollback evidence, and post-merge wiki
publication remain mandatory.
