# Transaction Processing Consolidation Change Ledger

Status: Active  
Owner: `lotus-core`  
Issue: #468  
Last reviewed: 2026-07-10

This ledger is the durable cutover/removal inventory for consolidating cost, cashflow, and position
processing. An item may move to `removed` only after its prerequisite evidence is committed. Business
tests move with their owning module; they are not deleted merely because a service shell is removed.

## Status Vocabulary

- `implemented-local`: target replacement exists and has focused proof.
- `required`: must change before target runtime cutover.
- `compatibility`: retain until downstream/replay parity permits removal.
- `candidate`: investigate usage and migration impact before deciding.
- `retain`: intentional long-term boundary; do not remove as consolidation cleanup.
- `removed`: deleted with evidence and downstream validation.

## Implemented Target

| Surface | Status | Evidence / next condition |
|---|---|---|
| Target layered package (`delivery -> application -> domain/ports -> infrastructure -> runtime`) | implemented-local | CR-1430 through CR-1440; architecture guards pass. |
| Framework-neutral booked transaction and one DTO mapping boundary | implemented-local | CR-1431; 98-field drift and round-trip tests. |
| One `ProcessTransactionUseCase` | implemented-local | CR-1432; ordered cost/cashflow/position execution. |
| Cost, cashflow, and position caller-owned adapters | implemented-local | CR-1433 through CR-1435. |
| One SQLAlchemy session/commit and combined idempotency fence | implemented-local | CR-1436; unit and PostgreSQL rollback proof. |
| Plain cost and cashflow workflows independent of Kafka delivery | implemented-local | CR-1437 and CR-1438. |
| One final normal-path consumer and governed dependency builder | implemented-local | CR-1439 and CR-1440; not registered yet. |
| Concrete combined `ADJUSTMENT` database parity and duplicate proof | implemented-local | CR-1441. |
| Concrete ordered BUY/SELL, fee, and full-disposal database parity | implemented-local | CR-1442 and CR-1443; FIFO partial/full disposal, fee rows, cashflows, positions, and duplicate proof. |
| Concrete effective-dated cross-currency database parity | implemented-local | CR-1444; latest-on-or-before FX selection and local/base values across transaction, lot, position, fee, and cashflow. |
| Shared combined integration support and domain-variant test layout | implemented-local | CR-1445; canonical persistence/event ordering has one helper and scenario modules are 134-179 lines. |
| AVCO source-quantity reconciliation | implemented-local | CR-1446; pro-rata source quantities reconcile exactly to pooled holdings instead of falsely closing every lot. |
| Typed remaining lot-state reconciliation | implemented-local | CR-1447; quantity and local/base remaining cost move together from strategy through persistence. |
| Concrete combined AVCO source/pool database parity | implemented-local | CR-1448; two acquisitions and one disposal reconcile policy, COGS, gain, source lots, cashflows, positions, and duplicate behavior. |
| Concrete combined FIFO multi-lot database parity | implemented-local | CR-1449; oldest source closes before partial next-source consumption with exact quantity/cost reconciliation. |
| Framework-neutral booked-transaction replay application boundary | implemented-local | CR-1450; normalized command, explicit result, and narrow replay port without delivery/infrastructure dependencies. |
| Canonical booked-transaction replay infrastructure adapter | implemented-local | CR-1451; short-lived SQLAlchemy session, canonical replayer delegation, correlation propagation, and zero/one cardinality enforcement. |
| Booked-transaction replay production composition | implemented-local | CR-1452; named canonical repository factory, shared producer, fresh request session, and explicit dependency injection. |
| Booked-transaction replay request delivery boundary | implemented-local | CR-1453; delivery DTO/mapper, one use-case-only consumer, correlation precedence, explicit outcomes, and shared bounded retry/DLQ policy. |
| Final two-consumer runtime composition | implemented-local | CR-1454; one live and one replay-request consumer, one composed use case each, canonical topics/groups, and no activation beside legacy consumers. |
| Duplicate replay semantic parity | implemented-local | CR-1455; distinct replay offsets preserve one cashflow/final position state, two delivery audits, and one required compatibility processed event per replay. |
| Inline backdated position epoch rebuild | implemented-local | CR-1456; target path advances the fenced epoch and rebuilds ordered current history atomically without a stranded legacy replay topic; deployed queue mode is preserved. |
| Worker runtime component task identity | implemented-local | CR-1457; bounded group/topic consumer task names plus stable dispatcher/server names make combined runtime failures attributable. |
| Combined health and image-metadata runtime contract | implemented-local | CR-1458; actual target app proves DB/Kafka/runtime fail-closed readiness and `/version` parity for commit, branch, timestamp, repo, version, digest, CI run, and OCI labels. |
| Target manager final topology default | implemented-local | CR-1459; starting the undeployed target selects one live and one replay-request consumer with explicit dependency injection; legacy six-consumer registry is no longer its default. |
| Target image package and CI release enrollment | implemented-local | CR-1460; bounded source closure avoids legacy wheel collisions, runs non-root, carries OCI/version metadata, and enters CI prebuild/release/Dependabot inventories. Release evidence is pending. |
| Bounded module outcome and latency metrics | implemented-local | CR-1461; observer port plus Prometheus adapter attributes live/replay, idempotency, cost, cashflow, position, and commit outcomes without business-identifier labels. |
| Target health-only security coverage | implemented-local | CR-1462; explicit shared-bootstrap, no-business-route, payload/upload, and unauthenticated operational allowlist contract with focused proof. |

## Required Before Runtime Cutover

| Surface | Status | Required change | Removal/cutover prerequisite |
|---|---|---|---|
| Concrete BUY/SELL and multi-leg behavior | required | Baseline FIFO partial disposal is implemented in CR-1442; fee-aware full disposal in CR-1443; effective-dated cross-currency valuation in CR-1444; AVCO source/pool reconciliation in CR-1448; FIFO multi-lot selection in CR-1449. Add explicit cross-currency cash legs and multi-leg behavior. | Existing transaction contract packs and all remaining combined parity paths pass. |
| Backdated cost correction persistence | implemented-local | CR-1463 atomically persists the deterministic affected suffix while publishing only the incoming event; CR-1464 proves FIFO, AVCO, fee-bearing multi-lot, cross-currency local/base, rollback, position epoch/basis, fee cardinality, and event count. | Runtime capacity and cutover gates remain; no stale future cost rows remain in the governed variants. |
| Replay request path | required | CR-1450 through CR-1456 implement the path, duplicate parity, and target inline backdated epoch rebuild without activation. Existing shared/target tests cover publisher partial failure, flush timeout, retry exhaustion, DLQ, and offset handling. Add explicit ordering, throttle, and backlog proof. | Replay ordering, duplicate, partial-publish, epoch, throttle, and backlog tests pass. |
| Historical AVCO lot evidence | required | Reconcile/backfill existing AVCO `position_lot_state` open quantities and current cost bases before treating tax-lot source products as current after cutover. | Idempotent migration, row-count/value reconciliation, rollback, and source-product supportability evidence pass. |
| Cost-history runtime complexity | required | Characterize `CostCalculatorRepository.get_transaction_history` full portfolio/security scans under long histories. Introduce incremental state only if FIFO, AVCO, backdated, fee/FX, multi-lot, and corporate-action parity proves identical results. | Query-count/explain/load evidence meets target without weakening deterministic replay; otherwise retain full-history correctness with explicit capacity limits and diagnostics. |
| Throughput and capacity | required | Measure events/second, p50/p95/p99, DB pool utilization, query count, Kafka lag, failure recovery, and shutdown drain against three-service baseline. | No material regression; bounded in-flight and per-portfolio ordering proven. |
| Aggregate observability | partial | CR-1457 makes task exits attributable, CR-1458 proves readiness/build metadata, and CR-1461 adds bounded module outcome/error/latency metrics. Add consumer lag, DB/Kafka/outbox diagnostics, traces, dashboard/alerts, and final support runbook. | Observability contract and failure-injection tests pass. |
| Target image | required | CR-1460 adds the bounded non-root image, dependency definition, OCI/version metadata, and CI release enrollment. Rebuild from the committed SHA and obtain the CI release evidence. | Image SHA label/tag, repo/branch/build/run metadata, digest manifest, SBOM, scan, signature, attestation, no build secrets. |
| Compose/runtime manifests | required | CR-1459 activates two consumers inside the target package only. Add the target service by digest-capable image reference and remove three runtime services atomically; never run both topologies together. | Canonical QA and rollback deployment proof pass. |
| Kubernetes/KEDA | required | Replace calculator scaled objects/deployments with target live/replay consumer scaling policy. | Partition, lag, DB pool, resource, disruption, and rollback evidence pass. |
| Prometheus and dashboards | required | Replace three scrape jobs/service alerts with one aggregate job plus module labels. | Dashboard/alert/runbook links validated. |
| CI service inventories | partial | CR-1460 enrolls prebuild/image release; CR-1465 adds the blocking manifest/Make PR and main PostgreSQL contract suite. Compose-backed service sets intentionally retain legacy workers until atomic cutover. | During deployment cutover, add the target and remove all three legacy workers from Docker/E2E/latency/performance/failure-recovery sets together; GitHub image/release gates pass. |
| Dependency automation | required | Replace three Dependabot package roots and stale `pyproject.toml` source roots with the target ownership layout. | Legacy roots deleted and lock/import checks pass. |
| OpenAPI worker surfaces | required | Replace three worker health OpenAPI registrations with the target worker surface. | OpenAPI quality/vocabulary gates pass. |
| Load/support scripts | required | Update `bank_day_load_scenario.py`, seed diagnostics, service names/ports, and operational probes. | Canonical load and support diagnostics pass. |

## Compatibility Surfaces To Retire

| Surface | Status | Intended action | Removal prerequisite |
|---|---|---|---|
| `app/infrastructure/legacy_consumer_registry.py` and six-consumer tests | compatibility | Delete when target manager is switched to one live plus one replay-request consumer. | Combined live/replay and rollback proof. |
| Cost/cashflow/position `main.py`, `consumer_manager.py`, and `web.py` shells | compatibility | Delete service shells; retain/move business modules and tests under target ownership. | Target health/runtime parity and manifest switch. |
| Three calculator Dockerfiles and cashflow `requirements.txt` | compatibility | Delete after one target image is released and deployable by digest. | Image provenance/security and rollback proof. |
| Normal cost, cashflow, gated-position, and cost-processed replay consumer classes | compatibility | Delete after target live/replay consumers own delivery. | Topic/group/downstream parity and replay proof. |
| Legacy cost/cashflow/position package roots | compatibility | Move surviving domain policies, ports, repositories, and tests into clear target module packages; then delete empty roots. | Import graph, ownership catalog, tests, and docs updated. |
| Old consumer groups and processed-event service identities | compatibility | Stop producing new rows/lag; retain historical data until governed retention expires. | Deployment cutover, lag zero, support sign-off. |
| `transaction_processing.ready` normal stage gate | compatibility | Remove target-path production/consumption and transaction-stage wait from pipeline orchestrator. | Every downstream consumer uses combined completion/compatible domain events. |
| `transactions.cost.processed` as normal fan-out carrier | compatibility | Retain compatibility emission initially; retire normal-path use after downstream migration. | Pipeline/query/idea/workbench and replay consumers no longer depend on it. |
| Pipeline orchestrator transaction-stage subscriptions/state | compatibility | Remove only transaction cost/cashflow readiness coordination; retain unrelated portfolio aggregation/reconciliation orchestration. | Stage ownership/downstream audit and migration plan. |
| Legacy worker ports, service names, alerts, dashboards, and runbooks | compatibility | Replace with target aggregate identity and module dimensions. | Operations/support validation and post-cutover observation window. |

## Database Decisions

| Structure | Status | Decision |
|---|---|---|
| `transactions` | retain | Canonical ingestion-owned transaction record; required before `transactions.persisted`. |
| `transaction_costs`, position-lot, and accrued-offset state | retain | Cost/lot audit and financial calculation invariants. |
| `cashflows` and `cashflow_rules` | retain | Cashflow fact/rule lineage, timing, and classification invariants. |
| `position_history`, `position_state`, daily snapshots | retain | Ordered position, epoch, replay, and valuation materialization invariants. |
| Shared `outbox_events` and `processed_events` tables | retain | Atomic publication and idempotency; consolidate service identities, not tables. |
| Transaction-stage rows/keys in pipeline stage state | candidate | Remove/archive only after normal stage gate is retired and historical/support requirements are defined. |
| Historical AVCO `position_lot_state` rows | candidate | Backfill rather than remove: prior processing may have zeroed open quantities despite positive pooled holdings. Preserve lineage and prove aggregate quantity/cost reconciliation. |
| Duplicate indexes, stale service-specific columns, or compatibility tables discovered during move | candidate | Require query-usage evidence, explain plans, migration/backfill, rollback, and downstream checks before removal. |

## Documentation And Contract Closure

| Surface | Status | Required change |
|---|---|---|
| README and supported architecture docs | required | Publish final two-consumer runtime, module ownership, commands, ports, and operational model after cutover. |
| Repo-local wiki | required | Replace Cost/Cashflow/Position service pages with target module/runtime truth; retain methodology and troubleshooting depth. |
| Current-state architecture and trigger matrix | required | Update runtime owners, topics, stage gate, replay, tables, and scaling decisions. |
| RFC-0081/RFC-0083 and event contracts | required | Record superseded normal stage topology while preserving truthful compatibility windows and replay semantics. |
| Event supportability/test pack | required | Remove obsolete producer/consumer ownership only after topic retirement; preserve valid domain-event contracts. |
| Repository context and modularity catalog | required | Mark legacy roots removed and target architecture fully adopted. |
| GitHub issue #468 | required | Move to fixed-local only after every required prerequisite is locally proven; close only after merged/mainline validation. |

## Explicit Non-Goals

- Do not merge valuation into transaction processing.
- Do not collapse distinct financial domain tables merely because runtime shells are consolidated.
- Do not delete compatibility topics, events, groups, or stage state before downstream migration.
- Do not weaken business, replay, integration, load, security, provenance, or observability tests.
- Do not open the final PR while required issue scope remains unproven locally.
