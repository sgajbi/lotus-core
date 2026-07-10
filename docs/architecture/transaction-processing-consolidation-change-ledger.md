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
- `partial`: a measured risk is reduced, but cutover evidence or migration work remains.
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
| One SQLAlchemy session/commit and combined idempotency fence | implemented-local | CR-1436 provides atomic rollback; CR-1491 adds versioned domain identity, content fingerprint, physical/semantic duplicate classification, and material-conflict rejection. |
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
| Duplicate replay semantic parity | implemented-local | CR-1491 supersedes CR-1455's offset-oriented processed-event expectation: distinct replay offsets preserve one semantic claim, one cashflow/final position state, and one compatibility processed fact; governed replay audit remains separate. |
| Inline backdated position epoch rebuild | implemented-local | CR-1456; target path advances the fenced epoch and rebuilds ordered current history atomically without a stranded legacy replay topic; deployed queue mode is preserved. |
| Worker runtime component task identity | implemented-local | CR-1457; bounded group/topic consumer task names plus stable dispatcher/server names make combined runtime failures attributable. |
| Combined health and image-metadata runtime contract | implemented-local | CR-1458; actual target app proves DB/Kafka/runtime fail-closed readiness and `/version` parity for commit, branch, timestamp, repo, version, digest, CI run, and OCI labels. |
| Target manager final topology default | implemented-local | CR-1459; starting the undeployed target selects one live and one replay-request consumer with explicit dependency injection; legacy six-consumer registry is no longer its default. |
| Target image package and CI release enrollment | implemented-local | CR-1460; bounded source closure avoids legacy wheel collisions, runs non-root, carries OCI/version metadata, and enters CI prebuild/release/Dependabot inventories. Release evidence is pending. |
| Bounded module outcome and latency metrics | implemented-local | CR-1461; observer port plus Prometheus adapter attributes live/replay, idempotency, cost, cashflow, position, and commit outcomes without business-identifier labels. |
| Target health-only security coverage | implemented-local | CR-1462; explicit shared-bootstrap, no-business-route, payload/upload, and unauthenticated operational allowlist contract with focused proof. |
| Batched effective-dated cost FX reads | implemented-local | CR-1466; full-history replay performs one indexed seed-plus-window query per normalized currency pair and maps persistence rows to immutable domain records. |
| Constant-time FIFO available quantity | implemented-local | CR-1467; validated BUY/SELL mutations maintain exact aggregate quantity without rescanning open lots, with an iteration-forbidden invariant and reproducible long-history profile. |
| Linear AVCO source allocation | implemented-local | CR-1468; lazy quantity and local/base basis scales preserve exact pooled residuals without per-disposal source scans. |
| Ordered cost append checkpoint | implemented-local | CR-1471; a versioned canonical watermark permits strict ordered appends from durable open-lot state and forces full replay for missing, incompatible, same-order, backdated, or unsupported state. |
| Bounded FIFO disposal restoration | implemented-local | CR-1473; ordered FIFO consumption streams only quantity-covering source lots, updates that explicit subset, fails on missing selected state, and leaves omitted later lots unchanged. Rebuilds and basis transfers retain complete snapshots. |
| Bounded AVCO pool restoration | implemented-local | CR-1479; ordered AVCO acquisition/disposal restores one versioned aggregate source, reconciles every externally visible source row with set-based exact-residual SQL, and atomically rolls back pool/source/downstream effects on failure. |
| Historical AVCO reconciliation command | implemented-local | CR-1480; bounded keyset dry-run/apply replays canonical history, reconstructs missing/stale sources in chunks, certifies replay/source/pool/count parity, isolates each key transactionally, and emits resumable machine-readable evidence. Production-estate execution remains pending. |
| AVCO database capacity evidence | implemented-local | CR-1481; ordered disposal uses five cost-state statements for both 2 and 200 sources, materializes no source rows, uses the normalized composite index, and locks only the portfolio/security pool key. Deployed latency/pool evidence remains pending. |
| Kafka drain and replay execution controls | implemented-local | CR-1482; two-phase shutdown drains active work before Kafka close, supervision honors configured drain budgets, live/replay profiles are independently composed, and the real replay consumer proves partition order, backlog pressure, ordered commits, and drain. |
| Committed Kafka partition lag | implemented-local | CR-1483; successful normal and DLQ commits set bounded group/topic/partition lag from cached high watermarks without a broker query or business labels; telemetry failures cannot change processing. |
| Async database pool state | implemented-local | CR-1484; successful readiness checks sample configured capacity, checked-in, checked-out, and normalized overflow from the in-process async pool without an extra database query or readiness coupling. |
| Transaction-processing dashboard | implemented-local | CR-1485; one focused app-local dashboard covers separate live/replay lag, stage p95/failures, async pool state, and outbox backlog. Threshold alerts remain evidence-gated. |
| Mixed corporate-action cash economics | implemented-local | CR-1472; true cash consideration carries allocated local/base basis, realized capital/FX/total P&L, `CORPORATE_ACTION_PROCEEDS`, linked cash settlement, target-plus-cash basis reconciliation, and combined PostgreSQL rollback proof. |
| Cash-in-lieu fractional ledger parity | implemented-local | CR-1486; explicit fractional local/base basis equals consumed lots, capital/FX/total P&L reconciles, product/cash flows sum to zero, cashflow classification is TRANSFER rather than income, and linked cross-currency ADJUSTMENT receives effective FX/base basis. |
| Atomic runtime manifest cutover | implemented-local | CR-1487; exact Kafka live/replay offset handoff, one Compose/CI/Kubernetes worker, one Prometheus scrape, one live/replay KEDA scaler, project-independent load diagnostics, completed transaction load/recovery evidence, and clean bank-day downstream tie-out. Registry publication and cluster rollout remain pending. |

## Required Before Runtime Cutover

| Surface | Status | Required change | Removal/cutover prerequisite |
|---|---|---|---|
| Concrete BUY/SELL and multi-leg behavior | implemented-local | Baseline FIFO partial disposal is implemented in CR-1442; fee-aware full disposal in CR-1443; effective-dated cross-currency valuation in CR-1444; AVCO source/pool reconciliation in CR-1448; FIFO multi-lot selection in CR-1449; mixed demerger cash basis/P&L/linkage in CR-1472; and cross-currency cash-in-lieu product/cash parity in CR-1486. | Retain all paths through deployed load/recovery and canonical cutover proof. |
| Backdated cost correction persistence | implemented-local | CR-1463 atomically persists the deterministic affected suffix while publishing only the incoming event; CR-1464 proves FIFO, AVCO, fee-bearing multi-lot, cross-currency local/base, rollback, position epoch/basis, fee cardinality, and event count. | Runtime capacity and cutover gates remain; no stale future cost rows remain in the governed variants. |
| Replay request path | implemented-local | CR-1450 through CR-1456 implement the layered path, duplicate parity, and target inline backdated epoch rebuild. CR-1482 adds independently composed live/replay profiles plus actual replay partition-order, bounded-backlog, ordered-commit, and graceful-drain proof. Shared/target tests cover publisher partial failure, flush timeout, retry exhaustion, DLQ, and offset handling. | Retain these tests through deployment cutover and prove deployed lag recovery and restart drain. |
| Historical AVCO lot evidence | partial | CR-1479 establishes current aggregate state for new processing. CR-1480 adds idempotent, bounded, replay-derived audit/apply with row-count/value certification and PostgreSQL rollback proof. Execute it against the production-like estate before treating tax-lot source products as current after cutover. | Reviewed dry-run/apply reports show no failed/drifted keys and source-product supportability evidence passes. |
| Cost-history runtime complexity | partial | CR-1466 removes the FX N+1 pattern; CR-1467 removes FIFO availability scans; CR-1468 makes AVCO source allocation linear; CR-1471 removes full-history replay from strictly ordered safe appends; CR-1473/CR-1479 bound FIFO/AVCO restoration; CR-1481 proves constant ordered-AVCO round trips, normalized index use, and key-scoped locking locally. At 8,000 rows, FIFO and AVCO disposal each restore 1 source at 0.065ms and 0.086ms respectively; backdated rebuild remains a complete 8,001-row operation. | End-to-end deployed load evidence meets target without weakening deterministic replay; measure DB/Kafka p50/p95/p99, pool wait/utilization, lag, recovery, and drain. |
| Throughput and capacity | partial | CR-1471 adds deterministic engine-only modes; CR-1482 proves bounded replay ordering/drain; CR-1487 fixes the false submission-only and failure-recovery gates, records clean completed-domain throughput/drain plus exact bank-day downstream tie-out, and proves a 100-record target interruption grows committed live lag exactly before full cost/cashflow/position/claim recovery with zero live/replay lag and no added DLQ event. Still measure p50/p95/p99, pool wait/utilization, shutdown-under-load, and a reviewed three-service comparison. | No material regression; bounded in-flight and per-portfolio ordering proven. |
| Aggregate observability | partial | CR-1457 makes task exits attributable, CR-1458 proves readiness/build metadata, CR-1461 adds bounded module outcome/error/latency metrics, CR-1483 adds committed partition lag, CR-1484 adds async DB pool state, and CR-1485 adds the focused app-local dashboard. Shared outbox gauges expose pending, retry-eligible, retry-waiting, terminal-failed, and oldest-pending state. Add trace export, evidence-based alerts, platform dashboard publication, and final support runbook. | Observability contract and failure-injection tests pass. |
| Target image | required | CR-1460 adds the bounded non-root image, dependency definition, OCI/version metadata, and CI release enrollment. Rebuild from the committed SHA and obtain the CI release evidence. | Image SHA label/tag, repo/branch/build/run metadata, digest manifest, SBOM, scan, signature, attestation, no build secrets. |
| Compose/runtime manifests | implemented-local | CR-1459 activates two target consumers; CR-1487 uses one digest-capable target image reference and removes all three legacy workers atomically from app-local Compose. Exact offset handoff prevents retained-history replay. | Registry/Kubernetes deployment, canonical QA, and rollback proof pass. |
| Kubernetes/KEDA | implemented-local | CR-1487 adds a digest-only hardened target Deployment/ServiceAccount/Service/PDB and replaces three legacy calculator scalers with one target live/replay scaler. The CI renderer fails closed unless one target release manifest proves SBOM, passed scan, signing, provenance, digest deployment, and same-image dev/UAT/prod promotion. | Registry artifact, server-side manifest validation, partition/lag/DB-pool/resource/disruption evidence, controlled rollout, and rollback pass. |
| Prometheus and dashboards | partial | CR-1487 replaces three app-local scrape jobs with one target job; CR-1485 supplies the module-aware dashboard. Platform publication and evidence-based alerts remain. | Dashboard/alert/runbook links validated. |
| CI service inventories | implemented-local | CR-1460 enrolls the target; CR-1465 adds the blocking PostgreSQL suite; CR-1487 removes all three legacy workers from runtime, prebuild, and image-release inventories and emits the target digest-pinned Kubernetes artifact. | GitHub image/release and mainline runtime gates pass. |
| Dependency automation | required | Replace three Dependabot package roots and stale `pyproject.toml` source roots with the target ownership layout. | Legacy roots deleted and lock/import checks pass. |
| OpenAPI worker surfaces | required | Replace three worker health OpenAPI registrations with the target worker surface. | OpenAPI quality/vocabulary gates pass. |
| Load/support scripts | implemented-local | CR-1487 centralizes valid source fixtures and exact domain-completion probes, bounds fixtures to the run date, resolves logs by Compose project/service, and measures committed target-group lag rather than ingestion backlog. Clean fast load, unified failure recovery, and bank-day DB/API/log tie-out passed. | Retain through full load, shutdown-under-load, canonical QA, and platform publication. |

## Compatibility Surfaces To Retire

| Surface | Status | Intended action | Removal prerequisite |
|---|---|---|---|
| Target six-consumer compatibility registry and tests | removed-local | Deleted after two-consumer composition, atomic rollback, replay, load, recovery, Compose, CI, and Kubernetes manifest proof. Import confinement remains enforced for transitional infrastructure adapters. | Do not restore; retain historical CR evidence only. |
| Cost/cashflow/position `main.py`, `consumer_manager.py`, and `web.py` shells | removed-local | Deleted after target health/runtime, Compose, CI, OpenAPI, security, image, and Kubernetes ownership switched. | Do not restore; target is the only worker HTTP/runtime identity. |
| Three calculator Dockerfiles, standalone package manifests, and cashflow `requirements.txt` | removed-local | Deleted; prebuild, image release, and Dependabot now track only the target transaction worker. | Do not restore overlapping standalone packages or images. |
| Legacy normal/replay delivery classes | partial | Position normal delivery and cost replay-request delivery are deleted. CR-1489 and CR-1490 isolate active cost and cashflow workflows; both compatibility consumers are confined and absent from target imports. | Migrate legacy delivery-hosted domain tests, then delete both compatibility consumers while retaining target delivery, replay, and image proof. |
| Legacy cost/cashflow/position package roots | compatibility | Move surviving domain policies, ports, repositories, and tests into clear target module packages; then delete empty roots. | Import graph, ownership catalog, tests, and docs updated. |
| Old consumer groups and processed-event service identities | compatibility | Stop producing new rows/lag; retain historical data until governed retention expires. | Deployment cutover, lag zero, support sign-off. |
| `transaction_processing.ready` normal stage gate | partial | CR-1488 removed the target-path consumer and two-event wait; retain compatibility publication until downstream usage is certified. | Every downstream consumer uses combined completion/compatible domain events. |
| `transactions.cost.processed` as normal fan-out carrier | compatibility | Retain compatibility emission initially; retire normal-path use after downstream migration. | Pipeline/query/idea/workbench and replay consumers no longer depend on it. |
| Pipeline orchestrator transaction-stage subscriptions/state | partial | CR-1488 removed cashflow subscription/readiness coordination; retain one atomic completion subscription and unrelated portfolio aggregation/reconciliation orchestration. | Downstream audit permits readiness-topic and historical stage-state retirement. |
| Legacy worker ports, service names, alerts, dashboards, and runbooks | partial | Compose, CI, OpenAPI, security, image, Kubernetes, KEDA, dashboard, and primary runbook identities use the target. Search and retire remaining feature-doc/history references without rewriting historical CR evidence. | Operations/support validation and post-cutover observation window. |

## Database Decisions

| Structure | Status | Decision |
|---|---|---|
| `transactions` | retain | Canonical ingestion-owned transaction record; required before `transactions.persisted`. |
| `transaction_costs`, position-lot, and accrued-offset state | retain | Cost/lot audit and financial calculation invariants. |
| `average_cost_pool_state` | retain | Versioned, transactionally owned AVCO aggregate used for bounded ordered restoration; it complements rather than replaces externally visible source-lot evidence. |
| `cashflows` and `cashflow_rules` | retain | Cashflow fact/rule lineage, timing, and classification invariants. |
| `position_history`, `position_state`, daily snapshots | retain | Ordered position, epoch, replay, and valuation materialization invariants. |
| Shared `outbox_events` and `processed_events` tables | retain | Atomic publication and idempotency; consolidate service identities, not tables. |
| Transaction-stage rows/keys in pipeline stage state | candidate | Remove/archive only after normal stage gate is retired and historical/support requirements are defined. |
| Historical AVCO `position_lot_state` rows | candidate | Backfill rather than remove: prior processing may have zeroed open quantities despite positive pooled holdings. Preserve lineage and prove aggregate quantity/cost reconciliation. |
| Duplicate indexes, stale service-specific columns, or compatibility tables discovered during move | candidate | Require query-usage evidence, explain plans, migration/backfill, rollback, and downstream checks before removal. |

## Documentation And Contract Closure

| Surface | Status | Required change |
|---|---|---|
| README and supported architecture docs | partial | App-local/CI/Kubernetes two-consumer runtime, module ownership, port, offset handoff, digest rendering, and current pending registry/cluster work are published in CR-1487. Final production truth follows controlled rollout and legacy removal. |
| Repo-local wiki | required | Replace Cost/Cashflow/Position service pages with target module/runtime truth; retain methodology and troubleshooting depth. |
| Current-state architecture and trigger matrix | implemented-local | CR-1488 records one atomic completion input and dormant compatibility facts. |
| RFC-0081/RFC-0083 and event contracts | implemented-local | CR-1488 records the superseded two-event stage topology while preserving compatibility windows and replay semantics. |
| Event supportability/test pack | required | Remove obsolete producer/consumer ownership only after topic retirement; preserve valid domain-event contracts. |
| Repository context and modularity catalog | required | Mark legacy roots removed and target architecture fully adopted. |
| GitHub issue #468 | required | Move to fixed-local only after every required prerequisite is locally proven; close only after merged/mainline validation. |

## Explicit Non-Goals

- Do not merge valuation into transaction processing.
- Do not collapse distinct financial domain tables merely because runtime shells are consolidated.
- Do not delete compatibility topics, events, groups, or stage state before downstream migration.
- Do not weaken business, replay, integration, load, security, provenance, or observability tests.
- Do not open the final PR while required issue scope remains unproven locally.
