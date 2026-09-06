# Repository Engineering Context

This is the repository-local engineering context for `lotus-core`. It describes current
ownership, architecture, invariants, task routes, commands, and completion evidence. Active work
and PR status belong in GitHub; historical delivery belongs in RFC and review evidence.

Read [AGENTS.md](AGENTS.md), the Platform
[quickstart](https://github.com/sgajbi/lotus-platform/blob/main/context/LOTUS-QUICKSTART-CONTEXT.md),
and this file first. Then use the Platform
[skill routing map](https://github.com/sgajbi/lotus-platform/blob/main/context/LOTUS-SKILL-ROUTING-MAP.md)
and the task routes below to load only relevant specialist context.

## Repository Role

`lotus-core` is the authoritative financial system of record for foundational portfolio,
account, holding, mandate, transaction, position, cash, valuation, cashflow, and historical state
used by the Lotus ecosystem.

Core owns source facts and their financial, temporal, tenant, lineage, audit, replay, and recovery
semantics. Downstream services consume those governed facts; they must not reconstruct competing
Core truth.

## Business And Domain Responsibility

Core owns:

1. tenant-owned portfolio, account, holding, instrument, mandate, and transaction records;
2. source ingestion, validation, persistence, and correction lineage;
3. supported transaction and corporate-action economic effects;
4. dated positions, cash, valuation, cashflow, and time-series foundations;
5. source-data products and operational, analytics-input, lineage, policy, support, snapshot,
   simulation, and export contracts;
6. reconciliation, idempotency, fencing, replay, reprocessing, and recovery evidence.

Core does not own performance or risk conclusions, advisory recommendations, mandate decisions,
client report composition, or the unified front-office experience. Those remain with their
respective Lotus services.

## Current-State Summary

- `query_service` is the operational read plane.
- `query_control_plane_service` owns governed analytics-input, source-product, lineage, policy,
  support, snapshot, simulation, and export contracts.
- `ingestion_service` owns HTTP/source adapters and delegates write lifecycle orchestration to
  application commands rather than routers.
- `portfolio_transaction_processing_service` is the combined app-local and CI runtime for atomic
  cost, cashflow, position, and transaction-readiness effects. Valuation remains independently
  scalable.
- `portfolio_derived_state_service` materializes position and portfolio time series and owns
  aggregation scheduling; `financial_reconciliation_service` owns reconciliation lifecycle and
  durable control evidence.
- `event_replay_service` owns DLQ, replay, ingestion-health, audit, and remediation operations.
- Tenant ownership is a durable root invariant; production ingress and jobs must fail closed when
  verified ownership is absent or mismatched.
- Source-effective valuation readiness is tied to current source facts, valuation epoch, and
  reconciliation state. Benign bookkeeping cannot invalidate unchanged facts; reprocessing,
  changed facts, or epoch mismatch cannot reuse stale evidence.
- Source-data product declarations, feature status, route families, RFC status, and runtime
  validation are machine-checked. A declaration or local test is not production certification.

Current implementation status is maintained in the
[supported-feature contract](contracts/supported-features/lotus-core-supported-features.v1.json),
[Supported Features](wiki/Supported-Features.md),
[API route catalogue](docs/standards/api-route-catalog.v1.json), and
[RFC status ledger](docs/standards/rfc-status-ledger.v1.json).

## Financial System-Of-Record Invariants

Every Core change must preserve the following:

1. **Exact economics.** Money, quantity, rates, fees, taxes, FX, and cost use governed exact
   numeric semantics and explicit rounding policy.
2. **Temporal truth.** Trade, settlement, booking, effective, observation, valuation, correction,
   and ingestion time are distinct. As-of queries cannot silently switch semantics.
3. **Tenant authority.** One validated source-owned tenant identity flows through request,
   application, persistence, jobs, events, replay, and reads; missing authority fails closed.
4. **Deterministic replay.** The same authoritative inputs, versions, and ordering reproduce the
   same outcome. Corrections preserve earliest affected scope and current lineage.
5. **Idempotency and fencing.** Duplicate delivery, stale leases, old epochs, and superseded jobs
   cannot overwrite newer authoritative state.
6. **Lineage and audit.** Derived values remain attributable to source batches, prices, FX,
   policies, versions, correlations, actors, and decision evidence.
7. **Reconciliation and readiness.** Missing, stale, malformed, mismatched, or unresolved evidence
   returns an explicit unavailable/blocked state; Core does not invent a plausible value.
8. **Operational recovery.** Failure, restart, timeout, poison work, and partial progress reach a
   controlled recoverable or quarantined state without losing financial truth.

## Architecture And Module Map

| Area | Ownership |
| --- | --- |
| `src/services/ingestion_service/` | Source-data and adapter write ingress; command-owned ingestion lifecycle. |
| `src/services/portfolio_transaction_processing_service/` | Atomic cost, cashflow, position, replay, rollback, and readiness effects. |
| `src/services/calculators/` | Independently deployable position valuation. |
| `src/services/valuation_orchestrator_service/` | Valuation scheduling, job lifecycle, reprocessing state, and dispatch. |
| `src/services/portfolio_derived_state_service/` | Position/portfolio time-series materialization and aggregation scheduling. |
| `src/services/financial_reconciliation_service/` | Reconciliation run/finding policy, control evidence, and completion events. |
| `src/services/query_service/` | Operational portfolio, position, transaction, cash, market, and reporting reads. |
| `src/services/query_control_plane_service/` | Analytics-input, snapshot, simulation, source-product, lineage, policy, support, and export contracts. |
| `src/services/event_replay_service/` | Replay, DLQ, ingestion-health, audit, and remediation control plane. |
| `src/libs/portfolio-common/` | Shared financial domain and contract-support primitives; not a dumping ground for service orchestration. |
| `contracts/` | Machine-readable feature, eventing, source-product, security, CI, and trust contracts. |
| `scripts/` | Purpose-owned quality, validation, operations, release, development, and generation automation. |
| `docs/` | Detailed architecture, methodology, standards, features, testing, and operations truth. |
| `wiki/` | Authored source for concise GitHub wiki navigation and operator guidance. |

Use the [current-state architecture map](docs/architecture/current-state-architecture-map.md),
[target architecture](docs/architecture/lotus-core-target-architecture.md),
[architecture index](docs/architecture/README.md), and
[service boundary map](docs/architecture/microservice-boundaries-and-trigger-matrix.md) for deeper
structure and event-flow detail.

## Runtime And Integration Boundaries

1. Core-owned writes enter through governed ingestion or service application boundaries and retain
   source identity, tenant, correlation, and idempotency evidence.
2. PostgreSQL is authoritative persistence. Kafka/outbox paths distribute facts and commands but
   do not replace durable state ownership.
3. `query_service` and `query_control_plane_service` have distinct route families; do not move a
   route or duplicate logic without updating the RFC-0082 registry and consumer evidence.
4. Downstream analytics receive source-owned facts and readiness, not permission to reinterpret
   missing evidence or broaden tenant scope.
5. Local Compose is isolated Core development. Shared infrastructure belongs to Platform; the
   populated integrated front-office runtime belongs to Workbench.
6. Promoted runtime claims require exact image, deployment, dependency, migration, observability,
   IAM, and operational evidence. Local green tests are not that certification.

## Task Routes

| Task | Read next |
| --- | --- |
| Architecture or ownership | [Architecture index](docs/architecture/README.md) and [current-state map](docs/architecture/current-state-architecture-map.md) |
| API or downstream integration | [RFC-0082 inventory](docs/architecture/RFC-0082-contract-family-inventory.md), [API Surface](wiki/API-Surface.md), route catalogue and registry |
| Financial or transaction behavior | [Transaction capability catalogue](contracts/transaction-processing/transaction-capability-catalog.v1.json), relevant transaction RFC, and domain tests |
| Time/as-of semantics | [Temporal vocabulary](docs/standards/temporal-vocabulary.md) and the owning schema/methodology |
| Source-data products | [Source-product catalogue](docs/architecture/RFC-0083-source-data-product-catalog.md), `contracts/domain-data-products/`, and relevant methodology |
| Reconciliation or data quality | [Reconciliation target model](docs/architecture/RFC-0083-reconciliation-data-quality-target-model.md) and recovery runbooks |
| Tenant, security, or audit | [Security/tenancy target model](docs/architecture/RFC-0083-security-tenancy-lifecycle-target-model.md) and [Security and Governance](wiki/Security-and-Governance.md) |
| Migration or PostgreSQL behavior | [Migration contract](docs/standards/migration-contract.md), migration files, and real PostgreSQL proof guidance |
| Replay, jobs, or recovery | [Recovery index](docs/operations/recovery/README.md), [transaction replay standard](docs/standards/transaction-replay-boundary-standard.md), and owning application state machine |
| CI, tests, or quality gates | [Validation and CI](wiki/Validation-and-CI.md), relevant contract under `docs/standards/`, and the repo-native Make target |
| Operations and incidents | [Operations runbook](docs/operations/runbook.md), [observability](docs/operations/observability.md), and incident playbooks |
| Documentation or wiki | [Docs index](docs/README.md), front-door contract, and Platform documentation-layering guidance |

## Repo-Native Commands

Run from the `lotus-core` repository root:

```bash
make install
make ci-local
make ci
make ci-main
make front-door-sync-guard
make quality-wiki-docs-gate
make docs-evidence-pack
make lotus-core-validate
```

Use focused Make targets listed in the [Development Workflow](wiki/Development-Workflow.md) for
fast fix-forward proof. Do not replace a governed target with an ad hoc command that changes the
interpreter, dependency, database, Compose, coverage, or failure-propagation boundary.

## Validation And CI Expectations

Core uses Remote Feature Lane, Pull Request Merge Gate, and Main Releasability Gate. The applicable
lane must pass against the exact implementation SHA.

Tests must prove the economic invariant, edge/failure behavior, replay or idempotency semantics,
and contract meaning—not merely execute lines. Use real PostgreSQL when correctness depends on its
SQL, types, constraints, locks, transactions, or persistence behavior. Concurrency proof must force
the claimed ordering and assert the database observation rather than only synchronizing callers.

Completion requires:

- focused proof plus the applicable repo-native lane;
- no weakened assertions, exclusions, compatibility paths, or hidden command failures;
- resolved blocking review findings after the latest implementation commit;
- updated contract, docs, context, feature, RFC, runbook, and wiki truth where affected;
- wiki publication and strict parity after merge when wiki source changes;
- exact-main validation and clean branch/worktree state;
- GitHub issues reconciled to what remains.

## Standards And RFCs That Govern This Repository

Primary authorities:

1. [RFC-0082 contract-family inventory](docs/architecture/RFC-0082-contract-family-inventory.md)
2. [RFC-0083 target architecture](docs/architecture/lotus-core-target-architecture.md)
3. [Temporal vocabulary](docs/standards/temporal-vocabulary.md)
4. [Application-layer contract](docs/standards/application-layer-contract.md)
5. [Repository transaction boundary](docs/standards/repository-transaction-boundary-standard.md)
6. [Runtime boundary decisions](docs/standards/runtime-boundary-decision-standard.md)
7. [Migration contract](docs/standards/migration-contract.md)
8. [Risk-based test matrix](docs/standards/risk-based-test-coverage-matrix.v1.json)
9. [Critical-path coverage contract](docs/standards/critical-path-coverage.v1.json)
10. [Front-door synchronization contract](docs/standards/front-door-sync.v1.json)

Use the [RFC Index](wiki/RFC-Index.md) for current status. RFC prose does not override current code,
schema, machine-readable contracts, or executable evidence.

## Known Constraints And Implementation Notes

- Some external treasury and OMS source products intentionally remain unavailable until bank-owned
  integration evidence is certified; do not fabricate substitutes.
- Production security and audit defaults do not replace platform ingress, IAM, or deployment proof.
- App-local Compose and CI use checkout-specific ownership. Never disturb the shared canonical
  runtime while validating a branch.
- Generated catalogues and evidence must be regenerated by their owning scripts; do not hand-edit
  derived output.
- Compatibility behavior must have a current consumer and explicit retirement posture. Remove dead
  or obsolete paths rather than preserving them by habit.
- Repository docs must distinguish implemented capability, local validation, mesh certification,
  release evidence, and production availability.

## Context Maintenance Rule

Update this file only when current Core ownership, architecture, financial invariants, task routes,
canonical commands, or completion evidence changes. Keep issue status, PR history, commit diaries,
and temporary blockers in GitHub.

## Cross-Links

1. [README](README.md)
2. [Documentation index](docs/README.md)
3. [Architecture index](docs/architecture/README.md)
4. [Supported Features](wiki/Supported-Features.md)
5. [API Surface](wiki/API-Surface.md)
6. [Operations Runbook](wiki/Operations-Runbook.md)
7. [Validation and CI](wiki/Validation-and-CI.md)
8. [Platform context reference map](https://github.com/sgajbi/lotus-platform/blob/main/context/CONTEXT-REFERENCE-MAP.md)
9. [Platform engineering context](https://github.com/sgajbi/lotus-platform/blob/main/context/LOTUS-ENGINEERING-CONTEXT.md)
