# Calculator Runtime Consolidation Decision

Status: App-local/CI and Kubernetes manifests cut over; registry/cluster/legacy removal pending
Date: 2026-07-10  
Issue: #468  
Target: `portfolio_transaction_processing_service`

Cutover and removal tracking:
[transaction-processing consolidation change ledger](./transaction-processing-consolidation-change-ledger.md).

## Decision

Consolidate `cost_calculator_service`, `cashflow_calculator_service`, and
`position_calculator_service` into one transaction-processing deployable. Keep cost, cashflow, and
position as separate domain/application modules inside that deployable.

Keep `position_valuation_calculator` independently deployable.

## Why Consolidate These Three

The three workers implement one ordered transaction-processing capability and currently duplicate:

- 321 lines of consumer-manager startup, health, signal, dispatcher, and shutdown wiring;
- 261 lines across three near-identical Dockerfiles;
- three Python dependency packages with materially overlapping runtime dependencies;
- three embedded health servers and three outbox dispatcher loops.

The target reduces three deployables to one, removes two runtime shells, and replaces asynchronous
normal-path fan-out with one transaction-processing application use case. Calculation policies
remain independently testable.

## Why Valuation Remains Separate

Valuation is job-driven rather than transaction-event driven. It has different scaling pressure,
market-data dependencies, latency/backfill behavior, failure recovery, and compute profile.
Independent deployment and failure isolation therefore have current operational value.

## Preserved Boundaries

| Boundary | Required compatibility |
| --- | --- |
| Cost | Own cost basis, lot state, accrued offsets, cost replay, and `transactions.cost.processed`. |
| Cashflow | Own rule resolution, cashflow persistence, and `cashflows.calculated`. |
| Position | Own ordered position reduction, history/snapshots, epoch fencing, and backdated replay. |
| Transaction unit of work | Normal booked-transaction processing commits cost, cashflow, position, idempotency, and compatibility outbox effects atomically. Reprocessing uses an explicit bounded replay unit of work. |
| Kafka | Preserve topics, partition keys, payloads, and headers. Move live/replay offsets to the clearly named target groups through the verified cutover command; never rely on reset policy. |
| Reliability | Use one semantic transaction-processing idempotency claim while preserving module outcome diagnostics, retry classification, DLQ reasons, and outbox compatibility. |
| Operations | Preserve module-specific metrics and diagnostics; expose one aggregate health/version surface. |

`ProcessTransactionUseCase` coordinates cost policy, cashflow policy, and the position reducer
through typed application/domain contracts and ports. It must not reach into concrete repositories
or consumer implementations. Existing cost/cashflow/readiness events remain compatibility outbox
events during migration; they can be retired only after every downstream consumer has moved to the
combined completion contract.

## Migration Sequence

1. Canonicalize event owners and enforce calculator/orchestrator dependency boundaries.
2. Extract typed cost, cashflow, and position policies/ports plus uniquely named packages.
3. Add the combined host in compatibility mode with existing consumers, groups, metrics, and
   health dependencies.
4. Add `ProcessTransactionUseCase` and one atomic normal-path unit of work while emitting existing
   compatibility outbox events.
5. Prove duplicate delivery, replay, DLQ, rollback-on-module-failure, shutdown, and backlog behavior.
6. Switch local/CI deployment manifests to the combined image and run local load/tie-out proof.
7. The three legacy service shells, images, and package manifests are removed. Move the surviving
   workflow/domain/repository modules and remove the obsolete normal-path stage wait only after
   downstream compatibility, registry/cluster rollout, and canonical platform QA pass.

Steps 1 through 6 are implemented locally. The branch must not claim full runtime consolidation
complete before step 7 and the remaining release/deployment gates are validated.

## Rollback

Retain the existing event contracts throughout migration. Use
`scripts/operations/transaction_processing_cutover_offsets.py` to audit and copy exact drained live/replay
offsets into the target groups. Before legacy deployables are removed, rollback requires a
quiesced, reviewed reverse offset handoff and one atomic deployment-manifest change back to all
three images. Database rollback is not required because this decision introduces no schema
ownership change.

## Acceptance Evidence

Runtime consolidation is complete only when:

- calculator unit and DB integration suites pass unchanged;
- event/outbox and architecture guards pass;
- the combined image passes provenance, SBOM, vulnerability, signing, and attestation gates;
- readiness identifies failed cost, cashflow, position, Kafka, database, and dispatcher components;
- throughput and backlog evidence is no worse than the three-service baseline at the governed load;
- duplicate/replay tests prove no double mutation or lost stage transition;
- a failure in any normal-path calculation proves the complete transaction-processing unit of work
  rolls back without partial cost, cashflow, position, idempotency, or outbox state;
- Docker Compose and deployment manifests contain one transaction-processing worker;
- `/version` and OCI metadata remain consistent with the image provenance contract.
