# RFC 086 - Load Drain Throughput, Completion Telemetry, and Materialization Assurance

| Field | Value |
| --- | --- |
| Status | Draft |
| Created | 2026-04-18 |
| Last Updated | 2026-04-18 |
| Owners | lotus-core engineering |
| Depends On | RFC 024; RFC 065; RFC 066; RFC 081 |
| Related Standards | production-readiness and operational governance standards |
| Scope | In repo |

## Executive Summary

The live institutional bank-day load run on 2026-04-18 demonstrated that `lotus-core` can ingest a realistic portfolio-ledger workload without obvious correctness failures, but it also exposed a material readiness gap:

1. ingestion completes,
2. sample APIs remain correct and responsive,
3. failed job counts stay at zero,
4. but full downstream completion is too slow and too opaque to qualify as banking-grade operational behavior.

This RFC closes that gap by defining a focused hardening program across three linked concerns:

1. post-ingestion materialization throughput,
2. run-scoped completion telemetry,
3. interruption-safe, operator-grade evidence generation.

The latest live-run diagnosis on 2026-04-18 also shows that the lag is not evenly distributed
across the downstream drain. Snapshot coverage materially leads position-timeseries and
portfolio-timeseries coverage, so Phase 1 must first explain that stage boundary before changing
worker parallelism or scheduler cadence.

The first implementation slice is intentionally narrow. We should establish truthful completion visibility before changing concurrency or orchestration behavior. Once the platform can explain run state precisely, we can optimize the drain path with much lower operational risk.

## Decision Summary

`lotus-core` will treat large institutional load execution as a first-class operational contract rather than an ad hoc script outcome.

This RFC approves the following direction:

1. add durable, run-scoped completion telemetry,
2. emit partial evidence artifacts on interruption, timeout, or abort,
3. make portfolio-level completion visible through a support/control-plane contract,
4. use those measurements to optimize post-ingestion drain throughput without weakening deterministic stage guarantees.

This RFC does **not** approve speculative concurrency increases without first landing the observability and completion-accounting foundation.

## Original Requested Requirements (Preserved)

The user-requested scope that motivated this RFC was:

1. validate whether `lotus-core` can process a realistic bank day of `1000` portfolios with `100` transactions each,
2. measure how long the system takes to ingest, calculate, reconcile, and expose accurate API responses,
3. produce customer-grade evidence across DB state, APIs, logs, and reconciliation results,
4. identify bottlenecks and tighten the application while the run is in progress,
5. eliminate operational ambiguity that would undermine confidence in the platform as a ledger authority.

## Problem Statement

`lotus-core` currently has a strong ingestion path and a directionally sound event-driven architecture, but it does not yet provide an institutional-grade completion contract for large bank-day runs.

Today, after full ingestion, operators cannot answer these questions quickly and truthfully without manual SQL and ad hoc interpretation:

1. how many portfolios are fully complete,
2. how many are still in valuation versus aggregation,
3. whether the run is merely unfinished, operationally slow, or effectively stuck,
4. when final API outputs are complete enough to use for customer or sign-off evidence.

That is a production-readiness defect even when numeric correctness appears stable.

## Current Implementation Reality

### Implemented foundation

1. A governed load harness exists at `scripts/bank_day_load_scenario.py`.
2. Smoke-run evidence is emitted as JSON and Markdown artifacts.
3. A real valuation scheduler defect was discovered under load and fixed in `src/libs/portfolio-common/portfolio_common/valuation_repository_base.py`.
4. A regression integration test now protects that defect path in `tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_repo_empty_open_dates.py`.

### Live full-run evidence baseline

At `2026-04-18T09:09:16Z`, direct database facts for the active full run `20260418T065154Z`
showed:

1. `100000` transactions ingested successfully,
2. `1000` portfolios ingested successfully,
3. `0` failed valuation jobs,
4. `0` failed aggregation jobs,
5. `1000` portfolios with at least one target-date snapshot,
6. `562` portfolios with at least one target-date position-timeseries row,
7. `561` portfolios with at least one target-date portfolio-timeseries row,
8. `100000` total target-date snapshots written,
9. `56194` total target-date position-timeseries rows written,
10. `561` total target-date portfolio-timeseries rows written,
11. `0` pending valuation jobs and `0` processing valuation jobs,
12. `1` pending aggregation job and `0` processing aggregation jobs,
13. the target business date `2026-04-17` already present in both snapshots and portfolio
    timeseries,
14. valuation-to-position-timeseries handoff latency at `56194` matched rows with p50
    `2174.8558825` seconds, p95 `2353.17991545` seconds, and max `2371.357363` seconds,
15. before the targeted service refresh, the running control-plane container still returned `404`
    for the new support route because the live stack had not yet been refreshed to the Phase 0
    code,
16. after the targeted refresh, `GET /support/load-runs/20260418T065154Z?business_date=2026-04-17`
    returned `COMPLETE` at `2026-04-18T12:00:25Z` with `1000/1000` portfolio coverage for
    snapshots, position-timeseries, and portfolio-timeseries,
17. the original harness process PID `42764` no longer existed at measurement time even though
    downstream services were still materializing new position-timeseries and portfolio-timeseries
    rows.

### What this means

The platform does **not** currently look numerically broken.

Instead, the run points to a different defect class:

1. portfolio-level completion is too slow,
2. completion visibility is too weak,
3. the operator evidence model is incomplete for long-running or interrupted executions,
4. the current lag now concentrates downstream of valuation completion and before broad
   position-timeseries completion, not inside portfolio aggregation after the aggregation stage
   has already caught up to completed position-timeseries breadth.

## Evidence From Live Run 20260418T065154Z

### Stable positive signals

1. Ingestion completed all requested records.
2. Sample query APIs remained healthy:
   - `GET /portfolios/{id}/positions?as_of_date=2026-04-17` returned `200` with `100` positions
   - `GET /portfolios/{id}/transactions?...` returned `200` with `100` transactions
   - `GET /support/portfolios/{id}/overview` returned `200` with no failed work for the sampled portfolio
3. Failed valuation and aggregation job counts remained at `0`.
4. The target materialization date `2026-04-17` was reached in sampled snapshot and timeseries output.
5. Queue state remained active rather than deadlocked; the open valuation backlog continued to
   move from processing work into complete state during repeated observations.

### Limiting signals

1. Portfolio coverage progressed much more slowly than ingestion volume.
2. The harness produced no final artifact before interruption.
3. Standard output and error logs for the full run remained empty, which forced manual state reconstruction.
4. Before the targeted service refresh, the running control-plane container returned `404` for
   `GET /support/load-runs/{run_id}`, so completion percentage initially had to be reconstructed
   from DB facts instead of the intended support contract.
5. Position-timeseries and portfolio-timeseries coverage lag snapshots materially, so “timeseries
   lag” is not a single opaque symptom.
6. At `2026-04-18T09:09:16Z`, valuation backlog had fully drained while position-timeseries and
   portfolio-timeseries breadth remained only about `56%`, which shifts the primary bottleneck to
   valuation-to-timeseries handoff and/or position-timeseries consumer throughput rather than
   valuation scheduler backlog.
7. The harness process can exit before asynchronous materialization finishes, so process lifetime
   is not a reliable proxy for pipeline completion.
8. At `2026-04-18T09:18:31Z`, there were still `26774` valuation jobs already in `COMPLETE`
   state with no matching `position_timeseries` row, and the oldest such completion had been
   waiting since `2026-04-18T08:46:24Z`, which confirms that the dominant backlog is now in
   post-valuation materialization rather than job dispatch.
9. At `2026-04-18T09:33:17Z`, the same run had reached full target-date coverage:
   `1000/1000` portfolios with snapshots, `1000/1000` portfolios with position-timeseries,
   `1000/1000` portfolios with portfolio-timeseries, and `0` completed valuation jobs still
   waiting for position-timeseries.
10. Even after materialization convergence, the live stack still carried a large pending outbox
    tail on topics with weak or no active runtime consumers: `50067`
    `portfolio_security_day.position_timeseries.completed` events and `503`
    `portfolio_day.aggregation.completed` events at `2026-04-18T09:33:17Z`.
11. After the review-driven hot-path cleanup and targeted runtime refresh, the support route
    returned `COMPLETE` at `2026-04-18T12:00:25Z`, `timeseries_generator_service` startup
    required only `valuation.snapshot.persisted`, and the dormant completion topics had `0`
    pending outbox rows; remaining rows were `PROCESSED` history only.
12. Final sampled reconciliation for the same run at `2026-04-18T12:19:27Z` covered
    `LOAD_20260418T065154Z_PF_0001` through `LOAD_20260418T065154Z_PF_0005` and found:
    `100` positions, `100` transactions, expected market value `11617.2163000000`, and `0`
    timeseries-integrity reconciliation findings for every sampled portfolio.
13. Exhaustive reconciliation for the same run at `2026-04-18T12:23:35Z` evaluated all
    `1000` portfolios through the new repo-native existing-run reconciliation workflow and found:
    `100/100` positions, `100/100` transactions, expected market value `11617.2163000000`, and
    `0` timeseries-integrity reconciliation findings for every portfolio.

## Requirement-to-Implementation Traceability

| Requirement | Current State | Evidence |
| --- | --- | --- |
| Realistic bank-day load generation | Implemented baseline | `scripts/bank_day_load_scenario.py`; `docs/operations/bank-day-load-scenario.md`; `tests/unit/scripts/test_bank_day_load_scenario.py` |
| Correctness under institutional load | Implemented baseline | live run `20260418T065154Z`; support-route evidence `output/task-runs/20260418T120025Z-rfc086-support-route-progress.md`; sampled reconciliation `output/task-runs/20260418T120025Z-rfc086-final-reconciliation.md`; exhaustive reconciliation `output/task-runs/20260418T122335-bank-day-load-reconciliation.md` |
| Deterministic visibility into completion state | Implemented baseline | run-scoped support contract and stage split metrics are live; `GET /support/load-runs/20260418T065154Z?business_date=2026-04-17` returned `COMPLETE` at `2026-04-18T12:00:25Z`; evidence: `output/task-runs/20260418T120025Z-rfc086-support-route-progress.md` |
| Interruption-safe operator evidence | Implemented baseline | `scripts/bank_day_load_scenario.py`; `output/task-runs/20260418T064716Z-bank-day-load.json`; `output/task-runs/20260418T064716Z-bank-day-load.md`; `tests/unit/scripts/test_bank_day_load_scenario.py` |
| Throughput adequate for institutional completion SLA | Partially implemented (requires enhancement) | full ingestion and snapshot completion were achieved, but target-date coverage remained at `562` position-timeseries portfolios and `561` portfolio-timeseries portfolios at `2026-04-18T09:09:16Z` while valuation-to-position-timeseries p50 latency remained about `36.25` minutes |

## Goals

1. make large-run completion state introspectable by `run_id`,
2. make interrupted runs leave truthful, usable evidence artifacts,
3. provide explicit portfolio-level completion accounting,
4. improve post-ingestion drain throughput without weakening deterministic stage correctness,
5. define measurable exit criteria for institutional load readiness.

## Non-Goals

1. replacing Kafka, Postgres, or the current event-driven topology,
2. rewriting valuation, cost, or cashflow business logic,
3. changing unrelated canonical API contracts,
4. tuning concurrency blindly before observability and completion accounting are in place.

## Design Principles

1. **Truth before speed**: a slow but explainable system is easier to harden than a fast but opaque one.
2. **Derive from durable facts**: run progress should come from durable stage/job state, not best-effort in-memory counters.
3. **Optimize after measurement**: concurrency changes require baseline telemetry first.
4. **No correctness regression for throughput gains**: RFC 024 and RFC 081 stage guarantees remain non-negotiable.
5. **Interrupted work must still be auditable**: partial output is a required operational artifact, not a convenience.

## Alternatives Considered

### A. Increase scheduler and worker concurrency immediately

Rejected as the first move.

Reason:

1. current observability is too weak to prove whether serialization, scheduling cadence, lock contention, or stage gating is the dominant bottleneck,
2. raising concurrency first increases the risk of duplicate work, harder-to-debug race conditions, and misleading apparent progress.

### B. Keep telemetry only inside the harness

Rejected as the long-term model.

Reason:

1. operators and downstream support workflows need run visibility without attaching to a script process,
2. supportability belongs in the application surface, not only in an external harness.

### C. Add only final artifact generation and skip live progress visibility

Rejected.

Reason:

1. final artifacts are necessary but insufficient,
2. live completion visibility is required to manage long-running bank-day executions safely.

## Proposed Changes

### 1. Add Run-Scoped Completion Telemetry

Introduce a durable run-progress model keyed by `run_id`.

Minimum telemetry dimensions:

1. `run_id`
2. started timestamp
3. terminal status: `running`, `complete`, `incomplete`, `failed`, `aborted`
4. portfolios ingested
5. transactions ingested
6. portfolios with any snapshots
7. portfolios with target-date snapshots complete
8. portfolios with target-date timeseries complete
9. open valuation jobs for the run
10. open aggregation jobs for the run
11. failed valuation jobs for the run
12. failed aggregation jobs for the run
13. oldest pending valuation date
14. oldest pending aggregation date
15. last progress heartbeat timestamp

Preferred exposure model:

1. durable progress facts in Postgres,
2. control-plane read contract in `query_control_plane_service`,
3. harness consumption of the same contract or same underlying query model.

### 2. Add Interruption-Safe Evidence Emission

Enhance `scripts/bank_day_load_scenario.py` so that any interruption, timeout, or controlled abort writes:

1. DB state summary,
2. completion percentages,
3. portfolio coverage counts,
4. open backlog summary,
5. sample API responses,
6. error/log summary,
7. explicit terminal status showing that the run is incomplete.

Required artifact outputs:

1. JSON
2. Markdown

This artifact must be written even when full completion is not reached.

### 3. Add Portfolio Completion Accounting

Track portfolio-level completion through explicit stage states, for example:

1. `ingested`
2. `valuation_pending`
3. `valuation_in_progress`
4. `valuation_complete`
5. `aggregation_pending`
6. `aggregation_in_progress`
7. `aggregation_complete`
8. `reconciliation_complete`
9. `failed`

This can be implemented as:

1. a dedicated run-progress table and stage rows, or
2. a deterministic derived query model over existing stage and job facts.

### 4. Tighten Post-Ingestion Throughput

Once telemetry is in place, profile and improve:

1. valuation scheduler polling cadence,
2. valuation claim batch sizing,
3. valuation worker parallelism,
4. aggregation scheduler polling cadence,
5. aggregation claim behavior,
6. hidden per-portfolio or per-date serialization,
7. avoidable latency between valuation completion and aggregation request emission.

This phase must remain evidence-driven. Every change needs before/after telemetry.

### 5. Add Completion-Focused Readiness Gates

Extend the load harness and validation stack with explicit assertions for:

1. full portfolio completion coverage,
2. bounded lag after ingestion completion,
3. interruption-safe artifact generation,
4. no failed valuation or aggregation jobs at steady state,
5. sampled API correctness after declared completion,
6. deterministic tie-out between ledger, snapshots, and timeseries.

## Success Metrics

RFC 086 is not complete when the code merely emits more logs. It is complete when the following become true for the institutional scenario:

1. operators can query run-scoped completion state without ad hoc SQL,
2. interrupted runs emit a truthful partial evidence pack automatically,
3. run coverage can be reported as:
   - portfolios ingested
   - portfolios snapshot-complete
   - portfolios timeseries-complete
   - remaining open work
4. a rerun of the `1000 x 100` scenario produces a complete final evidence pack,
5. post-ingestion completion time materially improves from the 2026-04-18 baseline.

For approval and implementation purposes, “materially improves” means:

1. the before/after comparison must be measured on the same scenario shape,
2. improvement must be reported with elapsed time and coverage progression,
3. no correctness regressions or increased failed-job rates are acceptable trade-offs.

## Phased Delivery Plan

### Phase 0 - Evidence and Telemetry Baseline

Deliver:

1. run-scoped progress query model,
2. partial artifact emission on interrupt/timeout/abort,
3. control-plane or support query for load-run progress.

Implementation status as of 2026-04-18:

1. completed in `src/services/query_service/app/repositories/operations_repository.py`,
   `src/services/query_service/app/services/operations_service.py`, and
   `src/services/query_control_plane_service/app/routers/operations.py` through
   governed `GET /support/load-runs/{run_id}?business_date=YYYY-MM-DD`,
2. completed in `scripts/bank_day_load_scenario.py` through interruption-safe JSON and
   Markdown artifact emission with explicit `terminal_status`,
3. completed with focused regressions in:
   - `tests/unit/services/query_service/repositories/test_operations_repository.py`
   - `tests/integration/services/query_service/test_int_operations_service.py`
   - `tests/unit/scripts/test_bank_day_load_scenario.py`,
4. reviewed for maintainability before closure of the slice:
   - replaced unsafe concurrent awaits on a shared `AsyncSession` with sequential reads,
   - completed field-level OpenAPI descriptions for the new response model so the contract is
     self-explanatory for operators and downstream consumers,
   - added interrupted-run regression coverage so partial evidence remains truthful.

Phase 0 exit criteria:

1. a stopped run emits partial JSON and Markdown evidence,
2. a run can be queried by `run_id`,
3. completion state can be described without manual SQL.

Phase 0 evidence:

1. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/dtos/operations_dto.py src/services/query_service/app/services/operations_service.py src/services/query_control_plane_service/app/routers/operations.py scripts/bank_day_load_scenario.py tests/unit/scripts/test_bank_day_load_scenario.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/integration/services/query_service/test_int_operations_service.py`
2. `python -m pytest tests/unit/scripts/test_bank_day_load_scenario.py tests/unit/services/query_service/repositories/test_operations_repository.py -q`
3. `python -m pytest tests/integration/services/query_service/test_int_operations_service.py -q`

Phase 0 outcome:

1. exit criteria satisfied,
2. no downstream contract break introduced because the new support route is additive,
3. the next limiting factor remains throughput/materialization pace rather than visibility.

### Phase 1 - Throughput Diagnosis and Safe Optimization

Deliver:

1. scheduler and worker cadence instrumentation,
2. measured stage latency breakdown,
3. targeted tuning of batch size, polling, or concurrency where evidence justifies it.

Implementation status as of 2026-04-18:

1. initial diagnostic telemetry landed in the branch by extending load-run progress output with:
   - target-date position-timeseries portfolio and row coverage,
   - explicit stage-gap counts between snapshots and position-timeseries, and between
     position-timeseries and portfolio-timeseries,
   - split pending versus processing valuation job counts,
   - split pending versus processing aggregation job counts,
   - latest per-stage materialization and queue heartbeat timestamps so operators can
     distinguish active drain from a quiet or stalled stage,
   - explicit count and oldest completion timestamp for valuation jobs that are already
     `COMPLETE` but still have no matching position-timeseries row,
   - valuation-to-position-timeseries handoff latency summary from durable facts,
   - matching harness evidence-pack fields so JSON and Markdown artifacts now expose the same
      stage boundary and queue split,
   - review-driven `as_of` consistency hardening so stage counts, latest-artifact timestamps,
     and latency samples all honor the same response-generation cutoff instead of mixing
     pre-cutoff job state with post-cutoff materialized rows,
   - review-driven cleanup of the `timeseries_generator_service` consumer so it now accepts only
     the active `valuation.snapshot.persisted` trigger, with dead compatibility parsing for
     `portfolio_security_day.valuation.completed` removed and runtime/governance docs aligned to
     the actual handoff path,
   - review-driven removal of the unused `portfolio_security_day.valuation.completed` outbox
     emission from `position_valuation_calculator`, eliminating duplicated hot-path outbox work
     after confirming that the topic has no active runtime producer/consumer path,
   - follow-up review-driven removal of the unused
     `portfolio_security_day.position_timeseries.completed` outbox emission from
     `timeseries_generator_service` after live-run evidence showed a large pending outbox tail on a
     topic with no active runtime consumer,
   - targeted write-churn reduction in `timeseries_generator_service` so aggregation jobs are no
     longer redundantly restaged when the same portfolio-day is already `PENDING` under the same
     correlation id, while still rearming late material changes when status or correlation
     actually changes,
   - follow-up hot-path simplification in `timeseries_generator_service` that removed the
     redundant per-message `Instrument` lookup and retry branch from
     `valuation.snapshot.persisted` processing, because the event is emitted only after snapshot
     persistence and the downstream timeseries calculation does not consume instrument data,
2. repeated live-run measurement now shows the main lag boundary more precisely:
   - snapshots (`1000` portfolios) reached full coverage,
   - valuation backlog drained to `0` open jobs,
   - follow-up live measurement at `2026-04-18T09:18:31Z` showed position-timeseries (`733`
     portfolios) and portfolio-timeseries (`732` portfolios) still materially incomplete even
     after valuation backlog drain,
   - `26774` completed valuation jobs still had no matching position-timeseries row, with the
     oldest such completion waiting since `2026-04-18T08:46:24Z`,
   - valuation-to-position-timeseries latency remains roughly `36` to `40` minutes across
     `56194` matched rows,
   - portfolio-timeseries closely tracks completed position-timeseries breadth, so portfolio
     aggregation is no longer the limiting stage,
3. the next justified optimization slice should therefore focus on valuation-to-position-timeseries
   drain behavior and handoff cadence before changing portfolio aggregation internals,
4. live follow-up at `2026-04-18T09:33:17Z` then showed that the bank-day run does fully
   converge without failures, but only after a substantial post-valuation drain period of roughly
   `28` minutes after the last target-date snapshot was persisted (`2026-04-18T09:05:10Z` to
   `2026-04-18T09:32:59Z` for full position-timeseries coverage),
5. the same follow-up exposed a large non-critical outbox tail on dormant
   `portfolio_security_day.position_timeseries.completed` publication, which justifies removing
   that emission instead of treating worker concurrency as the first optimization lever.
6. review-driven cleanup then removed the dormant
   `portfolio_security_day.valuation.completed` and
   `portfolio_security_day.position_timeseries.completed` hot-path emissions, marked those event
   families as runtime-dormant in the supportability catalog, and refreshed the runtime so the
   active timeseries worker now requires only `valuation.snapshot.persisted` at startup.
7. post-refresh support-route evidence at `2026-04-18T12:00:25Z` shows the run in `COMPLETE`
   state with `0` open valuation jobs, `0` open aggregation jobs, `0` completed valuations still
   waiting for position-timeseries, and no pending outbox rows on the dormant completion topics.
8. a new repo-native `scripts/bank_day_load_reconciliation_report.py` workflow now lets operators
   reconcile an existing completed run without reseeding data, which reduces pressure to rerun a
   long institutional load test just to tighten correctness evidence after drain completion.

Phase 1 exit criteria:

1. bottleneck stage is explicitly identified,
2. before/after metrics show improved portfolio completion rate,
3. no regression in duplicate suppression or failed-job counts.

### Phase 2 - Completion Contract

Deliver:

1. portfolio-level completion accounting,
2. remaining-work estimate,
3. operator-facing support guidance for run interpretation.

Phase 2 exit criteria:

1. operators can tell how many portfolios are complete versus incomplete,
2. the system can distinguish “slow”, “running”, and “stuck” states more clearly,
3. progress reporting is consistent between DB facts, support surfaces, and artifacts.

### Phase 3 - Institutional Completion Gate

Deliver:

1. repeatable institutional-scale completion scenario in readiness automation,
2. gate on bounded completion lag plus evidence-pack generation.

Phase 3 exit criteria:

1. the scenario is repeatable,
2. final evidence is customer-grade,
3. the platform can support approval-grade statements about institutional load completion.

### Phase 4 - Documentation, Agent Context, Skill Guidance, and Branch Hygiene

Deliver:

1. documentation updates for any changed operational truth, support flows, or runbooks,
2. explicit review of repository and platform context that should change because of the work,
3. explicit review of Lotus skill and guidance improvements that would make similar future work faster or more reliable,
4. removal or correction of stale guidance where the implementation exposed misleading or missing instructions,
5. branch and artifact hygiene so the RFC closes in a clean, reviewable, governable state.

Mandatory assessment areas:

1. whether `REPOSITORY-ENGINEERING-CONTEXT.md` should change,
2. whether `lotus-platform/context/` should change,
3. whether any Lotus skill instructions should be added, tightened, or removed,
4. whether any documentation should be removed because it creates confusion or duplicates better sources,
5. whether “no context or skill change required” is the truthful conclusion after explicit review.

Phase 4 exit criteria:

1. documentation truth is aligned with the implemented runtime and operator workflow,
2. context and skill changes are either implemented or consciously declined with rationale,
3. no known temporary branch-only guidance remains undocumented,
4. the final implementation slice leaves the branch in a reviewable and operationally coherent state.

## Test and Validation Evidence Required

1. unit tests for run-progress calculation,
2. unit tests for interruption-safe artifact emission,
3. integration tests for progress support/control-plane queries,
4. integration or repository-level tests for portfolio completion accounting,
5. repeated smoke load scenarios proving partial and final artifact generation,
6. at least one rerun of the `1000 x 100` institutional scenario after implementation with:
   - full ingestion,
   - full portfolio coverage,
   - no failed jobs,
   - final evidence pack,
   - truthful elapsed-time reporting,
7. documentation and context review evidence showing that:
   - changed runbooks were updated where needed,
   - relevant repository or platform context was updated where needed,
   - skill guidance updates were either implemented or consciously declined.

## Risks and Mitigations

1. Risk: increased concurrency introduces duplicate work or race conditions.  
   Mitigation: preserve RFC 024 and RFC 081 stage invariants; add focused regression coverage before changing concurrency.

2. Risk: progress telemetry becomes a second inconsistent truth source.  
   Mitigation: derive from durable stage/job facts or update atomically from orchestrated transitions.

3. Risk: partial artifact generation is confused with successful completion.  
   Mitigation: explicit terminal states `complete`, `incomplete`, `failed`, `aborted`.

4. Risk: support/control-plane progress endpoints become expensive under load.  
   Mitigation: use bounded run-scoped queries, indexed progress tables or deterministic aggregates, and do not expose unbounded list semantics by default.

## Rollout and Backward Compatibility

1. Phase 0 is additive and should not affect existing downstream contracts.
2. Phase 1 changes must remain internal to scheduling, orchestration, and supportability paths unless a separate contract change is explicitly approved.
3. Any new support/control-plane surface must follow existing governance and vocabulary standards and avoid introducing legacy aliases.

## Open Questions

1. Should run-progress telemetry be persisted directly by orchestration services or derived from existing durable stage and job tables?
2. Should the long-term operator surface be a support endpoint, a reporting endpoint, or both?
3. Should the institutional completion gate become part of RFC 066 readiness automation or remain a dedicated heavy validation workflow?
4. Should the Lotus RFC standard itself be updated so every RFC includes a final documentation/context/branch-hygiene slice by default?

## Approval Requested

Approval is requested for the following implementation order:

1. Phase 0 immediately,
2. Phase 1 only after telemetry is in place and baseline measurements are captured,
3. Phase 2 and Phase 3 after throughput evidence shows the correct next hardening path,
4. Phase 4 before RFC closure so documentation, context, skills, and branch hygiene are treated as first-class deliverables.

This ordering is deliberate. It minimizes the chance of making the system faster while remaining operationally opaque.

## Next Actions

1. Approve RFC 086.
2. Capture the first post-Phase-0 institutional run with partial and final artifact support.
3. Use that evidence to prioritize the exact Phase 1 throughput changes.
4. Implement Phase 1 in small, test-backed slices with before/after timing evidence.
5. Perform the explicit documentation/context/skills review required by Phase 4 before declaring the RFC complete.
