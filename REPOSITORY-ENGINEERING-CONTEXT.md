# Repository Engineering Context

This file provides repository-local engineering context for `lotus-core`.

For platform-wide truth, read:

1. `../lotus-platform/context/LOTUS-QUICKSTART-CONTEXT.md`
2. `../lotus-platform/context/LOTUS-ENGINEERING-CONTEXT.md`
3. `../lotus-platform/context/CONTEXT-REFERENCE-MAP.md`

## Repository Role

`lotus-core` is the authoritative portfolio, booking, account, and transaction platform for Lotus.

It provides the foundational operational and analytical data used by multiple downstream services.

## Business And Domain Responsibility

This repository owns:

1. portfolio and holding master data,
2. booking and transaction data,
3. ingestion and persistence,
4. position, valuation, cashflow, and time-series generation foundations,
5. query-service APIs for operational, integration, and reporting-oriented consumption.

## Current-State Summary

Current repository posture:

1. `lotus-core` is the domain authority for portfolio-management and transaction data,
2. downstream-facing API ownership is now classified under the RFC-0082 contract-family model, with `query_service` as the operational read plane and `query_control_plane_service` as the governed analytics-input, snapshot/simulation, support, and policy contract plane,
3. RFC-0083 now defines the target system-of-record architecture, and the local Slice 0 gap analysis maps current route, model, temporal, source-data product, ingestion, reconciliation, and observability gaps to the implementation program,
4. RFC-0083 Slice 1 now defines repo-local temporal vocabulary and schema policy for as-of, valuation, trade, settlement, booking, effective, ingestion, observation, correction, and restatement semantics,
5. RFC-0083 Slice 2 now enforces route contract-family classification through a machine-readable registry and guard,
6. RFC-0083 Slice 3 now defines the portfolio reconstruction target model and deterministic snapshot identity helper,
7. RFC-0083 Slice 4 now defines the ingestion source-lineage target model and source-batch evidence helper,
8. RFC-0083 Slice 5 now defines the reconciliation/data-quality target model and shared status helper,
9. RFC-0083 Slice 6 now defines the priority source-data product catalog, product metadata requirements, consumer map, paging/export disposition, route metadata bindings, DTO-envelope product identity, HoldingsAsOf runtime data-quality metadata and reporting evidence timestamps, canonical TransactionLedgerWindow runtime evidence timestamp and window-completeness data-quality metadata, PortfolioStateSnapshot runtime metadata, snapshot evidence timestamp, freshness epoch handling, and baseline data-quality classification, analytics-input data-quality classification, market/reference runtime evidence timestamp and data-quality classification, coverage data-quality classification and evidence timestamps, ingestion/reconciliation evidence runtime supportability metadata with reconciliation evidence status derivation, a linted source-data product contract guard, and a `lotus-performance` analytics-input consumer conformance guard,
10. RFC-0083 Slice 7 now defines market/reference quality, observed-at mapping, and freshness/completeness classification for benchmark, index, risk-free, price, FX, and instrument products,
11. RFC-0083 Slice 8 now records endpoint-consolidation disposition and deprecates selected pre-live reporting convenience routes in OpenAPI while preserving tested handlers,
12. RFC-0083 Slice 9 now defines source-data product security, tenancy, entitlement, capability, audit, sensitivity, and retention profiles, exposes that posture through guarded `x-lotus-source-data-security` OpenAPI route metadata, prevents operator-only products from drifting outside control-plane/policy route families, constrains access classifications, audit requirements, and sensitivity-driven retention requirements to governed RFC-0082/RFC-0083 lanes, derives default source-data read capability rules from the governed product catalog for both `GET` and query-style `POST` routes, and centralizes duplicated query-service/query-control-plane enterprise readiness authorization, policy-header, capability, write-audit, opt-in read-audit, opt-in read-authorization, and opt-in strict capability-rule middleware support in `portfolio_common.enterprise_readiness` while preserving service-local wrappers,
13. RFC-0083 Slice 10 now defines event family governance, schema governance requirements, operator supportability surface posture, operator-only security profile bindings for support evidence, a guarded runtime outbox event/type topic alignment check, direct Kafka publish-topic governance for source-ingestion, recovery, and job-command topics, explicit shared event-model envelope tolerance, and centralized outbox payload envelope metadata for `event_type`, `schema_version`, and `correlation_id`,
14. RFC-0083 Slice 11 now records target-model closure through a machine-readable implementation ledger and closure guard,
15. the repository already enforces a broad banking-grade CI contract including architecture, OpenAPI, warning, coverage, latency, Docker, and operational gates,
16. canonical shared infrastructure ownership now lives in `lotus-platform`, while `lotus-core` still supports app-local stacks for isolated development,
17. RFC-0086 repo-native domain-product declarations now live under
    `contracts/domain-data-products/` and are validated by `make domain-product-validate` when the
    sibling `lotus-platform` validator and vocabulary registries are available.

## Architecture And Module Map

Primary areas:

1. `src/services/query_service/`
   Primary operational read-plane API surface.
2. `src/services/query_control_plane_service/`
   Governed downstream contract plane for analytics inputs, integration policy, support, lineage, and simulation APIs.
3. `src/services/ingestion_service/`
   Bundle and upload ingestion endpoints.
4. `src/services/persistence_service/`
   Persistence processing.
5. `src/services/calculators/`
   Position, valuation, and cashflow calculator services.
6. `src/services/timeseries_generator_service/`
   Position and portfolio time-series generation.
7. `scripts/`
   quality gates, performance and recovery gates, test-manifest orchestration, and operational tooling.
8. `tests/`
   unit, integration-lite, full integration, ops-contract, transaction-contract, e2e, Docker smoke, and performance-oriented coverage.
9. `contracts/domain-data-products/`
   Repo-native RFC-0086 domain-product producer declarations for governed `lotus-core` source-data
   products.
10. `wiki/`
   canonical authored source for GitHub wiki publication and core-owned operator and onboarding summaries.
11. `docs/architecture/README.md`
    the primary navigation index for the deep core architecture and RFC hardening set.

## Runtime And Integration Boundaries

Runtime model:

1. multi-service, event-driven platform with Kafka and PostgreSQL,
2. shared infrastructure can be owned centrally by `lotus-platform`,
3. app-local compose remains available for isolated development.

Boundary rules:

1. `lotus-core` remains authoritative for portfolio-management and transaction domain data,
2. downstream services should consume its governed APIs rather than duplicate foundational logic,
3. downstream-facing contracts must stay classified under RFC-0082 families: operational reads, snapshot/simulation, analytics inputs, control-plane/policy, write ingress, or control execution,
4. integration and capability metadata are part of the supported contract,
5. operational correctness and reprocessing reliability are first-class engineering concerns.

## Repo-Native Commands

Use these commands as the primary local contract:

1. install
   `make install`
2. feature-lane parity
   `make ci-local`
3. PR merge gate parity
   `make ci`
4. main releasability parity
   `make ci-main`
5. targeted unit gate
   `make test`
6. database-backed unit gate
   `make test-unit-db`
7. integration-lite suite
   `make test-integration-lite`
8. E2E smoke
   `make test-e2e-smoke`
9. Docker smoke
   `make test-docker-smoke`
10. repo-native domain-product validation
   `make domain-product-validate`

## Validation And CI Expectations

`lotus-core` uses explicit CI lanes with a much heavier validation contract than most repos.

Important validation expectations:

1. architecture guards, OpenAPI gates, warning budget, vocabulary, source-data product, and contract gates are active,
2. PR-grade validation includes runtime gates, Docker smoke, latency, and performance load checks,
3. main releasability extends PR validation with heavier release-only gates,
4. deterministic test-manifest orchestration is part of the repo truth and should not be bypassed casually,
5. repo-local wiki and README content should stay limited to current `lotus-core` ownership and
   should not re-import ecosystem-wide or commercial narrative that now belongs in `lotus-platform`.

## Standards And RFCs That Govern This Repository

Most relevant current governance:

1. `../lotus-platform/rfcs/RFC-0041-platform-integration-architecture-bible-governance.md`
2. `../lotus-platform/rfcs/RFC-0067-centralized-api-vocabulary-inventory-and-openapi-documentation-governance.md`
3. `../lotus-platform/rfcs/RFC-0068-centralized-shared-infrastructure-ownership-and-migration.md`
4. `../lotus-platform/rfcs/RFC-0071-centralized-environment-scoped-service-addressing-and-ingress-governance.md`
5. `../lotus-platform/rfcs/RFC-0072-platform-wide-multi-lane-ci-validation-and-release-governance.md`
6. `../lotus-platform/rfcs/RFC-0073-lotus-ecosystem-engineering-context-and-agent-guidance-system.md`
7. `../lotus-platform/rfcs/RFC-0082-lotus-core-domain-authority-and-analytics-serving-boundary-hardening.md`
8. `../lotus-platform/rfcs/RFC-0083-lotus-core-system-of-record-target-architecture.md`
9. `docs/architecture/RFC-0082-contract-family-inventory.md`
10. `docs/architecture/RFC-0083-target-state-gap-analysis.md`
11. `docs/architecture/lotus-core-target-architecture.md`
12. `docs/architecture/QUERY-SERVICE-AND-CONTROL-PLANE-BOUNDARY.md`
13. `docs/architecture/RFC-0083-portfolio-reconstruction-target-model.md`
14. `docs/architecture/RFC-0083-ingestion-source-lineage-target-model.md`
15. `docs/architecture/RFC-0083-reconciliation-data-quality-target-model.md`
16. `docs/architecture/RFC-0083-source-data-product-catalog.md`
17. `docs/architecture/RFC-0083-market-reference-data-target-model.md`
18. `docs/architecture/RFC-0083-endpoint-consolidation-disposition.md`
19. `docs/architecture/RFC-0083-security-tenancy-lifecycle-target-model.md`
20. `docs/architecture/RFC-0083-eventing-supportability-target-model.md`
21. `docs/architecture/RFC-0083-production-readiness-closure.md`
22. `docs/standards/rfc-0083-implementation-ledger.json`
23. `docs/standards/route-contract-family-registry.json`
24. `docs/standards/temporal-vocabulary.md`
25. `docs/standards/layering-boundaries.md`

## Known Constraints And Implementation Notes

1. this repository has the heaviest local gate set in the ecosystem, so targeted local proof plus GitHub-backed heavy execution is often the right working model,
2. query-service contracts are highly consequential because many other apps depend on them,
3. RFC-0083 implementation should follow `docs/architecture/RFC-0083-target-state-gap-analysis.md` slice order before adding broad new architecture work,
4. temporal fields in new downstream-facing contracts must follow `docs/standards/temporal-vocabulary.md`,
5. route additions, removals, or family changes must update `docs/standards/route-contract-family-registry.json` and pass `make route-contract-family-guard`,
6. future portfolio state products must use `docs/architecture/RFC-0083-portfolio-reconstruction-target-model.md` and the deterministic identity helper before exposing restatable snapshots,
7. future ingestion/replay evidence products must use `docs/architecture/RFC-0083-ingestion-source-lineage-target-model.md` before expanding runtime evidence contracts,
8. future reconciliation/data-quality evidence products must use `docs/architecture/RFC-0083-reconciliation-data-quality-target-model.md` before expanding source-data product supportability fields,
9. future source-data product DTO and route work must use `docs/architecture/RFC-0083-source-data-product-catalog.md` and `src/libs/portfolio-common/portfolio_common/source_data_products.py` for product names, versions, required metadata, consumer mapping, and paging/export disposition, and must pass `make source-data-product-contract-guard`; performance-facing or risk-facing upstream contract changes must also pass `make analytics-input-consumer-contract-guard`,
10. future source-data product catalog changes must keep `contracts/domain-data-products/lotus-core-products.v1.json` aligned with the same product names, versions, consumers, route metadata, serving planes, required trust metadata, and source-data security profile references, and must pass `make domain-product-validate` when the sibling platform checkout is available,
11. future market/reference/benchmark/index/risk-free DTO work must use `docs/architecture/RFC-0083-market-reference-data-target-model.md` and `src/libs/portfolio-common/portfolio_common/market_reference_quality.py` before changing observed/source timestamp or freshness/completeness semantics,
12. route removal or deprecation must follow `docs/architecture/RFC-0083-endpoint-consolidation-disposition.md`, update the route-family registry when routes change, and carry affected-consumer evidence,
13. future source-data product security, retention, audit, capability, and entitlement changes must use `docs/architecture/RFC-0083-security-tenancy-lifecycle-target-model.md`, `src/libs/portfolio-common/portfolio_common/source_data_security.py`, and `src/libs/portfolio-common/portfolio_common/enterprise_readiness.py`; they must keep generated `x-lotus-source-data-security` route metadata and catalog-derived capability rules aligned with the governed profile and avoid reintroducing duplicated service-local authorization or audit middleware logic,
14. future event, outbox, replay, DLQ, direct Kafka publish, and operator diagnostic changes must use `docs/architecture/RFC-0083-eventing-supportability-target-model.md`, `src/libs/portfolio-common/portfolio_common/event_supportability.py`, `src/libs/portfolio-common/portfolio_common/events.py`, and the centralized payload envelope in `src/libs/portfolio-common/portfolio_common/outbox_repository.py`; they must pass `make event-runtime-contract-guard` when outbox emissions, direct publish topics, or Kafka topics are touched,
15. RFC-0083 target-model closure is tracked by `docs/standards/rfc-0083-implementation-ledger.json` and guarded by `make rfc0083-closure-guard`; the ledger intentionally does not claim full production runtime closure,
16. borderline analytics-input/reference contracts in `query_control_plane_service` must be reviewed against `docs/architecture/RFC-0082-contract-family-inventory.md` before material expansion,
17. app-local compose is useful, but canonical shared infrastructure governance now belongs in `lotus-platform`,
18. because operational correctness matters here, failure-recovery and performance gates are part of real delivery quality, not optional extras.
19. institutional load-run diagnosis should distinguish target-date `daily_position_snapshots`,
    security-level `position_timeseries`, and portfolio-level `portfolio_timeseries` coverage,
    because timeseries lag can concentrate before portfolio aggregation rather than inside it,
20. run-progress evidence for institutional load work should split pending versus processing queue
    counts for valuation and aggregation so operators can distinguish backlog from active drain,
21. when branch-only support telemetry exists but the running stack has not been refreshed, use
    durable database facts as the source of truth and record the runtime rollout gap explicitly in
    RFC and operator evidence,
22. for institutional load monitoring, record harness process state separately from database
    completion state because asynchronous workers can continue draining after the original Python
    runner exits,
23. event-catalog completion topics are not automatically part of the active runtime graph:
    `portfolio_security_day.valuation.completed` and
    `portfolio_security_day.position_timeseries.completed` are currently dormant and should not be
    reintroduced into hot paths without a proven consumer need,
24. institutional load diagnosis should track outbox backlog separately from materialized
    portfolio/business-date coverage, because load completion can converge before non-critical
    completion-topic publication drains,
25. the run-scoped support route for institutional load progress is now part of the live local
    runtime baseline for RFC-086 work; after service refresh, use
    `GET /support/load-runs/{run_id}?business_date={date}` as the first completion surface and
    fall back to direct database facts only when runtime rollout has not yet occurred,
26. exact-run correctness evidence for institutional load no longer requires reseeding a fresh
    workload: use `scripts/bank_day_load_reconciliation_report.py` against the completed `run_id`
    to collect sampled or exhaustive reconciliation proof for positions, transactions, support
    overview state, and timeseries-integrity findings.
27. institutional sign-off evidence selection must prefer the strongest available proof, not just
    the newest artifact timestamp: use `full` profile-tier performance-load artifacts ahead of
    newer `fast` artifacts, and prefer exhaustive bank-day reconciliation artifacts where
    `portfolio_count_evaluated == portfolios_ingested` ahead of newer sampled refresh artifacts,
28. main releasability now owns a governed RFC-086 institutional completion gate that runs the
    bank-day load scenario and then exhaustive reconciliation for the generated run before the
    institutional sign-off pack aggregates artifacts,
29. legacy PAS-era wiki material should be filtered through the platform migration ledger before
    reuse; cross-cutting investor, GTM, or ecosystem rationale now belongs in `lotus-platform`.

## Context Maintenance Rule

Update this document when:

1. service ownership or major service boundaries change,
2. repo-native command contracts or test-manifest structure change,
3. shared-infrastructure ownership assumptions change,
4. integration contract posture, RFC-0082 contract-family classification, RFC-0083 target-state slice plan, or current-state architecture shifts materially,
5. the repository's CI and runtime expectations change.
6. deep-architecture navigation or documentation entrypoints change materially.

## Cross-Links

1. `../lotus-platform/context/LOTUS-QUICKSTART-CONTEXT.md`
2. `../lotus-platform/context/LOTUS-ENGINEERING-CONTEXT.md`
3. `../lotus-platform/context/CONTEXT-REFERENCE-MAP.md`
4. `../lotus-platform/context/Repository-Engineering-Context-Contract.md`
5. [Lotus Developer Onboarding](../lotus-platform/docs/onboarding/LOTUS-DEVELOPER-ONBOARDING.md)
6. [Lotus Agent Ramp-Up](../lotus-platform/docs/onboarding/LOTUS-AGENT-RAMP-UP.md)
