# Calculator Runtime Consolidation Decision

Status: Implemented locally; registry/cluster rollout and post-merge certification pending
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

## Post-Unification Runtime Boundary Review

After cost, cashflow, and position code has moved to target-owned packages and the combined runtime
has production workload evidence, run a separate boundary review for:

- `timeseries_generator_service`;
- `valuation_orchestrator_service`;
- `pipeline_orchestrator_service`;
- `portfolio_aggregation_service`;
- `position_valuation_calculator`.

Do not assume that these five services should either remain separate or collapse into one runtime.
Evaluate each capability by command/trigger model, source and derived state ownership, transaction
boundary, ordering, scaling profile, backfill volume, failure isolation, deployment cadence,
security boundary, SLO, and operational ownership. Prefer one deployable with explicit in-process
modules when those dimensions are materially shared; retain a runtime boundary only when measured
independent scaling, isolation, or ownership value exceeds its operational cost.

The review must test these specific hypotheses:

1. Unified transaction completion may make parts of `pipeline_orchestrator_service` redundant;
   delete obsolete stage gates instead of merging a no-longer-needed orchestrator.
2. Position valuation is market-data/job driven and currently has a different scale and failure
   profile from booked-transaction processing, so it remains separate unless workload evidence
   disproves that boundary.
3. Valuation job orchestration and valuation execution may share one deployable while retaining
   application/worker modules, but only if scheduling availability and compute saturation do not
   require independent isolation.
4. Security-level timeseries generation and portfolio aggregation form one derived-state pipeline
   and may share a deployable, but only if dependency ordering, backfills, and portfolio fan-in can
   be bounded without coupling their failure recovery.

Required output is a before/after runtime and data-flow map, dependency and consumer inventory,
load/backfill evidence, failure-mode analysis, database/table ownership decision, migration and
rollback plan, and explicit keep/merge/retire decision for every runtime. Do not begin this phase by
moving folders; complete the cost/cashflow target-ownership work first.

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

Steps 1 through 7 are implemented locally. Cost, cashflow, and position source ownership now lives
under the target package; the three legacy source roots, standalone consumers, package/image
inventories, Compose workers, and Kubernetes scalers are removed. Local implementation completion
must not be confused with production rollout: registry publication, controlled cluster rollout,
canonical platform QA, rollback, and post-merge release evidence remain mandatory.

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
