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

## Repository Documentation Structure

`docs/README.md` is the documentation front door. Durable documents belong in purpose-owned
subdirectories such as `architecture/`, `data/`, `features/`, `governance/`, `operations/`,
`standards/`, and `testing/`; do not add uncategorized files directly under `docs/`.

Individual codebase-review evidence records belong in
`docs/architecture/codebase-reviews/`. Keep current status and summary evidence in
`docs/architecture/CODEBASE-REVIEW-LEDGER.md`, and use
`docs/architecture/CODEBASE-REVIEW-PLAYBOOK.md` for the review workflow. The architecture
documentation catalog guard rejects root-level `CR-*` records and loose `docs/` files.

Repository automation follows `scripts/README.md`: executable modules belong under the owning
`development/`, `generators/`, `operations/`, `quality/`, `release/`, or `validation/` package.
Use descriptive domain/action filenames. Do not name ordinary files after issues or RFCs; an RFC
identifier is acceptable only when the module exclusively governs that RFC's status or closure.
Keep Make targets as the stable operator and CI entry points when internal script modules move.

## Current-State Summary

Current repository posture:

1. `lotus-core` is the domain authority for portfolio-management and transaction data,
2. the current-state bounded-context, deployable, database-ownership, event-flow, dependency-direction,
   and downstream-consumer map is `docs/architecture/current-state-architecture-map.md`; update it
   with the same slice when a change moves major routes, modules, deployables, database ownership,
   event flows, or downstream consumer relationships,
3. downstream-facing API ownership is now classified under the RFC-0082 contract-family model, with `query_service` as the operational read plane and `query_control_plane_service` as the governed analytics-input, snapshot/simulation, support, and policy contract plane,
4. RFC-0083 now defines the target system-of-record architecture, and the local Slice 0 gap analysis maps current route, model, temporal, source-data product, ingestion, reconciliation, and observability gaps to the implementation program,
5. RFC-0083 Slice 1 now defines repo-local temporal vocabulary and schema policy for as-of, valuation, trade, settlement, booking, effective, ingestion, observation, correction, and restatement semantics. Current query-service `transaction_date` is the transaction event/trade timestamp used for filtering and ordering; do not describe or implement it as `booking_date` unless a future slice introduces a first-class booking field with a migration plan,
6. RFC-0083 Slice 2 now enforces route contract-family classification through a machine-readable registry and guard,
7. RFC-0083 Slice 3 now defines the portfolio reconstruction target model and deterministic snapshot identity helper,
8. RFC-0083 Slice 4 now defines the ingestion source-lineage target model and source-batch evidence helper,
9. RFC-0083 Slice 5 now defines the reconciliation/data-quality target model and shared status helper,
10. RFC-0083 Slice 6 now defines the priority source-data product catalog, product metadata requirements, consumer map, paging/export disposition, route metadata bindings, DTO-envelope product identity, HoldingsAsOf runtime data-quality metadata and reporting evidence timestamps, canonical TransactionLedgerWindow runtime evidence timestamp and window-completeness data-quality metadata, PortfolioCashflowProjection runtime metadata, portfolio base-currency disclosure, and latest cashflow evidence timestamp, PortfolioStateSnapshot runtime metadata, snapshot evidence timestamp, freshness epoch handling, and baseline data-quality classification, analytics-input data-quality classification, market/reference runtime evidence timestamp and data-quality classification, coverage data-quality classification and evidence timestamps, ingestion/reconciliation evidence runtime supportability metadata with reconciliation evidence status derivation, a linted source-data product contract guard, and a `lotus-performance` analytics-input consumer conformance guard,
11. RFC-0083 Slice 7 now defines market/reference quality, observed-at mapping, and freshness/completeness classification for benchmark, index, risk-free, price, FX, and instrument products,
12. RFC-0083 Slice 8 now records endpoint-consolidation disposition, deprecates selected pre-live reporting convenience routes in OpenAPI while preserving tested handlers, and enforces the endpoint-consolidation watchlist through `docs/standards/endpoint-consolidation-watchlist.json`, `scripts/quality/endpoint_consolidation_watchlist_guard.py`, and `make endpoint-consolidation-watchlist-guard` so monitored convenience-route families cannot grow without source-data product identity or approved bounded-use rationale,
13. RFC-0083 Slice 9 now defines source-data product security, tenancy, entitlement, capability, audit, sensitivity, and retention profiles, exposes that posture through guarded `x-lotus-source-data-security` OpenAPI route metadata, prevents operator-only products from drifting outside control-plane/policy route families, constrains access classifications, audit requirements, and sensitivity-driven retention requirements to governed RFC-0082/RFC-0083 lanes, derives default source-data read capability rules from the governed product catalog for both `GET` and query-style `POST` routes, centralizes duplicated query-service/query-control-plane enterprise readiness authorization, policy-header, capability, write-audit, read-audit, read-authorization, and strict capability-rule middleware support in `portfolio_common.enterprise_readiness` while preserving service-local wrappers, and defaults production-like environments to the shared service-local enterprise security profile,
14. RFC-0083 Slice 10 now defines event family governance, schema governance requirements, operator supportability surface posture, operator-only security profile bindings for support evidence, a guarded runtime outbox event/type topic alignment check, direct Kafka publish-topic governance for source-ingestion, recovery, and job-command topics, explicit shared event-model envelope tolerance, and centralized outbox payload envelope metadata for `event_type`, `schema_version`, `correlation_id`, and `traceparent`,
15. RFC-0083 Slice 11 now records target-model closure through a machine-readable implementation ledger and closure guard,
16. RFC status governance now has a repository-wide machine-readable ledger at
    `docs/standards/rfc-status-ledger.v1.json`, guarded by `make rfc-status-ledger-guard` and
    `quality-wiki-docs-gate`. It covers core RFCs, transaction RFC/spec documents, architecture RFC
    material, and operations RFC playbooks so new RFC files cannot be added without status,
    ownership, evidence, wiki, supported-feature, and supersession metadata,
17. API surface truth now has a generated implementation-backed route catalog at
    `docs/standards/api-route-catalog.v1.json`, guarded by `make api-route-catalog-guard` and the
    existing `api-vocabulary-gate`. It is generated from FastAPI OpenAPI output and enriched with
    `docs/standards/route-contract-family-registry.json`, so route docs can cite method/path,
    service app, route family, owner, request/response schema, error model, pagination/filtering,
    idempotency, downstream-consumer posture, and deprecated-alias metadata without hand-maintained
    drift. The same `api-vocabulary-gate` runs the non-mutating API vocabulary `--validate-only`
    command, which validates generated and committed inventory structure and requires complete
    semantic parity while excluding only the top-level volatile `generatedAt` timestamp. Use the
    explicit `--output docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json` path for an
    intentional refresh; never treat in-memory validation alone as committed vocabulary proof,
18. README/wiki front-door synchronization is governed by
    `docs/standards/front-door-sync.v1.json` and `make front-door-sync-guard`. The contract
    distinguishes canonical sources from summary/navigation pages, verifies critical README links,
    wiki home links, sidebar pages, and PR documentation/no-doc-change checklist terms, and is part
    of `quality-wiki-docs-gate`,
19. the repository already enforces a broad banking-grade CI contract including architecture,
   OpenAPI, warning, aggregate branch-aware coverage, changed-code and critical-path coverage
   reporting, latency, Docker, and operational gates. Critical-path coverage governance lives in
   `docs/standards/critical-path-coverage.v1.json`, is checked by
   `make critical-path-coverage-guard`, and is reported by `make coverage-gate` under
   `output/coverage/critical-path-coverage-report.json`; contract-only validation writes the
   separate `critical-path-coverage-contract-report.json` artifact. Git name-status evidence preserves
   rename/copy/delete lineage, coverage evaluates only post-change files, and current changed
   critical modules fail closed when absent from the measured-source artifact or when measured
   coverage cannot establish Git comparison evidence. Contract-only validation does not require
   changed-source history. Selection follows contract globs across all governed Python paths, not
   only `src/`; changed Alembic migrations use the `./alembic` coverage source and exact-path JSON
   inclusion. Measured changed critical modules enforce both line and branch thresholds. Query Service
   aggregate evidence remains separate at `output/coverage/query-service-coverage.json`, so
   aggregate, changed-code, and critical-path coverage cannot be conflated. Risk-based test-family
   coverage governance lives in
   `docs/standards/risk-based-test-coverage-matrix.v1.json`, is checked by
   `make risk-based-test-coverage-matrix-guard`, and maps instruments, accounts, positions, cash,
   transactions, corporate actions, valuation, cashflow, cost, reconciliation, ingestion, replay,
   operations, security, and observability to required proof families, concrete test/Make evidence,
   gap status, and follow-up issue ownership,
20. canonical shared infrastructure ownership now lives in `lotus-platform`, while `lotus-core` still supports app-local stacks for isolated development,
21. app-local compose keeps the ingestion service write payload cap at 16 MiB through
    `ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES` so the governed local `demo_data_loader` bundle can seed
    through the HTTP write boundary; do not carry that local override into production ingress policy
    without explicit approval,
22. RFC-0086 repo-native domain-product declarations now live under
    `contracts/domain-data-products/` and are validated by `make domain-product-validate` when the
    sibling `lotus-platform` validator and vocabulary registries are available.
23. RFC-0087 trust telemetry proof currently covers exactly `PortfolioStateSnapshot:v1` and
    `DpmSourceReadiness:v1` under `contracts/trust-telemetry/`; it is validated by
    `tests/unit/test_trust_telemetry.py` against the platform trust telemetry validator when
    `lotus-platform` is available. Active source-product declaration, local implementation proof,
    CI proof, live validator proof, trust telemetry coverage, and platform mesh certification are
    distinct statuses; do not describe every active Core source product as mesh certified unless
    current generated platform certification artifacts prove that exact product state.
24. RFC-0087 now promotes the first DPM source-data products for `lotus-manage` stateful
    discretionary mandate portfolio management: `DpmModelPortfolioTarget:v1`,
    `DiscretionaryMandateBinding:v1`, `InstrumentEligibilityProfile:v1`, and
    `PortfolioTaxLotWindow:v1`, `TransactionCostCurve:v1`,
    `MarketDataCoverageWindow:v1`, `DpmSourceReadiness:v1`,
    `PortfolioManagerBookMembership:v1`, `CioModelChangeAffectedCohort:v1`, and
    `DpmPortfolioUniverseCandidate:v1`. They are declared in the active source-data catalog,
    route-family registry, source-security profiles, and domain-product declaration, backed by
    canonical front-office seed payloads where applicable, and live-proven for the RFC-0087 source
    family through `make live-dpm-source-validate`. `PortfolioPartyRoleAssignment:v1` owns
    effective-dated relationship coverage, investment-advisory, portfolio-management, and
    client-service capacity with source lineage and quality disposition. `party_id` remains a
    source-owned identifier until #518 establishes the broader Party aggregate.
    `PortfolioManagerBookMembership:v1` resolves governed portfolio-manager assignments and uses
    `advisor_id` only as a compatibility projection for portfolios with no role-assignment history;
    it does not claim a broader relationship-householding hierarchy.
    `CioModelChangeAffectedCohort:v1` is the RFC41-WTBD-002 source-owner foundation and resolves
    affected discretionary mandates from approved model definitions and effective mandate bindings
    without moving rebalance decisioning into core. `DpmPortfolioUniverseCandidate:v1` advances
    RFC37-WTBD-004 source-owner depth by exposing paged Core-owned DPM universe candidates from
    effective discretionary mandate bindings without claiming relationship-householding, client
    suitability, PM ranking, execution, or external workflow ownership. RFC40-WTBD-008 source-owner coverage adds
    `ClientRestrictionProfile:v1` and `SustainabilityPreferenceProfile:v1` as effective-dated,
    lineage-backed query-control-plane products and canonical front-office seed inputs; downstream
    `lotus-manage` consumption remains a separate slice. RFC42-WTBD-006 source-owner coverage adds
    `ClientTaxProfile:v1` and `ClientTaxRuleSet:v1` as effective-dated, lineage-backed
    query-control-plane products for bounded tax-reference evidence without tax-advice,
    after-tax-optimization, tax-loss-harvesting, client-tax-approval, or jurisdiction-specific
    recommendation claims. It also adds `ClientIncomeNeedsSchedule:v1`,
    `LiquidityReserveRequirement:v1`, and `PlannedWithdrawalSchedule:v1` as lineage-backed
    query-control-plane products for bounded DPM income, reserve, and withdrawal evidence without
    financial-planning-advice, suitability-approval, cashflow-forecasting, funding-recommendation,
    treasury-instruction, or OMS-acknowledgement claims. `PortfolioRealizedTaxSummary:v1` adds
    operational read-plane aggregation of explicit booked withholding-tax and
    other-interest-deduction evidence by ledger currency, with optional reporting-currency
    restatement and explicit boundaries from tax advice, after-tax optimization,
    tax-loss-harvesting, client-tax approval, tax-reporting certification, execution quality, and
    OMS acknowledgement.
25. RFC-0108 portfolio readiness supportability now publishes the bounded
    `metric_labels=["state", "reason", "freshness_bucket"]` contract in
    `PortfolioSupportabilitySummary`, uses the shared
    `portfolio_common.observability_contracts.PORTFOLIO_SUPPORTABILITY_METRIC_LABELS` tuple for the
    Prometheus counter, and has focused tests proving
    `lotus_core_portfolio_supportability_total` does not add portfolio, account, client,
    correlation, trace, transaction, security, request-body, or response-body labels.
26. App-level supported-surface validation now has a single repo-native evidence command:
    `make lotus-core-validate`. It runs static contract guards plus deterministic runtime smoke over
    ingestion, event replay and ops, operational query reads, query-control-plane support and
    lineage, integration policy and capabilities, core snapshot, simulation, and source-data
    contract governance. PR Merge Gate now runs it as a blocking app-validation gate with a
    workflow-provided `lotus-platform` checkout for domain-product contract validation. The
    runtime smoke must observe the exact transaction in the query ledger before issuing the
    one-shot reprocessing command; do not retry the side-effecting POST or accept `404` as proof.
27. Boundary mapping conformance now has a repo-native command,
    `make test-boundary-mapping-conformance`, backed by the test manifest and documented in
    `docs/architecture/mapping-anti-corruption-boundary.md`; `make architecture-guard` also runs
    `scripts/quality/mapping_anti_corruption_guard.py` as the representative contract index. It currently
    protects representative transaction event, persistence event-envelope, portfolio tax-lot, and
    performance-economics source-data mappings.
    Ingestion publish workflows must route API DTO serialization through
    `ingestion_service.app.services.ingestion_event_payloads` before Kafka publication; do not add
    new inline DTO `model_dump()` publish payloads in `IngestionService`.
    Valuation, persistence, financial-reconciliation, and future event-consuming services must use
    `portfolio_common.event_mapping` or a narrower service adapter around it for Kafka bytes,
    deterministic message identity, governed Pydantic event validation, outbox event payload
    serialization, and explicit correlation/idempotency metadata before opening database units of
    work. Persistence repositories must consume adapter-owned event record values and keep only
    table-specific SQL conflict/update policy locally.
    `PortfolioTaxLotWindow:v1` uses `PortfolioTaxLotReadRecord` as the typed
    repository-to-source-data boundary. `TransactionCostCurve:v1` and
    `PerformanceComponentEconomics:v1` are QCP-owned end to end and use
    `BookedTransactionEconomics`, `TransactionCashflowEvidence`, and
    `TransactionCostComponentEvidence` so latest optional cashflow evidence and transaction-cost
    component evidence are modeled explicitly before source-data response assembly. Their QCP
    capability separates API contracts, application row/policy/response assembly, a source-reader
    port, and a SQLAlchemy adapter; preserve that shape before adding component-family,
    supportability, lineage, runtime metadata, or response behavior. Extend this pattern before
    adding new high-value
    source-data mappers that would otherwise accept raw ORM rows, ORM relationship objects, or
    tuple-shaped SQL results.
    Repository output-shape governance now also has `make repository-output-shape-guard`, wired into
    `make lint`, backed by `scripts/quality/repository_output_shape_guard.py`, and documented in
    `docs/architecture/repository-output-shape-standard.md`. It blocks new public repository methods
    from exposing SQLAlchemy ORM return annotations unless the method is explicitly registered as a
    transitional exception, and it fails stale exceptions after future typed-record conversions.
    Timeseries generation and portfolio aggregation repositories now map persistence rows to
    immutable service-owned domain records for snapshots, cashflows, position/portfolio timeseries,
    portfolio scope, and claimed jobs. Their calculation and scheduler modules must not accept ORM
    return contracts. Delete production-unused repository methods rather than adding exceptions or
    keeping tests that falsely imply a supported persistence contract.
    API-router boundary governance now also has a documented contract in
    `docs/architecture/api-layer-router-boundary-contract.md`; `make architecture-guard` blocks new
    router-local database session dependencies, repository construction, SQLAlchemy operations,
    external client access, and file access unless explicitly registered in
    `docs/standards/api-layer-router-boundary-exceptions.json`. Treat that registry as transitional
    extraction backlog for issues #635 and #638, not as approval for new router coupling. The
    financial reconciliation router has been moved behind reconciliation use cases, so #636 no
    longer requires an API-router boundary exception. The query-service BUY/SELL state, cash
    account, cash balance, cash movement, cashflow projection, liquidity ladder, portfolio,
    position, reporting, FX rate, instrument, price, lookup, and transaction routers now use
    dependency-module service providers and no longer require #638 exceptions. Query-control-plane
    analytics-input, simulation, integration, and operations routers now use a QCP dependency
    module too. Business-date ingestion validation now lives in `BusinessDateIngestionPolicy`
    behind ingestion dependency-module composition, so the local #635 API-router repository
    exception is cleared too. The API-router boundary exception registry is empty.
    Query-service lookup catalog assembly now lives in `LookupCatalogService`; lookup routers
    should keep selector routes limited to HTTP query parameter parsing and response wrapping while
    the service owns source scoping, de-duplication, ordering, and limit behavior.
    Event-replay operations now follows the same bounded-module pattern: FastAPI routes in
    `src/services/event_replay_service/app/routers/` bind HTTP requests, build API DTOs, and map
    `HTTPException` only; command and query orchestration belongs in
    `src/services/event_replay_service/app/application/`; runtime composition providers belong in
    `src/services/event_replay_service/app/dependencies.py`; OpenAPI/operator examples belong in
    router-support modules such as `ingestion_operations_examples.py`, not inline in the main route
    module. Do not rebuild replay payloads, deterministic replay fingerprints, consumer-DLQ
    candidate selection, audit persistence, retry/bookkeeping state transitions, query envelope
    totals, or large example catalogs in the router. Add application service tests first when
    extending ingestion operations, and add router-support guard tests when moving API
    documentation data.
    Consumer-DLQ replay correlation joins must use purpose-built ingestion job service lookups,
    not generic operator listing pages. Use the latest replayable correlation lookup for recovery
    paths so replay correctness does not depend on unrelated job volume, page size, or incidental
    list ordering.
28. Reference-data ingestion source-observation lineage now has a shared DTO contract for
    benchmark, index, risk-free, and classification families. The canonical API-facing fields are
    `source_system`, `source_record_id`, `observed_at`, and `quality_status`; legacy
    `source_vendor` and `source_timestamp` inputs remain accepted and are mapped to the existing
    storage columns until persistence migrations are explicitly approved.
29. Consumer DLQ and replay-audit evidence now follows a correlation-or-reason contract:
    `correlation_id` remains nullable for legacy and malformed events, but missing-correlation rows
    must carry `correlation_missing_reason` and `alternate_lookup_key` for support lookup and replay
    forensics. The first implementation covers shared Kafka DLQ persistence, consumer DLQ read
    DTOs, replay response DTOs, replay-audit persistence, and missing-correlation not-replayable
    replay responses.
30. Replay audit recording is mandatory for ingestion-job retry and consumer-DLQ replay workflows.
    Replay outcomes must not be acknowledged when audit persistence fails; affected endpoints return
    `INGESTION_REPLAY_AUDIT_WRITE_FAILED` with recovery path, event/job identity, replay status, and
    deterministic fingerprint so operators can restore audit persistence and retry through the
    governed endpoint.
31. Direct ingestion-router Kafka publish dependency failures use the shared
    `routers.publish_errors` mapper. Preserve the `INGESTION_PUBLISH_FAILED` application code, but
    return HTTP 503 with `Retry-After`, dependency=`kafka`, retryability, correlation lineage,
    failed-record keys, publish state, and published-record count. Reference-data persistence
    failures and post-publish bookkeeping failures remain distinct HTTP 500 contracts.
32. Direct ingestion post-publish or post-persist bookkeeping failures must preserve the
    `INGESTION_JOB_BOOKKEEPING_FAILED` code while making partial-failure state explicit with
    `publish_state`, `work_state`, `published_record_count`, `retry_safe=false`,
    `recovery_action`, `recovery_path`, and `supportability_reason_code`. Client retry is not safe
    until operators inspect failure history. Bookkeeping repair must use the protected
    `POST /ingestion/jobs/{job_id}/bookkeeping/repair` operation and must require recorded
    `queue_bookkeeping` or `persist_bookkeeping` evidence before moving accepted jobs to queued.
    Reference-data ingestion family dispatch is governed by
    `ingestion_service.app.application.reference_data_ingestion_registry.ReferenceDataIngestionRegistry`.
    New reference-data families must add one registry command plus focused registry/router tests;
    do not reintroduce route-local `persist_fn` lambdas, `ReferenceDataIngestionService.upsert_*`
    dispatch, accepted-count mapping, or DTO-to-record transformation in
    `ingestion_service/app/routers/reference_data.py`.
    Lifecycle mutations are expected-state guarded; repair must treat stale accepted-to-queued
    updates as conflicts, not successful repairs. New lifecycle workflows must follow
    `docs/standards/domain-state-transition-policy.md`; domain policy modules own status
    vocabulary, allowed transitions, terminal posture, retry metadata, and audit/failure-evidence
    requirements, while persistence helpers only consume policy-derived expected states. The
    current implemented lifecycle policies cover ingestion job mutations and financial
    reconciliation run completion/outcome posture.
    Financial reconciliation position-valuation rules now also use pure domain policy/value
    objects in `financial_reconciliation_service.app.domain.reconciliation_policies`; the
    application service must load evidence, invoke the policy, and map domain findings to
    persistence rows through `financial_reconciliation_service.app.adapters`.
    Portfolio aggregation owns reconciliation-request staging after successful aggregation;
    financial reconciliation owns monotonic/latest-epoch control evidence and controls-event
    staging. The former `pipeline_orchestrator_service` runtime, package, image, consumers, health
    API, and deployment inventory are retired. Do not recreate a generic pipeline coordinator;
    place each transition with the capability that owns the resulting state. Retain the shared
    `pipeline_stage_state` table only as active transaction-readiness/QCP compatibility evidence
    until a separately reversible retention and schema migration is proven.
    Shared private-banking financial amount objects now live in
    `portfolio_common.domain.financial.amounts` for `CurrencyCode`, `MoneyAmount`, `FxRate`,
    `CurrencyBasis`, `Quantity`, `UnitPrice`, and named monetary aliases. New calculation and
    reporting-currency paths should normalize DTO/ORM primitives into these value objects at the
    boundary, keep domain rules framework-free, and serialize back to primitive payloads only at
    API/event/persistence edges. `MoneyAmount.quantized()` is an explicit output-boundary operation
    using canonical `ROUND_HALF_EVEN` policy version `1.1.0`; conversion remains unrounded, and a
    caller must supply the governed quantum when `0.01` is not the applicable boundary scale.
    Cost-engine domain models now follow
    `docs/standards/cost-basis-domain-standard.md`:
    `portfolio_transaction_processing_service/app/domain/cost_basis` must stay free of
    Pydantic, FastAPI, SQLAlchemy, repositories, database sessions, Kafka clients, HTTP clients, and
    settings. Keep event/API validation at adapter boundaries and let parser construction map raw
    dictionaries into pure domain objects.
    The broader domain-layer contract lives in `docs/standards/domain-layer-contract.md` and is
    enforced by `make domain-layer-guard`, which also runs under `make architecture-guard`. New
    `domain` packages must not import framework, persistence, DTO, repository, client, consumer, or
    settings modules unless a narrow transitional exception is explicitly allowlisted with
    migration rationale.
    Time, monotonic timer, and generated ID behavior is governed by
    `docs/standards/time-id-provider-policy.md`. Application/use-case code should inject provider
    ports for generated timestamps, elapsed duration, expiry checks, and deterministic IDs.
    Financial reconciliation, simulation, and core snapshot now provide representative provider
    coverage with focused deterministic tests and targeted static guard coverage.
33. Ingestion job retry recovery failures must use stable recovery details with `code`, `message`,
    `outcome`, `remediation`, and `recovery_path="ingestion_job_retry"`. Preserve existing route
    paths, HTTP statuses, success DTOs, replay audit side effects, and failed-job side effects, but
    do not expose raw downstream publish or bookkeeping exception text as the primary client
    message. Current outcomes are `not_found`, `retry_unsupported`, `partial_retry_unsupported`,
    `retry_blocked`, `duplicate_blocked`, `publish_failed`, `bookkeeping_failed`,
    `bookkeeping_conflict`, and `audit_write_failed`. Replay success bookkeeping must use the
    atomic retry-plus-queued transition so retry counters cannot advance separately from queued
    status.
34. `/metrics` is an operational scrape endpoint governed by the shared metrics access policy.
    Token parsing belongs in `portfolio_common.metrics_settings`, and standard API apps,
    health-only worker apps, and web-backed worker runtime paths must all use the shared policy so
    `LOTUS_METRICS_ACCESS_TOKEN` consistently enables bearer-token protection without direct env
    reads in HTTP middleware.
35. Shared `/health/ready` endpoints must keep dependency checks bounded and failure-isolated
    through `portfolio_common.health`. Preserve the per-dependency timeout pattern and explicit
    `ok`, `unavailable`, `timeout`, `misconfigured`, and `error` status vocabulary when adding
    database, Kafka, or future dependency probes. Readiness can return HTTP 503 with dependency
    detail without changing route paths or the top-level ready/not-ready contract. Health responses
    must keep the bounded `runtime` metadata block with service name, app version, environment,
    runtime profile, started-at, uptime, and shared build metadata so operators can correlate probes
    to image provenance without shell access. Dependency telemetry must use the shared
    `health_dependency_check_total`, `health_dependency_check_duration_seconds`, and
    `health_readiness_state` metrics with only service, dependency, status, and readiness-state
    labels; keep raw exception text, business identifiers, request IDs, correlation IDs, and trace
    IDs out of Prometheus labels.
36. Prometheus metric vocabulary is governed by `portfolio_common.observability_contracts` and
    enforced by `make metric-vocabulary-guard` through `make lint`. HTTP request metrics must use
    `endpoint_template`, not raw `path`. New labels must be registered in
    `TELEMETRY_METRIC_ALLOWED_LABELS`, must not be listed in `TELEMETRY_METRIC_FORBIDDEN_LABELS`,
    and service-local metrics outside `portfolio_common.monitoring` must be registered in
    `SERVICE_LOCAL_METRIC_OWNERS` with an owning service.
37. Standard FastAPI service apps and health-only worker web apps are covered by the shared HTTP
    middleware-chain contract in `tests/test_support/http_middleware_contract.py` and
    `tests/unit/test_http_middleware_chain_contract.py`. The contract proves `/version` metadata,
    correlation/request/trace headers, `traceparent`, secure response headers, safe unhandled
    exception responses, and route-template HTTP metrics across every app entrypoint that uses
    `configure_standard_http_app` or `create_standard_health_app`. Do not add a new FastAPI app
    entrypoint without extending that matrix.
38. Kafka consumers inheriting `portfolio_common.kafka_consumer.BaseConsumer` emit the standard
    `kafka_consumer_events_total` and `kafka_consumer_processing_duration_seconds` metrics. Keep
    processing attempts, success, retryable/terminal failure, DLQ, commit, poll, critical-exit, and
    shutdown telemetry on the shared consumer boundary; add service-local metrics only as
    registered extensions when the shared fleet-level metrics are insufficient. DLQ publication
    failures default to stopping after one failed DLQ publication or post-publication offset commit
    without committing the source offset, allowing governed restart redelivery. Operators can set
    `KAFKA_CONSUMER_DLQ_FAILURE_MAX_ATTEMPTS` to a positive value to enable bounded ordered
    in-process recovery; exhaustion stops the consumer with `DlqPublicationBudgetExhausted` and
    `dlq_failure_budget_exhausted` telemetry for the same topic/group/partition/offset/key. Do not
    claim durable local
    quarantine unless a separate service-owned quarantine store exists. Retryable consumer failures
    default to one attempt followed by consumer shutdown before any later same-partition offset can
    be processed or committed. The source offset remains uncommitted for restart/rebalance
    redelivery, and concurrent pending messages for that partition are discarded. Operators can set
    `KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ATTEMPTS` and/or
    `KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ELAPSED_SECONDS` to route repeatedly retryable messages
    to DLQ after a bounded in-process budget, committing only after DLQ success.
    The shared base now exposes a typed subclass boundary while its legacy implementation remains a
    silently followed migration module. New or changed consumers must declare explicit constructor
    dependencies and base configuration parameters; do not hide delivery contracts behind untyped
    `*args` or `**kwargs` forwarding.
    Service delivery adapters must not call `_send_to_dlq_async` or commit terminal source offsets.
    They decode, map, invoke the application boundary, classify retryable infrastructure failures,
    and raise terminal failures with their original typed identity. Only
    `BaseConsumer._recover_exhausted_retryable_failure` and
    `BaseConsumer._handle_terminal_processing_error` may publish and confirm DLQ delivery, persist
    support evidence, and then commit the exact source message. `make event-runtime-contract-guard`
    enforces this ownership. For derived-state changes, run
    `make test-derived-state-poison-gate` to prove one poison record, support-plane visibility,
    bounded lag recovery, subsequent valid-message progress, and clean reconciliation.
    Kafka topic topology and ordering are governed by
    `contracts/eventing/kafka-topic-runtime-contract.v1.json`. Domain partition keys live in
    `portfolio_common.domain.eventing`; dates and epochs must not enter position, portfolio,
    security, currency-pair, or business-calendar ordering keys. Outbox aggregate identity and
    transport partition identity are separate fields. Topic provisioning and service startup must
    fail when broker partition metadata differs from the source contract. Known consumer groups
    may process independent partitions concurrently but must remain serial within each partition
    and may not exceed governed partition capacity. Follow
    `docs/operations/kafka-partition-migration-runbook.md` for pause/drain/cutover/rollback. Current
    transaction reprocessing commands preserve the transaction-id API but resolve source-owned
    portfolio identity before publication; legacy commands without additive `portfolio_id` remain
    consumable. Current tenant-blind event families must not be described as tenant-isolation proof.
39. Structured operational logging is governed by
    `portfolio_common.logging_utils.operation_log_extra(...)`, `log_operation_event(...)`, and
    `make structured-log-guard` through `make lint`. Guarded health, Kafka, outbox, ingestion,
    query, replay, and scheduler paths must use constant messages plus `event_name`, `operation`,
    `status`, and `reason_code`; do not embed portfolio, account, client, security, request,
    correlation, or trace identifiers in free-text operational log messages.
40. Query-control-plane routes (QCP routes under `query_control_plane_service`) migrated to the
    shared `QueryControlPlaneProblem` contract must
    document error responses as `application/problem+json` with stable QCP error codes,
    correlation IDs, and bounded metadata. Routes not yet migrated must remain explicitly
    documented as legacy `application/json` bare-detail responses until their runtime handlers are
    converted; do not publish problem-details OpenAPI schemas for routes that still raise default
    FastAPI `HTTPException(detail=...)`. Mandate-scoped source-data routes that fail because no
    effective discretionary mandate binding exists should use the shared mandate-scoped
    integration-source helper and assert `QCP_INTEGRATION_SOURCE_NOT_FOUND` with source product,
    portfolio ID, and `not_found` reason metadata at unit, ASGI, and OpenAPI layers.
    `make qcp-problem-details-guard` now prevents active QCP routers from reintroducing direct
    FastAPI/Starlette `HTTPException` calls or raw `detail=str(...)` payloads. When a QCP route
    maps application/service failures, prefer typed service exceptions and router type dispatch
    over substring checks against exception message text; keep human-readable details bounded and
    stable in the problem-details mapper.
    API example documentation is governed by `docs/standards/verified-api-examples.v1.json` and
    `make api-example-catalog-guard`. New example snippets for success, validation errors,
    authorization denial, not-found, idempotency conflict, dependency timeout, degraded source data,
    or pagination/filtering/sorting must extend the catalog with source-test references, synthetic
    identifiers, correlation IDs, and standard problem metadata before wiki prose points to them.
    Synthetic fixtures, API examples, seed examples, and generated evidence safety are governed by
    `docs/standards/synthetic-test-data-governance.v1.json` and
    `make synthetic-fixture-leakage-guard` through `make lint`. New reusable fixtures should prefer
    `SYNTH_*` identifiers, must model required private-banking relationships when representative,
    and must not commit concrete bearer tokens, credentialed database URLs, personal emails,
    natural-person client names, uncataloged CIF-style identifiers, concrete account numbers, API
    keys, secrets, or passwords.
    Test lane governance now lives in `docs/standards/test-lane-governance.v1.json` and is enforced
    by `make test-lane-governance-guard` through `make lint`. Changes to pytest markers,
    `scripts/quality/test_manifest.py`, Make test targets, flaky-test quarantine, deterministic-time
    guidance, or integration/E2E lane ownership must update the contract and keep unit lanes
    excluding `integration_db`, `db_direct`, `live_worker`, and `e2e` runtime markers.
    Concurrency and duplicate-delivery proof now lives in
    `docs/standards/concurrency-duplicate-delivery-test-pack.v1.json` and is enforced by
    `make concurrency-duplicate-delivery-guard` through `make lint`. When touching idempotency
    fences, semantic event identity, consumer replay, outbox claim/result handling, worker
    claim/reset logic, epoch fences, dirty-window propagation, or correction/cancellation
    recalculation behavior, update the pack and add deterministic tests that assert durable final
    state, emitted event count where applicable, version/epoch behavior where applicable, and
    operator-visible job/retry state. Do not rely on unbounded sleeps as the primary concurrency
    trigger; use barriers, callback outcomes, database constraints, claim tokens, and explicit
    transactions.
    Cross-product transaction and corporate-action golden examples now live in
    `tests/fixtures/cross-product-transaction-golden-scenarios.v1.json` with governance in
    `docs/standards/cross-product-golden-regression-pack.v1.json`; `make
    cross-product-golden-regression-guard` is wired into lint. When changing transaction lifecycle,
    cash/product leg mapping, cost basis, income/cashflow classification, valuation assumptions,
    corporate-action legs, or lineage/correlation behavior, update the reusable fixture and add
    executable lowest-meaningful-level assertions first. Product families that are not yet fully
    executable must remain explicit `implemented_with_gaps` entries with expected state sections,
    executable target-gap assertions where possible, and linked follow-up ownership instead of
    disappearing from the golden pack. Do not mark target-model-only product mechanics as
    production-booking supported merely to close a test-suite issue.
    Command API behavior certification now lives in
    `docs/standards/command-api-behavior-certification-pack.v1.json`; `make
    command-api-behavior-certification-guard` is wired into lint. When changing ingestion write
    commands, event replay retry/repair/DLQ replay/ops-control commands, financial reconciliation
    control commands, idempotency behavior, runtime-mode or policy blocking, dependency-failure
    mapping, post-publish bookkeeping recovery, or security-denied command responses, keep
    route-surface evidence for accepted, duplicate, conflict, malformed, blocked, retryable
    failure, bookkeeping failure, and denied outcomes in that pack instead of relying on service
    tests alone.
41. Runtime configuration is becoming strict outside local/development/test profiles. Invalid
    bounded ingestion settings for rate limits, replay caps, worker polling and batching, scheduler
    dispatch, operating bands, and calculator lag JSON raise `IngestionConfigurationError` when
    `LOTUS_CORE_STRICT_CONFIG_VALIDATION=true` or non-local `ENVIRONMENT` is active; local profiles
    retain explicit warning-backed fallback. Query-service and query-control-plane settings use the
    shared `portfolio_common.runtime_settings` strict/local parser for bool, int, string, and JSON
    object settings while preserving their public helper wrappers. Common outbox and valuation
    runtime settings also use the shared parser while preserving existing local fallback and clamp
    semantics. Ingestion write rate-limit scope truth is guarded by
    `make ingestion-rate-limit-scope-guard`; `local_process` must remain documented as per-process
    defense in depth, not as global service-level enforcement, unless a gateway-backed scope and
    gateway policy ID are configured. Gateway-backed ingestion write limiting now has a
    repo-owned policy contract at
    `contracts/operational-controls/ingestion-write-rate-limit-gateway-policy.v1.json`. The
    `make ingestion-gateway-rate-limit-policy-guard` target keeps the policy ID, endpoint coverage,
    default budgets, bounded denial labels, and platform-runtime validation boundary synchronized.
    `make monetary-float-guard` uses token-aware money-like matching and currently has zero active
    findings and zero allowlisted suppressions.
42. Service runtime import correctness is now part of the architecture guard. Service code under
    `src/services/<service>/app` must not import its own application package through the repo-root
    path `src.services.<service>.app...`; use relative imports so the same code works in repo-root
    tests, app-local compose mounts, and installed wheel/container runtime. `make architecture-guard`
    enforces this to prevent CI-only Docker readiness failures caused by packaging path drift.
43. Canonical transaction-type classification now starts in
    `portfolio_common.domain.transaction.type_registry`. New or changed transaction types in cost,
    cashflow, position, query, validation, or RFC target work must be classified there first.
    `OTHER` is migration-only and not production-booking allowed. Redemption and
    conversion/exercise target types are known but not implemented until dedicated runtime slices
    add validation, cost, position, cashflow, supportability, and downstream compatibility proof.
    `SPIN_IN` and `DEMERGER_IN` are position transfer inflows; keep position rule tables aligned
    with registry-classified target-security inflow legs.
    Cost-basis calculation must fail closed for registry-classified migration-only or
    target-not-implemented
    types such as `OTHER`; production-booking cost enum values need explicit strategy mappings.
    Query projected-position quantity and cash-position effects are registry-derived from
    production-booking `position_effect` semantics and must not reintroduce local duplicated sets.
    Cashflow transfer-sign sets are registry-derived for production-booking transfer,
    corporate-action, and rights transaction types; keep current fallback-signed exceptions such as
    `CASH_IN_LIEU` explicit and behavior-tested before changing lifecycle semantics.
    FX business transaction types for validation and linkage enrichment are registry-derived;
    keep FX component types separate because they describe component rows rather than booking
    transaction types.
    Portfolio-flow no-auto-generate guardrail sets are registry-derived from production-booking
    `cash_movement`, `expense`, and `transfer` lifecycle families through the shared lifecycle
    selector.
    Auto-generated adjustment cash-leg eligibility is registry-derived from production-booking
    trade and income transaction types with direct inflow/outflow cash effects and required cash-leg
    settlement; amount, direction, and reason formulas remain explicit resolver behavior.
    Cost-engine cash dependency sort sets are registry-conformance guarded. Do not derive them from
    product-leg `cash_effect` until cash-leg transaction direction is modeled explicitly because
    cash rows intentionally invert trade labels (`BUY` cash rows are inflows; `SELL` cash rows are
    outflows).
    E2E transaction-type coverage support derives supported types, transfer sign sets, cash
    instrument routing, and no-cashflow-rule exceptions from the registry while preserving
    migration-only `OTHER` coverage and explicit fallback exceptions.
44. Keep `portfolio_common` limited to demonstrated multi-capability contracts, immutable value
    objects, and pure infrastructure primitives. Service-specific domain policy, application
    workflow, DTO mapping, repositories, and persistence behavior belong under the owning service
    even when another service has similar code. Shared async decorators must preserve concrete
    `Coroutine` signatures with `ParamSpec`; a broader `Awaitable` return weakens structural port
    conformance. `mypy.ini` exposes the worktree-local common library and follows only deliberately
    typed shared modules so strict service checks do not depend on a stale editable installation or
    implicitly opt the whole legacy common package into typed ownership. `make typecheck` includes
    the complete `portfolio_transaction_processing_service/app` tree; do not narrow that scope when
    adding modules or resolving unrelated legacy typing debt.

## Defect Tracking During Refactoring

Do not leave actionable defects, architecture gaps, correctness risks, or deferred cleanup only in
chat, local notes, or commit messages. When a refactor or GitHub issue fix exposes work that will not
be completed in the current slice:

1. search open and closed GitHub issues using both the broad failure pattern and concrete symbols,
   routes, tables, services, or files;
2. reuse and update the existing issue when it owns the root cause;
3. otherwise raise one focused issue with current evidence, expected standard, impact, owner
   boundary, acceptance criteria, evaluation condition, non-goals, related work, and recheck trigger;
4. link child issues to the active parent/refactor issue and update the issue-discovery ledger;
5. when the correct owner is another Lotus application, raise or reuse linked issues in both the
   source and destination repositories; record the field/capability ownership matrix, producer and
   consumer contract, compatibility window, migration order, rollback, and cross-repo validation;
6. keep speculative, stale, or not-yet-actionable observations in the codebase review ledger until
   they have enough evidence to become useful issues.

Issue labels and chat summaries are visibility aids, not closure proof. An issue is locally fixed
only when implementation, meaningful tests, contract/docs/context truth, same-pattern review, and
focused validation evidence are committed. Close only after merge to `main` and post-merge QA.

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
6. `src/services/portfolio_derived_state_service/`
   Position and portfolio time-series materialization through separate application/domain modules
   in one supervised deployable.
7. `scripts/`
   quality gates, performance and recovery gates, test-manifest orchestration, and operational tooling.
8. `tests/`
   unit, integration-lite, full integration, ops-contract, transaction-contract, e2e, Docker smoke, and performance-oriented coverage.
9. `contracts/domain-data-products/`
   Repo-native RFC-0086 domain-product producer declarations for governed `lotus-core` source-data
   products.
10. `contracts/trust-telemetry/`
    Repo-native RFC-0087 trust telemetry fixtures for the currently covered
    `PortfolioStateSnapshot:v1` and `DpmSourceReadiness:v1` products.
11. `wiki/`
   canonical authored source for GitHub wiki publication and core-owned operator and onboarding summaries.
12. `docs/architecture/README.md`
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
5. repository-wide lint and format plus governed contract guards
   `make lint`
6. targeted unit gate
   `make test`
7. database-backed unit gate
   `make test-unit-db`
8. integration-lite suite
   `make test-integration-lite`
9. boundary mapping conformance
   `make test-boundary-mapping-conformance`
10. E2E smoke
   `make test-e2e-smoke`
11. Docker smoke
   `make test-docker-smoke`
12. repo-native domain-product validation
   `make domain-product-validate`
13. app-level supported-surface validation
   `make lotus-core-validate`
14. documentation release evidence pack
   `make docs-evidence-pack`
15. verified API example catalog
   `make api-example-catalog-guard`
16. generated API route catalog
   `make api-route-catalog-guard`
17. front-door synchronization guard
   `make front-door-sync-guard`

All Python-backed Make recipes route through
`python scripts/development/repository_python.py`. The launcher prepends this invoking checkout's
repository and shared `portfolio-common` roots, filters inherited paths from other `lotus-core*`
worktrees, proves first-party source origin before delegation, uses `shell=False`, and preserves the
child exit code. Bootstrap verifies installed provenance through a fresh interpreter with inherited
`PYTHONPATH` removed and unsafe-path insertion disabled; do not rely on optional editable-install
metadata as the execution contract. Do not use an ambient editable install or another worktree's
`PYTHONPATH` as validation evidence. Use `make install` to repair import provenance and invoke direct
diagnostics through the launcher when a Make target is not available.

## Validation And CI Expectations

`lotus-core` uses explicit CI lanes with a much heavier validation contract than most repos.

Important validation expectations:

1. architecture guards, OpenAPI gates, warning budget, vocabulary, source-data product, and contract gates are active,
2. PR-grade validation includes runtime gates, Docker smoke, latency, and performance load checks,
3. main releasability extends PR validation with heavier release-only gates,
4. deterministic test-manifest orchestration is part of the repo truth and should not be bypassed casually,
5. repo-local wiki and README content should stay limited to current `lotus-core` ownership and
   should not re-import ecosystem-wide or commercial narrative that now belongs in `lotus-platform`.
6. service-runtime packaging/import checks are part of architecture validation: when a slice touches
   service app imports, Dockerfiles, compose mounts, or package metadata, run `make architecture-guard`
   plus a focused runtime import proof. For PowerShell, set
   `$env:PYTHONPATH="$PWD/src/services/<service>"`, then run
   `python scripts/development/repository_python.py -c "import app.main"`; the launcher adds current
   repository/shared-library roots while retaining only the explicitly selected service-local
   `app` root.
7. PR documentation acceptance is explicit: if a change affects routes, contracts,
   supported features, operational behavior, security posture, validation lanes, service
   boundaries, README, architecture docs, API catalog, RFCs, runbooks, wiki source,
   repository context, or platform context, update the relevant source-of-truth docs in the
   same slice or record a concrete no-doc-change rationale in the PR template. Wiki source
   changes require a post-merge publication evidence plan.
8. Supported-feature publication is manifest-backed. Keep
   `contracts/supported-features/lotus-core-supported-features.v1.json`,
   `docs/features/supported-features.md`, and `wiki/Supported-Features.md` aligned through
   `make supported-features-guard`. The manifest is the canonical place to record capability
   owner, implementation modules/routes, source-data products, tests, validation evidence,
   current status, fail-closed limitations, safe demo claims, prohibited claims, and downstream
   ownership caveats.
9. Incident playbooks are contract-backed. Keep
   `contracts/operations/incident-playbooks.v1.json`,
   `docs/operations/Incident-Playbooks.md`, `docs/operations/runbook.md`,
   `wiki/Operations-Runbook.md`, and `wiki/Troubleshooting.md` aligned through
   `make incident-playbook-guard`. Every runtime failure family must include symptoms, metrics,
   API checks, read-only database checks, expected fields, containment, escalation, and
   post-incident evidence. Do not add destructive commands to operator playbooks.

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
12. route removal, deprecation, or monitored convenience-route growth must follow `docs/architecture/RFC-0083-endpoint-consolidation-disposition.md`, update `docs/standards/endpoint-consolidation-watchlist.json` and the route-family registry when routes change, pass `make endpoint-consolidation-watchlist-guard`, and carry affected-consumer evidence,
13. future source-data product security, retention, audit, capability, and entitlement changes must use `docs/architecture/RFC-0083-security-tenancy-lifecycle-target-model.md`, `src/libs/portfolio-common/portfolio_common/source_data_security.py`, and `src/libs/portfolio-common/portfolio_common/enterprise_readiness.py`; they must keep generated `x-lotus-source-data-security` route metadata and catalog-derived capability rules aligned with the governed profile and avoid reintroducing duplicated service-local authorization or audit middleware logic,
14. future event, outbox, replay, DLQ, direct Kafka publish, and operator diagnostic changes must use `docs/architecture/RFC-0083-eventing-supportability-target-model.md`, `src/libs/portfolio-common/portfolio_common/event_supportability.py`, `src/libs/portfolio-common/portfolio_common/events.py`, and the centralized payload envelope in `src/libs/portfolio-common/portfolio_common/outbox_repository.py`; they must pass `make event-runtime-contract-guard` when outbox emissions, direct publish topics, or Kafka topics are touched. Failed outbox diagnostics belong on the QCP operator surface through source-safe row views such as `GET /support/outbox/failed-events`; do not expose raw outbox payloads. Failed outbox recovery must use governed commands such as `POST /support/outbox/failed-events/{outbox_id}/requeue`, persist actor, reason, correlation, prior/new status, and outcome evidence in `outbox_recovery_audit` rather than relying on direct database status updates, expose recovery history through source-safe QCP audit views such as `GET /support/outbox/recovery-audits`, emit only bounded fleet-level metrics such as `outbox_recovery_attempts_total` without `outbox_id`, `correlation_id`, `requested_by`, raw reason text, or business identifiers as metric labels, keep DB-backed integration tests proving dispatcher-created terminal failures can be diagnosed, governed-requeued, audited, and processed by the dispatcher afterward, and preserve W3C `traceparent` as governed trace context across HTTP bootstrap, outbox payloads, Kafka headers, shared consumers, DLQ publication, and replay while keeping `correlation_id` as the Lotus operator correlation key. Standard HTTP bootstrap must preserve valid inbound `traceparent`; when deriving `traceparent` from `X-Trace-Id` or generating fresh trace context, use non-zero W3C span IDs through `portfolio_common.logging_utils` and do not reintroduce fixed synthetic span IDs,
15. future boundary mapping changes should follow `docs/architecture/mapping-anti-corruption-boundary.md` and pass `make test-boundary-mapping-conformance` when API DTO, event, persistence-record, read-record, or source-data envelope mappings are touched,
16. RFC-0083 target-model closure is tracked by `docs/standards/rfc-0083-implementation-ledger.json` and guarded by `make rfc0083-closure-guard`; the ledger intentionally does not claim full production runtime closure,
17. borderline analytics-input/reference contracts in `query_control_plane_service` must be reviewed against `docs/architecture/RFC-0082-contract-family-inventory.md` before material expansion,
18. app-local compose is useful, but canonical shared infrastructure governance now belongs in `lotus-platform`,
19. because operational correctness matters here, failure-recovery and performance gates are part of real delivery quality, not optional extras.
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
    workload: use `scripts/operations/bank_day_load_reconciliation_report.py` against the completed `run_id`
    to collect sampled or exhaustive reconciliation proof for positions, transactions, support
    overview state, and timeseries-integrity findings.
27. institutional sign-off evidence selection must prefer the strongest available proof, not just
    the newest artifact timestamp: use `full` profile-tier performance-load artifacts ahead of
    newer `fast` artifacts, and prefer exhaustive bank-day reconciliation artifacts where
    `portfolio_count_evaluated == portfolios_ingested` ahead of newer sampled refresh artifacts,
28. scheduled and manually dispatched main releasability runs own the governed RFC-086
    institutional completion gate that runs the bank-day load scenario and then exhaustive
    reconciliation for the generated run before the institutional sign-off pack aggregates
    artifacts; routine `main` push runs keep the lighter release gates blocking and leave the
    approval-grade institutional lane to the scheduled/manual path,
29. legacy PAS-era wiki material should be filtered through the platform migration ledger before
    reuse; cross-cutting investor, GTM, or ecosystem rationale now belongs in `lotus-platform`.
30. RFC-087 DPM source-data work is implemented for `DpmModelPortfolioTarget:v1`,
    `DiscretionaryMandateBinding:v1`, `InstrumentEligibilityProfile:v1`,
    `PortfolioTaxLotWindow:v1`, `TransactionCostCurve:v1`,
    `MarketDataCoverageWindow:v1`, `DpmSourceReadiness:v1`, and
    `PortfolioManagerBookMembership:v1`, `PortfolioPartyRoleAssignment:v1`,
    `CioModelChangeAffectedCohort:v1`, and
    `DpmPortfolioUniverseCandidate:v1`, with product-specific APIs, ingestion/persistence support
    where core owns source state, route-family metadata, source-data security, domain-product
    declarations, OpenAPI proof, live validator coverage where applicable, and canonical
    front-office seed support for `PB_SG_GLOBAL_BAL_001`.
31. RFC42-WTBD-006 source-owner methodology depth now includes the implementation-backed
    `TransactionLedgerWindow:v1` methodology under
    `docs/methodologies/source-data-products/transaction-ledger-window.md`; it pins row filtering
    by portfolio, instrument/security, transaction type, FX/event linkage, date window, and
    effective as-of date; joined transaction-cost and cashflow row preservation; optional
    field-aware reporting-currency restatement from latest available FX rates, including explicit
    row-level realized FX P&L local evidence restated from trade currency when present; empty,
    complete, and paged window data-quality posture; and
    explicit boundaries from tax advice, FX attribution, cash aggregation, transaction-cost
    methodology, execution quality, and OMS acknowledgement.
32. RFC42-WTBD-006 source-owner methodology depth now includes the implementation-backed
    `PortfolioCashflowProjection:v1` methodology under
    `docs/methodologies/source-data-products/portfolio-cashflow-projection.md`; it pins the
    booked-only versus projected modes, latest-cashflow-row selection, settlement-dated external
    `DEPOSIT`/`WITHDRAWAL` inclusion rule, same-day booked/projected additivity with separate
    booked and projected component fields, portfolio-base currency convention, and explicit
    boundary from liquidity ladders, tax, performance, market-impact, and OMS execution
    methodology.
33. RFC42-WTBD-006 source-owner methodology depth now also includes the implementation-backed
    `TransactionCostCurve:v1` methodology under
    `docs/methodologies/source-data-products/transaction-cost-curve.md`; it pins observed
    booked-fee grouping by security, transaction type, and currency; explicit transaction-cost row
    precedence over `trade_fee`; zero-fee and zero-notional exclusion; notional-weighted average
    cost bps; min/max cost bps; deterministic paging; and the explicit boundary from
    market-impact, venue-routing, best-execution, OMS acknowledgement, and minimum-cost execution
    methodology.
34. RFC42-WTBD-006 source-owner methodology depth now includes implementation-backed
    `ClientTaxProfile:v1` and `ClientTaxRuleSet:v1` methodologies under
    `docs/methodologies/source-data-products/client-tax-profile.md` and
    `docs/methodologies/source-data-products/client-tax-rule-set.md`; they pin effective-dated
    discretionary mandate resolution, profile/rule selection and deduplication, supportability
    states, lineage, source-record identity, and explicit boundaries from tax advice, after-tax
    optimization, tax-loss harvesting suitability, client-tax approval, jurisdiction-specific
    recommendations, tax-reporting certification, best execution, and OMS acknowledgement.
35. RFC42-WTBD-006 source-owner methodology depth now includes the implementation-backed
    `PortfolioRealizedTaxSummary:v1` product and methodology under
    `docs/methodologies/source-data-products/portfolio-realized-tax-summary.md`; it pins
    portfolio/date/as-of transaction filtering, explicit withholding-tax and
    other-interest-deduction inclusion, currency-grouped totals, optional reporting-currency
    restatement from latest available FX rates, evidence-row and source-window counts, and the
    explicit boundary from tax advice, after-tax optimization, tax-loss harvesting, client-tax
    approval, tax-reporting certification, execution quality, and OMS acknowledgement.
36. RFC42-WTBD-006 source-owner methodology depth now includes the implementation-backed
    `PortfolioCashMovementSummary:v1` product and methodology under
    `docs/methodologies/source-data-products/portfolio-cash-movement-summary.md`; it pins latest
    cashflow row selection by transaction epoch/id, bounded cashflow-date windows, grouping by
    classification, timing, currency, and flow scope, signed bucket totals, source row counts,
    movement direction, empty-window posture, and the explicit boundary from cashflow forecasting,
    funding recommendations, treasury instructions, liquidity advice, tax methodology, execution
    quality, and OMS acknowledgement.
37. RFC39-WTBD-008 now has active fail-closed `ExternalCurrencyExposure:v1`,
    `ExternalHedgePolicy:v1`, `ExternalEligibleHedgeInstrument:v1`,
    `ExternalFXForwardCurve:v1`, and `ExternalHedgeExecutionReadiness:v1`
    source-product routes at
    `/integration/portfolios/{portfolio_id}/external-currency-exposure`,
    `/integration/portfolios/{portfolio_id}/external-hedge-policy`,
    `/integration/portfolios/{portfolio_id}/external-eligible-hedge-instruments`,
    `/integration/market-data/external-fx-forward-curve`, and
    `/integration/portfolios/{portfolio_id}/external-hedge-execution-readiness`. They resolve
    portfolio mandate identity where portfolio-scoped, return `UNAVAILABLE` until bank-owned
    external treasury ingestion is certified, and publish required missing treasury data families
    plus blocked capabilities for downstream supportability gates. This boundary does not claim FX
    attribution, hedge advice, hedge-policy approval, eligible-instrument selection, product
    recommendation, forward pricing, FX valuation methodology, treasury instructions, counterparty
    choice, order generation, venue routing, best execution, OMS acknowledgement, fills,
    settlement, or autonomous treasury action. `ExternalEligibleHedgeInstrument:v1`,
    `ExternalFXForwardCurve:v1`, and `ExternalHedgeExecutionReadiness:v1` are pinned by
    implementation-backed methodology truth at
    `docs/methodologies/source-data-products/external-eligible-hedge-instrument.md`,
    `docs/methodologies/source-data-products/external-fx-forward-curve.md`, and
    `docs/methodologies/source-data-products/external-hedge-execution-readiness.md`.
38. RFC42-WTBD execution-boundary coverage now has active fail-closed
    `ExternalOrderExecutionAcknowledgement:v1` at
    `/integration/portfolios/{portfolio_id}/external-order-execution-acknowledgement`. It resolves
    portfolio mandate identity, returns `UNAVAILABLE` until bank-owned OMS acknowledgement ingestion
    is certified, publishes missing OMS data family plus blocked capabilities for downstream
    supportability gates, and is pinned by the implementation-backed methodology at
    `docs/methodologies/source-data-products/external-order-execution-acknowledgement.md` without
    claiming order generation, venue routing, best execution, OMS acknowledgement, fills,
    settlement, execution-status certification, or autonomous execution action.
39. The canonical front-office seed now derives its Core portfolio `advisor_id` from the platform
    canonical front-office contract's RFC-0026 advisor-cockpit scenario, with fallback
    `advisor_sg_001`. This keeps Core portfolio master membership aligned with downstream
    advisor-cockpit validation instead of hard-coding a separate relationship-manager identifier.
    It separately derives and persists the canonical `PM_SG_001` portfolio-management assignment
    through `/ingest/portfolio-party-role-assignments`; `advisor_id` remains compatibility-only.
    Canonical verification must observe the portfolio through Gateway with
    `governed_role_assignment` lineage and current source evidence before Workbench proof can pass.
    `tools/validate_front_office_advisor_book_seed.py` exercises the same bundle and dependency-
    ordered request builders as the live seed and is the cross-repository contract proof. Its
    structured evidence must bind portfolio and manager identity, governed business date, role and
    scope, effective interval, assignment version, source system/record/product, observation time,
    quality status, ingestion endpoint, and exact assignment count; partial identity evidence is
    not canonical seed proof. The reported source product must be resolved from Core's executable
    source-data-product registry and match the Platform contract; echoing contract text is not
    product-binding evidence. The same proof must bind the single governed PM-book route, exact
    approved Gateway/Manage consumer set, Core ownership, query-control-plane serving plane, and
    analytics-input route family before returning `pass`.
    Canonical parent reference ingestion remains asynchronous: before posting eligibility or other
    dependent reference products, the seed must prove every unique instrument is query-visible
    within a bounded wait and fail closed with the unresolved security ids. Local reseed fence
    cleanup must use the governed physical topic identity (`instruments.received-*`), not a logical
    or obsolete alias. The complete cleanup must remain one `ON_ERROR_STOP` PostgreSQL transaction
    and include every direct portfolio foreign-key child, so schema drift rolls back before retry
    instead of leaving `PB_SG_GLOBAL_BAL_001` partially deleted.
    Clean bootstrap must also persist FX and market-price histories and fail closed on their bounded
    query-visibility fences before activating the business-date horizon; no-horizon observations
    are initial source facts, while existing-horizon backdated and future observations retain
    durable correction replay. Transactions follow calendar activation so their readiness events
    own the first valuation pass.
40. `PerformanceComponentEconomics:v1` is active at
    `/integration/portfolios/{portfolio_id}/performance-component-economics` for
    `lotus-performance` contribution analytics sourcing. It returns source-authored transaction,
    cashflow, fee, tax, income, realized P&L, and FX-context economics evidence with component
    totals, coverage metadata, runtime source-product metadata, and lineage. It does not calculate
    contribution, attribution, performance returns, tax advice, execution quality, best execution,
    or OMS acknowledgement; downstream `lotus-performance` consumption and UI/gateway proof remain
    separate work.
41. `HoldingsAsOf:v1` cash balances now publish Core-owned `source_reported_cash_weight`,
    denominator, and supportability posture from same-date portfolio market-value snapshot
    evidence. The cash-balance response also publishes a deterministic evidence fingerprint and
    `holdings_as_of_cash_balances:<fingerprint>` snapshot identity for downstream lineage and replay.
    Cash-balance rows publish `cash_account_id_source`; transaction-derived fallback account ids
    must validate against active/effective `cash_account_masters`, and unresolved cash-security
    fallback identity is `PARTIAL` quality rather than governed account evidence. Raw transaction
    persistence uses `raw_transaction_cash_account_reference_policy_v1`; unresolved settlement
    cash-account references may land only as provisional raw evidence and must remain blocked or
    degraded downstream until active/effective cash-account master data exists. `lotus-idea` is an
    approved consumer for high-cash source evidence, but it must consume the field and source
    identity instead of reconstructing cash weight from Core-owned portfolio facts. This evidence is
    not liquidity advice, cash-deployment recommendation, performance methodology, risk
    methodology, or OMS acknowledgement.
42. Cost-calculator product transaction processing requires instrument master data before
    cost-basis processing, transaction-cost persistence, BUY lot-state persistence, or processed
    event publication. Missing product instrument references are retryable reference-data
    dependencies, not normal cost/lot writes; FX contract and pure adjustment flows keep their
    specialized creation/validation paths. Raw transaction persistence uses the explicit
    `raw_transaction_instrument_reference_policy_v1` policy: unresolved instrument references may
    land as provisional raw evidence for source-batch ordering tolerance, but they remain blocked
    from downstream lifecycle processing and are surfaced through read-side supportability.
43. Cashflow-calculator transaction processing uses a classify-then-finalize unit-of-work pattern:
    branch helpers return typed processing outcomes and a single application boundary owns commit
    or rollback. Preserve this pattern for replay, duplicate, epoch-fence, lifecycle, and
    cashflow/outbox atomicity changes; do not reintroduce helper-owned transaction finalization.
44. `TransactionLedgerWindow:v1` now checks returned row security ids against governed instrument
    master data. Missing instrument references are additive read-side supportability evidence:
    `data_quality_status=PARTIAL`, `TRANSACTION_LEDGER_INSTRUMENT_REFERENCE_MISSING`, and bounded
    missing-security fields. Preserve this degraded-reference pattern for legacy/orphan rows while
    broader ingestion and tax-lot reference policies are completed.
45. `PortfolioTaxLotWindow:v1` now applies the same degraded-reference pattern for returned lot
    rows. Missing instrument master support is exposed through
    `TAX_LOTS_INSTRUMENT_REFERENCE_MISSING`, `missing_instrument_security_ids`, and
    `data_quality_status=PARTIAL` while preserving existing lot evidence and requested-security
    missing-lot supportability.
46. Service self-imports must preserve runtime package truth. Do not reintroduce
    `src.services.<same_service>.app...` imports inside a service package; they can pass repo-root
    tests while failing in installed service images. Prefer relative imports for same-service code,
    shared libraries for durable cross-service contracts, and explicit migration plans for
    transitional cross-service app imports that are still mounted in compose.
47. FX contract lifecycle rows use service-owned transaction-domain cashflow semantics. `FX_CONTRACT_OPEN`
    and `FX_CONTRACT_CLOSE` are non-cashflow processing types: they carry position exposure, while
    settlement cash movements are represented by separate FX cash settlement rows. Cashflow
    consumers, pipeline readiness, reconciliation, and future supportability code must use
    `portfolio_transaction_processing_service.app.domain.transaction.requires_cashflow_processing(...)`
    instead of duplicating
    local FX lifecycle skip lists.
48. Runtime CI gates that bring up the compose-backed stack consume one exact-source image set per
    workflow SHA. The existing `Validate Docker Build` job is the sole producer after coverage; it
    builds the ordered PR or main service union, coalesces services that use the same Dockerfile,
    exports one portable bundle, and publishes build timings plus a deterministic integrity
    manifest. Every Docker-backed consumer must download and run `runtime_image_set.py load-verify`
    against `GITHUB_SHA` before startup. Keep `kafka-topic-creator` and `migration-runner` in the
    runtime image set for Docker smoke, E2E, latency, performance, failure-recovery, and
    institutional-completion gates. E2E diagnostics should be captured by the pytest fixture
    through `LOTUS_TESTS_COMPOSE_LOG_FILE` before compose teardown; workflow-level `docker compose
    logs` capture is only fallback evidence after fixture ownership is gone.
    Service Dockerfiles must keep the governed image provenance block: OCI labels and matching
    runtime environment values for Git commit SHA, Git branch, build timestamp, repo URL, image
    version, image digest, and CI pipeline/run ID. `configure_standard_http_app` registers
    `GET /version` so API services and worker health web apps expose the same metadata plus the
    OCI label map used for release-manifest parity checks. `/health/live` and `/health/ready`
    expose a bounded runtime block with the same build metadata, service app version, environment,
    runtime profile, started-at time, and uptime for safe incident diagnostics.
    `scripts/release/prebuild_ci_images.py` supplies build args and timing evidence in CI,
    `scripts/release/runtime_image_set.py` owns ephemeral cross-job transport and exact-source
    verification, and `scripts/release/write_build_provenance.py` records matching build evidence.
    `.github/workflows/image-release.yml` remains the only image-push path, and
    `scripts/release/write_image_release_manifest.py` records digest, OCI label parity, SBOM, scan,
    signing, provenance-attestation, digest-deploy, and same-image-promotion evidence across `dev`,
    `uat`, and `prod`. `make image-provenance-guard` blocks drift,
    including secret-like Dockerfile/workflow build ARG or ENV additions. Local builds may report
    `LOTUS_IMAGE_DIGEST=unknown` until a release lane or deploy manifest supplies the resolved
    digest.
    Architecture documentation metadata is now governed by
    `docs/architecture/architecture-documentation-catalog.v1.json`. The catalog distinguishes
    current-state truth, review evidence, historical context, templates, and catalog metadata, and
    links architecture docs back to API catalog, RFC ledger, runbook, supported-feature, and wiki
    surfaces. `make architecture-docs-catalog-guard` runs directly and through
    `make architecture-guard`; it fails when a new `docs/architecture` Markdown or JSON document is
    neither explicitly cataloged nor covered by an intentional rule such as `CR-*` review evidence.
    Compose-backed latency and load evidence must distinguish service health, source-ingestion
    completion, and downstream data-product readiness. A successful one-shot seed loader does not
    prove valuation, timeseries, aggregation, or other asynchronous projections are query-ready.
    Before warmup or timing, preflight the actual measured source-backed contracts and require three
    consecutive ordered all-2xx sweeps at the governed poll interval. Reset the stability fence on
    any non-2xx or transport failure and propagate seed failure immediately. Keep permanent failures
    fail-closed with endpoint-specific and observed/required stability diagnostics; never count
    convergence requests as latency samples or weaken budgets to hide a readiness race. Validate
    operator-supplied stability controls at argument parsing before service, seed, context, or
    session work, while retaining helper validation for direct callers.
49. GitHub Security automation coverage is governed as repository truth. `.github/dependabot.yml`
    covers GitHub Actions, every governed Python dependency manifest, and every runtime service
    Dockerfile. Routine Dependabot version-update PR churn is currently paused with
    `open-pull-requests-limit: 0` while issue-closure PRs are stabilized; reviewed bot suggestions
    should be cherry-picked into governed dependency or CI slices with local gates. Keep
    `tests/unit/test_dependabot_security_coverage.py` aligned with new service manifests or
    Dockerfiles so supply-chain coverage cannot silently drift. Repository admins still need to
    enable Dependabot alerts/security updates and CodeQL/default code scanning in GitHub settings;
    the repo file does not enable those settings by itself.
50. Cost-calculator persistence boundaries must strip event-envelope fields before transaction-table
    upserts. `TransactionEvent` carries governed event fields such as `event_type`,
    `schema_version`, and `correlation_id` that are not `transactions` columns. Use the persistence
    service event-record mapper and the SQLAlchemy table-column whitelist in the cost repository
    instead of persisting event DTO dictionaries directly; this prevents FX lifecycle rows from
    DLQing when event-envelope metadata is present.
51. `PortfolioMaturitySummary:v1` is the Core-owned maturity posture contract for downstream
    opportunity and review workflows. It is served by `query_service` at
    `/portfolios/{portfolio_id}/maturity-summary`, reuses the existing `HoldingsAsOf:v1` read path,
    publishes `next_maturity_date`, `maturing_holding_count`, freshness, supportability reasons,
    and deterministic input/calculation/output lineage. The trust-certified receipt is booked-only,
    carries caller tenant and correlation scope, binds deterministic HoldingsAsOf snapshot/content/
    source-batch/policy identity, and derives reconciliation from one set-based read of each
    collective selected portfolio-day scope at its maximum valid row epoch. Per-security epochs
    are last-mutation versions, so the financial position-valuation control must read the latest
    row per security at or below that target epoch rather than only rows equal to it. Missing,
    incomplete, stale, failed, replay-required,
    unknown, or source-newer-than-control evidence must not produce `SUPPORTED`. This prevents
    downstream services such as `lotus-idea` from
    reconstructing maturity windows from raw holdings rows. The current implementation is
    contractual-instrument-maturity-date evidence only; callable, putable, amortizing,
    structured-note, lockup, expiry, liquidity, reinvestment, performance, risk, tax, execution,
    and OMS methodology remain outside this product unless Core reference data and methodology
    expand explicitly.
52. Source-data lineage fixes should be executed category-wise: fix every active product in the
    defect pattern that can be safely corrected, then promote the rule into the source-data product
    contract guard. `source_batch_fingerprint` is upstream source-batch lineage only. Request,
    pagination, and response snapshot identity must remain in request/snapshot fields such as
    `snapshot_id` or `request_scope_fingerprint`. Proof-facing Core source products consumed by
    `lotus-idea` must emit Core-owned `generated_at`, `content_hash`/`source_digest`,
    `source_refs`, `source_evidence_current`, and `freshness_status` evidence; when downstream
    proof tooling requires `source_batch_fingerprint`, emit the deterministic content hash through
    the shared runtime metadata helper rather than making the consumer synthesize authority.
    Legacy products without true source-batch or proof-fingerprint evidence should continue to
    return `source_batch_fingerprint: null`. `make source-data-product-contract-guard` now blocks
    `request_fingerprint(...)`, `snapshot_fingerprint`, and `request_scope_fingerprint` from being
    assigned to source-batch lineage.
53. Durable claim-and-publish scheduler loops must recover rows immediately when they directly
    observe Kafka publish or delivery-confirmation failure after claiming work into `PROCESSING`.
    Use the shared `portfolio_common.scheduler_dispatch_recovery` vocabulary and repository-level
    recovery methods for valuation and aggregation control queues. Preserve published versus
    unpublished record-key evidence where possible, requeue retryable rows to `PENDING`, mark rows
    at or above max-attempt policy `FAILED`, and keep stale-job reset as a crash/unknown-failure
    safety net rather than the primary recovery path for observed dispatch failures.
54. Inline analytics export jobs must have an explicit execution budget separate from stale
    in-flight reuse detection. `LOTUS_CORE_ANALYTICS_EXPORT_EXECUTION_TIMEOUT_SECONDS` bounds
    current `inline_job_execution` dataset collection and result materialization. Observed timeout
    or request cancellation must transition the durable analytics export job to `failed` with
    bounded reason text, preserve existing response contracts, and keep a future async export
    runner as a separate lifecycle-mode change rather than an implicit background task using a
    request-scoped database session.
55. Simulation session mutations use an application-owned unit-of-work boundary. Repositories stage
    session rows, change rows, status updates, and deletes only; `SimulationService` owns
    deterministic clock/ID providers, expiry calculation, version increments, commit/refresh, and
    rollback decisions. Do not reintroduce repository-owned commits, rollbacks, UUID generation, or
    clock reads when adding simulation audit, idempotency, replay, or lifecycle evidence.
56. Outbox dispatch uses leased claims and fenced result updates. Do not publish to Kafka or wait
    for producer flush while holding row locks from `FOR UPDATE SKIP LOCKED`. Claim `PENDING`
    outbox rows in a short transaction with `claim_token` and `claim_expires_at`, publish and flush
    outside the transaction, then update results only when the persisted `claim_token` still
    matches. Expired claims are reclaimable; stale delivery callbacks from a lost claim must not
    mark reclaimed rows `PROCESSED` or alter retry state.
57. Outbox retry policy must keep retry state explicit and observable. Retryable failures persist
    `next_attempt_at`; claim queries must skip rows waiting for a future retry window; max attempts
    remain the default terminal budget; `OUTBOX_DISPATCHER_RETRY_MAX_ELAPSED_SECONDS` is an
    optional elapsed terminal budget when configured above zero. Operator metrics must preserve the
    split between total pending, retry-eligible pending, retry-waiting pending, terminal failed, and
    published outcomes without high-cardinality or payload-derived labels.
58. FastAPI app security control coverage is governed by
    `contracts/security/security-control-coverage.v1.json` and enforced by
    `make security-control-coverage-guard` through `make lint`. Every active `main.py` or `web.py`
    FastAPI app under `src/services/**/app/` must be listed in the matrix and use the shared HTTP
    bootstrap for secure response headers, fail-closed CORS, trusted-host enforcement, metrics
    access policy, correlation and trace headers, and safe unhandled-error responses. Production-like
    profiles must set non-wildcard `LOTUS_HTTP_TRUSTED_HOSTS`; the wildcard default is only for
    local/dev/test compatibility. Business/operator HTTP apps must install enterprise
    audit/authorization middleware; health-only worker apps must be explicitly classified as
    health-only. Ingestion upload APIs are bounded by
    `LOTUS_CORE_INGEST_UPLOAD_MAX_BYTES` and return `INGESTION_UPLOAD_TOO_LARGE` for oversized
    payloads. Upload parsers must also enforce configured row, column, and cell-length budgets
    rather than relying only on HTTP byte limits. The guard is static repo evidence only; live
    ingress, IAM, WAF, network, and penetration-test proof remain separate higher-lane evidence.
59. App-level supported-surface validation is blocking in PR Merge Gate. The
    `lotus-core-validation-report` workflow job is retained as the stable job id, but its check name
    is `PR Merge Gate / Lotus Core Validation Gate`, it checks out `sgajbi/lotus-platform` into the
    workflow workspace, sets `LOTUS_PLATFORM_ROOT`, and runs `make lotus-core-validate`
    fail-closed. Do not reintroduce `continue-on-error`, `set +e`, warning-only exit handling, or
    `exit 0` around this command. Local runs still use the default sibling
    `../lotus-platform` path unless `LOTUS_PLATFORM_ROOT` is set explicitly.
60. Production-like `lotus-core` environments must use the shared production security profile
    unless a temporary opt-out is explicitly documented. `prod`, `production`, `preprod`,
    `pre-prod`, `pre-production`, `staging`, `stage`, and `uat` default
    `ENTERPRISE_ENFORCE_AUTHZ`, `ENTERPRISE_ENFORCE_READ_AUTHZ`, `ENTERPRISE_AUDIT_READS`,
    `ENTERPRISE_REQUIRE_CAPABILITY_RULES`, and `ENTERPRISE_ENFORCE_RUNTIME_CONFIG` to true through
    `portfolio_common.runtime_settings.production_security_profile_enabled(...)`. Local/dev/test
    environments stay opt-in. Do not add new service-local enterprise auth/audit flags with
    hand-written production defaults; use the shared profile helper so query service, query control
    plane, and future business/operator HTTP apps remain consistent. This is service-local proof;
    gateway/platform ingress and IAM closure still require higher-lane evidence.
61. Cost-basis FX processing uses the service-owned canonical FX baseline helper. `FX_SPOT`,
    `FX_FORWARD`, and `FX_SWAP` must route through
    `portfolio_transaction_processing_service.app.domain.transaction.fx.build_fx_baseline_processing_update(...)`
    after canonical
    FX validation instead of service-local pending strategies or duplicated realized-P&L mode
    branches. Baseline engine and consumer paths support `NONE` and `UPSTREAM_PROVIDED`
    `fx_realized_pnl_mode`; `CASH_LOT_COST_METHOD` remains an explicit future extension that must
    not be simulated without a governed cash-lot ledger, methodology, and tests.
62. Local cleanup is governed by `scripts/development/clean_generated_artifacts.py` and exposed through
    `make clean`. Keep cleanup policy explicit, repo-root scoped, and test-backed. It may remove
    ignored local caches, Python bytecode, build/package byproducts, coverage files, and generated
    `output/` evidence artifacts, but must preserve source, docs, wiki source, migrations,
    contracts, `.git`, virtual environments, and dependency directories. Do not reintroduce opaque
    inline cleanup commands in `Makefile`. After containment verification, Windows directory
    removal must use extended-length paths and bounded retry; persistent failures remain blocking.
    `make generated-artifact-tracking-guard` is the
    source-truth companion: it must fail if generated build, cache, package, coverage, or output
    evidence paths are tracked by Git. A local ignored `src/services/query_service/build/lib` tree
    is disposable workspace output, not authored implementation truth.
63. Ingestion audit and idempotency workflows must use explicit store ports before reaching
    SQLAlchemy helper functions. `IngestionJobStore` owns same-key idempotency replay/conflict
    semantics; `ReplayAuditStore` owns replay-audit duplicate lookup, audit persistence, audit
    reads, fail-closed typed audit-write behavior, and source-safe diagnostic metadata. Default
    runtime wiring may use SQLAlchemy-backed adapters, but `IngestionJobService` must call the
    ports for job creation/idempotency and replay audit workflows. `make architecture-guard` now
    runs `scripts/quality/ingestion_store_port_guard.py`; keep it green when adding diagnostics, DLQ event,
    ops-control, unit-of-work, or publisher ports. Ingestion job idempotency is endpoint plus
    `X-Idempotency-Key` plus canonical request payload fingerprint: keyed create/replay must
    acquire the transaction-scoped database lock before lookup/create, same payload replays the
    existing job across accepted/queued/failed states, different payload returns
    `409 INGESTION_IDEMPOTENCY_CONFLICT`, OpenAPI must expose the shared 409 response on every
    job-backed ingestion route, and diagnostics must classify same-endpoint payload conflicts
    separately from cross-endpoint key reuse.
    Observability contract evidence for HTTP app bootstrap, health/version/metrics surfaces,
    route-template metrics, trace/correlation headers, unsafe metric/log rejection, and source-safe
    diagnostics is governed by `docs/standards/observability-contract-test-pack.v1.json` and
    `make observability-contract-test-pack-guard`. Keep this pack current whenever middleware,
    metrics, tracing, structured logging, or operator diagnostics change; do not scatter
    observability proof across tests without updating the pack.
    Business-date ingestion lifecycle orchestration belongs in
    `BusinessDateIngestionCommandHandler`, not `routers/business_dates.py`. Keep empty payload,
    max-future-date, and monotonic calendar advancement in `BusinessDateIngestionPolicy`; keep
    write-mode checks, rate limiting, ingestion job create/replay, publish failure marking, and
    queued-state bookkeeping in the command handler; and keep the router limited to HTTP metadata,
    typed error mapping, and ACK assembly. Preserve the stable business-date failure codes when
    extending this path. This is an in-process design-modularity boundary, not a runtime service
    split.
64. Application event publishing must use `portfolio_common.event_publisher` ports rather than
    concrete Kafka producer APIs. `EventPublishRequest` carries topic, key, payload, headers,
    outbox id, and delivery callback metadata. `EventPublishResult` reports `success`,
    `retryable_failure`, `terminal_failure`, or `uncertain` delivery state. Ingestion publish paths
    map those results back to existing `IngestionPublishError` contracts; valuation job publishing
    uses the same port behind the scheduler-specific publisher wrapper. `make architecture-guard`
    now runs `scripts/quality/event_publisher_port_guard.py` to block governed ingestion and valuation
    application publisher paths from importing `KafkaProducer` or `get_kafka_producer` directly.
    Runtime dispatchers, consumer managers, aggregation scheduler publishing, and outbox
    publication are separate follow-up slices.
    The surviving pipeline Kafka consumers are portfolio-day delivery adapters only: decode and
    validate aggregation/reconciliation events, establish correlation context, delegate to
    `PipelineStageMessageHandler`, and map invalid payloads, retryable DB errors, or defensive
    failures to existing retry/DLQ behavior. Keep SQLAlchemy sessions, idempotency, portfolio-control
    stage persistence, outbox persistence, and `PipelineOrchestratorService` assembly behind the
    pipeline unit-of-work adapter. Portfolio-control blocking and stale-epoch policy belongs in
    `pipeline_stage_state_machine`; reconciliation-request and controls-event mapping belongs in
    `pipeline_event_factory`. Transaction readiness belongs to
    `portfolio_transaction_processing_service` and is staged after cost, position, and cashflow
    effects succeed in the same unit of work. Do not restore a `transactions.cost.processed`
    pipeline consumer, transaction-stage handler/service/repository path, or processed-transaction
    consumer group.
65. Application/source-data repository dependencies should use capability-specific ports before
    broad concrete repositories. `PortfolioTaxLotWindow:v1` now depends on
    `PortfolioTaxLotReader`, and financial reconciliation service orchestration now depends on
    reconciliation run-writer and evidence-reader ports through `ReconciliationRepositoryPort`
    instead of the concrete `ReconciliationRepository` type. Concrete SQLAlchemy repositories may
    implement multiple ports, but new use cases should name the narrow read/write capability they
    need, add fake-port behavior tests, and keep `make architecture-guard`
    (`scripts/quality/repository_port_guard.py`) green. This is design modularity inside existing
    deployables, not approval for a runtime service split.
66. Governed application ports are cataloged in
    `docs/architecture/application-port-capability-catalog.json` with the human companion
    `docs/architecture/application-port-capability-catalog.md` and standard
    `docs/standards/application-port-layer-standard.md`. Service-local ports should live under
    `src/services/<service>/app/ports/`; shared cross-service ports should live in the narrow
    shared library that owns the reusable contract. `make architecture-guard` now runs
    `scripts/quality/application_port_catalog_guard.py` before the specific port-regression guards, so new
    representative ports must keep port modules, symbols, adapters, consumers, standards, and guard
    references truthful. This catalog is not a claim that every dependency has been inverted; it is
    the governed entrypoint for implemented representative port patterns and follow-on slices.
67. Infrastructure adapters should translate concrete library failures into typed infrastructure
    errors before application workflows decide retry, DLQ, degraded response, operator attention, or
    API problem-detail behavior. The shared taxonomy lives in
    `portfolio_common.infrastructure_errors` and is documented in
    `docs/standards/infrastructure-error-taxonomy.md`. `KafkaEventPublisher` now returns typed
    Kafka infrastructure errors on publish back-pressure, terminal publish failure, and uncertain
    delivery confirmation while preserving existing `EventPublishResult` status fields. Replay
    audit persistence continues to fail closed with `InfrastructureAuditWriteFailed`, now backed by
    the shared taxonomy and source-safe diagnostics. Future repository, downstream HTTP, cache,
    storage, and configuration adapter slices should extend this taxonomy instead of raising raw
    `RuntimeError` or leaking concrete library exception classes into application workflows.
68. Application services with governed port boundaries must not reintroduce direct infrastructure
    dependencies. `make architecture-guard` now runs
    `scripts/quality/application_dependency_inversion_guard.py`, which protects the representative
    port-enabled ingestion job, ingestion publishing, `PortfolioTaxLotWindow:v1`, and financial
    reconciliation use cases from direct SQLAlchemy session imports, broad concrete repository
    imports, concrete Kafka producer APIs, and direct helper calls for capabilities that now have
    ports. This does not claim every query-service application service has been inverted; remaining
    direct `AsyncSession` and concrete repository construction in core snapshot, integration,
    portfolio, position, transaction, cash account, FX rate, price, and similar services remains
    follow-up migration scope. Preserve existing runtime deployables unless separate scaling,
    ownership, isolation, or operational evidence justifies a runtime service split.
69. Concrete infrastructure adapters should live behind `app/infrastructure` package boundaries or
    explicitly transitional legacy packages. `docs/standards/infrastructure-adapter-layer-standard.md`
    defines the repo-local adapter package contract. `IngestionJobStore` and `ReplayAuditStore`
    SQLAlchemy implementations now live in
    `src/services/ingestion_service/app/infrastructure/workflow_stores.py`, while the previous
    `app/adapters/ingestion_workflow_stores.py` module is a compatibility re-export only.
    `make architecture-guard` now runs `scripts/quality/infrastructure_adapter_layer_guard.py` so migrated
    concrete store wiring cannot drift back into the transitional adapter module. Existing
    `repositories`, `consumers`, `producers`, and `adapters` packages elsewhere remain transitional
    migration scope; do not treat them as approval for new concrete infrastructure coupling in API,
    domain, or application logic.
70. Repository modules should stage persistence changes and leave transaction completion to an
    explicit unit-of-work boundary. `docs/standards/repository-transaction-boundary-standard.md`
    defines the repo-local transaction ownership rule. `SimulationService` now uses the
    query-service `UnitOfWork` port and `SqlAlchemyUnitOfWork` infrastructure adapter for commit,
    rollback, and refresh behavior, while `SimulationRepository` remains a staging repository with
    no direct transaction completion. `make architecture-guard` now runs
    `scripts/quality/repository_transaction_boundary_guard.py`; direct repository `commit()` or
    `rollback()` calls are blocked unless explicitly registered as transitional. The current
    transitional exception is
    `query_control_plane_service/app/infrastructure/operations/repository.py` for operator
    control-plane status updates. The guard covers both legacy `app/repositories/` modules and
    modern repository adapters under `app/infrastructure/` so ownership moves cannot evade the
    transaction boundary.
71. Application command workflows should model idempotency, audit, correlation, command identity,
    and recovery evidence as reusable application policies instead of repeated local parameter
    plumbing. `docs/standards/application-workflow-policy-standard.md` defines the repo-local rule.
    The first representative workflow lives in
    `src/services/ingestion_service/app/application/workflow_policies.py`:
    `CorrelationContext`, `ApplicationCommandEnvelope`, `IdempotencyWorkflow`, and `AuditWorkflow`.
    `IngestionJobService` preserves its router-facing method signatures but now routes ingestion
    job duplicate/conflict behavior through `IdempotencyWorkflow` and consumer-DLQ replay audit
    writes through `AuditWorkflow`. `make architecture-guard` now runs
    `scripts/quality/application_workflow_policy_guard.py` so the representative path cannot bypass those
    policies. Broader command-handler extraction from routers and cross-workflow concurrency
    certification remain follow-up issue scope.
72. Application services should raise framework-independent application errors and leave HTTP,
    worker, consumer, and operator mapping to their entrypoint adapters. The first representative
    taxonomy lives in `src/services/ingestion_service/app/application/errors.py` with
    `ApplicationError`, `ValidationRejected`, and `UnsupportedOperation`. `UploadIngestionService`
    now raises those errors for upload validation failures, while
    `src/services/ingestion_service/app/routers/uploads.py` maps reason codes back to the existing
    HTTP 400/422 detail contract. `make architecture-guard` now runs
    `scripts/quality/application_error_taxonomy_guard.py` so the representative path cannot reintroduce
    FastAPI imports, `HTTPException`, or HTTP status mapping inside the application service.
    Broader application-error migration remains follow-up scope and should preserve API contracts
    with router mapping tests.
73. Application services should use command/query and result models instead of API DTOs as their
    internal use-case contracts. `docs/standards/application-command-result-standard.md` defines
    the repo-local rule. The first representative write workflow lives in
    `src/services/ingestion_service/app/application/upload_commands.py`; `UploadIngestionService`
    now accepts `UploadPreviewCommand` and `UploadCommitCommand` and returns application results
    while the upload router maps to/from public API DTOs. The first representative read workflow
    lives in `src/services/query_service/app/application/lookup_catalog.py`; `LookupCatalogService`
    now returns lookup application results while the lookup router maps them to `LookupResponse`.
    Core snapshot request fingerprinting now uses a canonical identity command from
    `src/services/query_control_plane_service/app/application/core_snapshot/identity_command.py`
    instead of API DTO JSON
    serialization side effects.
    `make architecture-guard` now runs `scripts/quality/application_command_result_guard.py` so the
    migrated representative services cannot reintroduce API DTO imports or response DTO return
    contracts, and core snapshot fingerprinting cannot return to `request.model_dump(mode="json")`.
    Remaining API DTO usage in broader application services is transitional backlog and should not
    be copied into new use cases.
74. The application layer now has a first-class repo-local contract in
    `docs/standards/application-layer-contract.md`. `app/application` and future `app/use_cases`
    packages own command/query handling, use-case orchestration, workflow policies, application
    errors, and calls to ports. They must not import FastAPI/Starlette, SQLAlchemy, concrete Kafka
    producers, repository implementations, producer infrastructure, or consumer infrastructure.
    `make architecture-guard` runs `scripts/quality/application_layer_contract_guard.py` to enforce this
    over current application packages in ingestion, query, event replay, and financial
    reconciliation services. Legacy `app/services` modules remain incremental migration scope, but
    new use cases should prefer `app/application` plus ports/adapters.
75. Ingestion business services and adapter-mode policy must stay framework-neutral. The repo-local
    standard lives at `docs/standards/ingestion-service-framework-boundary-standard.md`.
    `src/services/ingestion_service/app/dependencies.py` owns FastAPI dependency providers for
    ingestion publishing, reference-data ingestion, business-calendar policy composition, and
    adapter-mode HTTP `410 Gone` translation. `adapter_mode.py` raises
    `AdapterModeDisabledError`, while routers import `require_*_adapter_enabled(...)` providers
    from `dependencies.py`. `make architecture-guard` runs
    `scripts/quality/ingestion_service_framework_guard.py` to prevent FastAPI imports, `Depends(...)`,
    `HTTPException`, and `status.HTTP` mapping from returning to ingestion `app/services` modules
    or adapter-mode policy. This keeps current `app/services` modules directly constructable in
    tests while broader migration to `app/application` remains incremental issue scope.
76. Bulk upload handling is split into parser/validator, commit policy, and publisher adapter
    responsibilities. `docs/standards/bulk-upload-component-boundary-standard.md` defines the
    repo-local boundary. `BulkUploadValidator` in `upload_validation.py` owns CSV/XLSX parsing,
    header normalization, row normalization, DTO validation, and validation-report construction
    without FastAPI, Kafka, database, or ingestion-service dependencies. `UploadIngestionService`
    owns preview/commit policy and depends on the `UploadRecordPublisher` port. The
    `IngestionServiceUploadPublisher` adapter dispatches validated records to existing canonical
    ingestion publish methods. Upload parsing must stay budgeted by bytes, rows, columns, and cell
    length and must stream XLSX rows without materializing the whole worksheet. `make architecture-guard` runs
    `scripts/quality/upload_component_boundary_guard.py` so upload parsing and entity-specific publish
    dispatch do not drift back into the orchestration service.
77. Transaction replay planning is split from SQLAlchemy and Kafka adapters. The repo-local
    standard lives at `docs/standards/transaction-replay-boundary-standard.md`.
    `portfolio_common.reprocessing_replay` owns ordered transaction-id deduplication, explicit
    `ReplayCorrelationMetadata`, replay message planning, partial publish failure classification,
    and flush-timeout classification without `AsyncSession`, `KafkaProducer`, or global
    correlation context. `portfolio_common.reprocessing_repository` preserves the existing
    `ReprocessingRepository(db, kafka_producer)` public API while composing
    `SqlAlchemyTransactionReplayReader` and `KafkaTransactionReplayPublisher`; tests may use
    `ReprocessingRepository.from_ports(...)` with fake reader/publisher ports. `make
    architecture-guard` runs `scripts/quality/transaction_replay_boundary_guard.py` so event planning,
    deduplication, and correlation header construction do not drift back into the compatibility
    repository adapter.
78. Portfolio aggregation scheduler policy is split from global database sessions, concrete
    repositories, raw metric functions, system clocks, and transport publication. The
    repo-local standard lives at
    `docs/standards/aggregation-scheduler-boundary-standard.md`.
    `portfolio_derived_state_service.app.ports.aggregation_scheduler_ports` owns repository-provider,
    repository, metrics-sink, clock, token-generator, and batch-processor contracts;
    `app.infrastructure.aggregation_scheduler_adapters` owns SQLAlchemy, Prometheus, and system-clock
    adapters. `app.application.aggregation_jobs` owns expiry recovery, leased claims, and bounded
    processing. The database queue is the command boundary; do not restore the same-owner
    `portfolio_day.aggregation.job.requested` Kafka hop. `make architecture-guard` runs
    `scripts/quality/aggregation_scheduler_boundary_guard.py` so DB session factories, concrete
    repositories, Kafka producers/consumers, direct publish/flush calls, and raw metric functions do
    not drift into scheduler or worker orchestration.
79. Position calculation rules are split from database sessions, concrete repositories, outbox
    staging, metrics, epoch fencing, and position-history persistence orchestration. The repo-local
    standard lives at `docs/standards/position-reducer-boundary-standard.md`.
    `portfolio_transaction_processing_service.app.domain.position.reducer` owns
    `PositionBalanceState`, `BackdatedRecalculationDecision`, buy/sell transitions, cash movement
    deltas, transfer and
    corporate-action quantity policy, FX contract/cash settlement behavior, flat-position cost
    zeroing, and deterministic backdated replay planning without SQLAlchemy, repositories, outbox,
    metrics, `EpochFencer`, persistence models, Pydantic DTOs, or correlation context.
    `PositionHistoryProcessor` owns framework-neutral coordination through ports. SQLAlchemy
    mapping, state access, persistence, metrics, and structured logs are organized under the
    domain-owned `app/infrastructure/position` adapter package.
    `make architecture-guard` runs `scripts/quality/position_reducer_boundary_guard.py` so domain
    policy stays pure and the retired infrastructure workflow/repository cannot return.
80. Protected business logic modules must stay directly testable without FastAPI, real databases,
    Kafka, Redis, cloud SDKs, or downstream clients. The repo-local standard lives at
    `docs/standards/testability-architecture-standard.md`, and the machine-readable contract lives
    at `docs/standards/testability-architecture-contract.json`. `make architecture-guard` runs
    `scripts/quality/testability_architecture_guard.py`, which currently protects domain, application,
    ports, policy, and extracted pure reducer modules from runtime imports, runtime factory calls,
    repository/dependency/router/consumer imports, and concrete client symbols. Runtime composition
    belongs in approved composition roots such as `app/dependencies.py`, routers, consumers,
    infrastructure/adapters/repositories, and shared infrastructure modules. When a legacy service
    path is extracted into a use case, policy, port, or pure reducer, add that path to the
    protected contract and prove it with fake-port tests.
81. Runtime deployable boundaries require design-before-runtime-split evidence. The repo-local
    standard lives at `docs/standards/runtime-boundary-decision-standard.md`; the current deployable
    catalog lives at `docs/architecture/runtime-boundary-decision-catalog.json`; and the template
    lives at `docs/architecture/templates/runtime-boundary-decision-record-template.md`.
    `make architecture-guard` runs `scripts/quality/runtime_boundary_decision_guard.py`, which discovers
    `src/services/**/Dockerfile`, requires every deployable root to have a catalog entry, blocks
    stale catalog entries, prevents new service paths from using current-state status, and requires
    PR checklist coverage. Existing deployables are cataloged as
    `current-state-revalidation-required`; that is current-state documentation, not retrospective
    approval. In-process-only refactors must record a no-runtime-split rationale in their CR, RFC,
    or ledger entry.
82. Deployable service internals should follow the in-process modularity package standard before
    any runtime split is considered. The repo-local standard lives at
    `docs/standards/in-process-modularity-package-standard.md`; representative adoption is tracked
    in `docs/architecture/in-process-modularity-adoption-catalog.json`; and `make
    architecture-guard` runs `scripts/quality/in_process_modularity_guard.py`. The standard recommends
    `domain`, `application`, `ports`, `adapters`, delivery/routers, repositories/persistence,
    runtime composition files, and optional `proof_builders`, while keeping API DTOs at delivery,
    application commands/results in application, domain objects in domain, and persistence models
    in adapters/repositories. `ingestion_service` is the representative adopted service with
    explicit legacy-folder migration scope for `DTOs`, `services`, `transformers`, and `producers`.
    Do not perform broad folder renames; migrate cohesive workflows into the standard packages as
    issue slices touch them.
83. In-process package dependency direction is now guarded across service-local `domain`,
    `application`, `use_cases`, `ports`, `adapters`, and `proof_builders` packages. The repo-local
    standard lives at `docs/standards/in-process-boundary-contract-standard.md`; transitional
    exceptions live at `docs/standards/in-process-boundary-exceptions.json`; and `make
    architecture-guard` runs `scripts/quality/in_process_boundary_guard.py`. Domain packages must stay
    framework-free, infrastructure-free, and persistence-free; application packages may depend on
    domain and ports but not routers, concrete adapters, infrastructure, repositories, API DTOs, or
    legacy service packages; ports must stay framework-neutral and persistence-neutral; adapters may
    depend on concrete infrastructure while implementing ports; and proof builders must assemble
    evidence from application/domain outputs rather than routers or persistence models. Exceptions
    require owner, expiry, follow-up issue, and reason, and stale exceptions fail the guard.
84. The microservice boundary matrix now distinguishes in-process design boundaries from runtime
    deployable boundaries. `docs/architecture/microservice-boundaries-and-trigger-matrix.md` is the
    current service responsibility, in-process ownership, runtime rationale, and no-split-yet
    navigation page. Use it with `docs/standards/runtime-boundary-decision-standard.md`,
    `docs/architecture/runtime-boundary-decision-catalog.json`,
    `docs/standards/in-process-modularity-package-standard.md`, and
    `docs/standards/in-process-boundary-contract-standard.md`. Existing deployables remain
    historical/current-state revalidation unless a future decision record approves, consolidates,
    or changes the boundary. Important modules default to no runtime split until scale, deployment
    cadence, operations ownership, persistence ownership, failure isolation, security, or SLO
    evidence changes that decision.
85. Evidence-producing capabilities should use typed in-process proof builders before anyone
    considers a proof service. The repo-local standard lives at
    `docs/standards/proof-builder-pattern-standard.md`; shared typed proof contracts live in
    `portfolio_common.proof_builders`; and `make architecture-guard` runs
    `scripts/quality/proof_builder_pattern_guard.py`. The first contract families cover source-data
    supportability, ingestion/replay evidence, reconciliation evidence, and app validation
    evidence. Proof builders accept application/domain/support inputs and return typed artifacts;
    routers map artifacts to API DTOs, repositories own persistence reads, and runbooks document
    operator behavior. A separate proof service requires the runtime-boundary decision process.
86. API adapters should keep DTO-to-command, application-result-to-response, and typed
    error-to-HTTP translation in bounded mapper modules when the mapping is reused, non-trivial, or
    representative for a route family. The repo-local standard lives at
    `docs/standards/api-mapper-pattern-standard.md`; current representative modules cover lookup,
    reconciliation, event-replay command errors, and query-service read error mapping; and `make
    architecture-guard` runs `scripts/quality/api_mapper_pattern_guard.py`. Keep this context entry as
    navigation only: detailed mapping rules belong in the standard and executable guard, not
    duplicated prose.
87. Runtime current-time, elapsed-duration, and generated-ID access should flow through
    `portfolio_common.runtime_providers` in provider-migrated application workflows. The repo-local
    standard lives at `docs/standards/runtime-provider-port-standard.md`; current representative
    coverage includes financial reconciliation elapsed-duration/finding IDs, core snapshot
    generated metadata, and simulation session/change IDs plus TTL/expiry decisions; and `make
    architecture-guard` runs `scripts/quality/runtime_provider_port_guard.py`. Legacy analytics and
    operations services still have direct wall-clock usage and remain explicit migration scope.
88. Query-control-plane analytics-input responses use response-level `lineage` for reproducibility
    and source-data runtime metadata uses `source_lineage` for source proof. Do not let runtime
    metadata helpers return or unpack a raw `lineage` key into
    `PortfolioAnalyticsTimeseriesResponse`, `PositionAnalyticsTimeseriesResponse`, or
    `PortfolioAnalyticsReferenceResponse`; that collision causes unhandled constructor failures in
    downstream performance, risk, and idea proof generation. `AnalyticsTimeseriesService` routes
    those responses through a guarded metadata helper and has canonical
    `PB_SG_GLOBAL_BAL_001` regression tests for the issue #705 proof path.
    `MarketDataWindow:v1` is QCP-owned through contract, request/paging policy, typed evidence
    assembly, proof policy, ports, SQL adapters, route-scoped signed tokens, composition, and route.
    Keep raw operational reads in Query Service, and do not restore its obsolete market-series
    facade or delegate source hash/freshness authority to consumers.
    `DataQualityCoverageReport:v1` and the classification-taxonomy
    `InstrumentReferenceBundle:v1` are also QCP-owned through public contracts, application
    policy, immutable evidence, typed source ports, deterministic SQL adapters, source proof,
    composition, and routes. Do not restore Query Service coverage/taxonomy DTOs, helpers,
    repository methods, tests, or facade paths. Operations support and advisory simulation are now
    QCP-owned through contracts, application policies/use cases, immutable evidence, ports,
    infrastructure adapters, dependency composition, routes, and colocated tests. QCP production
    code has no Query Service implementation imports, its wheel and clean image import `app.main`,
    and Compose no longer mounts Query Service source into the QCP container. Preserve that package
    closure through `tests/unit/test_service_wheel_package_contract.py` and issue #715 evidence.
89. Resilience-critical runtime settings should use `portfolio_common.runtime_settings` so invalid
    values fail fast in strict or non-local profiles while local fallback remains explicit and
    logged. Current migrated families include ingestion, query service, query-control-plane,
    common outbox, valuation runtime, portfolio aggregation runtime controls, and shared
    `portfolio_common.config` integer, boolean, and Kafka consumer override JSON settings. Do not
    add local silent parsers for resilience, cache, retry, scheduler, consumer, or guardrail
    settings; either use the shared helper or document and test an explicit local-compatibility
    fallback.
90. Enterprise capability rules are exact by default. Use route templates such as
    `GET /portfolios/{portfolio_id}` only for that exact segment shape, and use explicit
    `/**` suffixes such as `GET /portfolios/{portfolio_id}/**` only when the rule intentionally
    authorizes a subtree. Do not rely on prefix matching for authorization examples, tests, source
    data rules, or service-local capability overrides.
91. Service-local enterprise-readiness wrappers must own default capability rules for their
    canonical business routes instead of relying on `ENTERPRISE_CAPABILITY_RULES_JSON` alone for
    production policy. Ingestion write APIs cover every canonical `/ingest/*` and `/reprocess/*`
    write route through `ingestion_write_capability_rules()`. Financial reconciliation control
    APIs cover every canonical `/reconciliation/*` write/read route through
    `financial_reconciliation_capability_rules()`, with `financial_reconciliation.controls.run`
    for control-run creation and `financial_reconciliation.controls.read` for evidence reads.
    Future business routes in these services must update the service-local capability-rule helper
    and keep the route-coverage test green. Shared enterprise middleware keeps health, metrics,
    OpenAPI, docs, ReDoc, and version endpoints on an explicit unauthenticated operational
    allowlist even when read authorization is enabled.
92. Query-service cursor/page tokens use the shared `PageTokenCodec` versioned envelope with
    `kid`, expiry, issuer/audience, optional route/tenant binding, and active/previous key support.
    Non-local or strict profiles must set non-default `LOTUS_CORE_PAGE_TOKEN_SECRET` and
    `LOTUS_CORE_PAGE_TOKEN_KEY_ID`; local defaults are developer-only compatibility. Do not add a
    parallel page-token HMAC helper or unversioned payload/signature envelope. Analytics page tokens
    must continue to route through the shared codec.
93. Privileged ingestion ops JWTs must carry required `exp`, `iat`, `iss`, `aud`, `jti`, a
    principal identity claim, required ops scope/capability, and `kid`. `ops_controls.py` supports
    active plus previous HS256 keys for symmetric rotation; do not add a second JWT verifier or make
    issuer, audience, expiry, issued-at, key id, or scope optional. Non-local or strict profiles
    must configure JWT issuer, audience, active key id, secret, and required scope. Static
    `X-Lotus-Ops-Token` fallback in non-local profiles requires explicit
    `LOTUS_CORE_INGEST_OPS_STATIC_TOKEN_NON_LOCAL_APPROVED=true` and a non-default token.
94. Enterprise read/write authorization must derive capabilities from a signed internal auth
    context, not arbitrary `X-Capabilities` headers. The shared enterprise middleware verifies
    `X-Enterprise-Auth-Key-Id`, `X-Enterprise-Auth-Timestamp`, and
    `X-Enterprise-Auth-Signature` over actor, tenant, role, correlation id, service identity, and
    normalized capabilities using `ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET`. Do not treat
    `Authorization` or `X-Service-Identity` presence as proof of service identity; unsigned gateway
    capability headers are only data until the auth-context signature verifies.
95. Bulk upload preview is source-safe by default. `/ingest/uploads/preview` keeps the
    `sample_rows` field for compatibility but returns an empty list unless the caller submits
    `include_sample_rows=true` and presents the signed
    `ingestion.uploads.preview_samples.read` capability. Privileged sample rows must still be
    redacted for sensitive identifiers, monetary, fee, tax, price, quantity, notional, balance, and
    market-value fields. Do not reintroduce default normalized row disclosure in preview responses.
96. Bulk upload preview and commit must enforce resource budgets before and during parser work.
    Use `LOTUS_CORE_INGEST_UPLOAD_MAX_BYTES`, `LOTUS_CORE_INGEST_UPLOAD_MAX_ROWS`,
    `LOTUS_CORE_INGEST_UPLOAD_MAX_COLUMNS`, and
    `LOTUS_CORE_INGEST_UPLOAD_MAX_CELL_LENGTH`; reject parser-budget breaches with
    `INGESTION_UPLOAD_PARSER_BUDGET_EXCEEDED`. Preview must have rate/abuse protection because it
    performs parsing work even though it does not publish records. Do not reintroduce full-file XLSX
    worksheet materialization or unbounded CSV row collection.
97. Downstream dependency probes and admin clients must use
    `portfolio_common.downstream_access.DownstreamAccessPolicy` instead of hard-coded timeout,
    retry, batch, pagination, cache, or circuit-breaker assumptions. The policy is configured with
    `LOTUS_CORE_DOWNSTREAM_*` environment variables and is strict-validation aware. Health
    readiness and Kafka admin helpers are the first consumers; future HTTP/source-data/storage
    adapters should inherit this policy rather than introducing local client defaults.
98. Kafka producer runtime posture is centralized in
    `portfolio_common.kafka_producer_policy.KafkaProducerPolicy` and applied by
    `portfolio_common.kafka_utils.KafkaProducer`. Do not add service-local producer config
    dictionaries for client identity, retry count, batching, compression, delivery timeout,
    request timeout, or queue bounds. Use the shared `LOTUS_CORE_KAFKA_PRODUCER_*` variables and
    service override JSON; keep idempotence, `acks=all`, and safe in-flight request limits as
    adapter-owned invariants rather than caller-overridable settings.
99. Kafka publish back-pressure has a first-class shared contract. `KafkaProducer.publish_message`
    emits `kafka_producer_events_total` with bounded `service`, `topic`, `outcome`, and `reason`
    labels and logs local queue saturation as `kafka.producer.back_pressure` with reason
    `queue_full`; `KafkaEventPublisher` maps `BufferError` to retryable
    `KafkaPublishBackPressure` and flush timeout/exception paths to uncertain delivery. Schedulers
    and outbox/replay publishers must preserve this distinction so queue saturation defers or
    recovers work instead of marking it dispatched or collapsing it into a generic terminal error.
100. Retry behavior for Kafka admin/startup checks and DB-backed consumers belongs in
     `portfolio_common.retry_policy`, not service-local `wait_fixed(...)` and
     `stop_after_attempt(...)` decorators. Use the shared profiles with bounded exponential jitter,
     max attempts, max elapsed budgets, explicit retryable exception classes, and
     `retry_policy_events_total` telemetry. Unexpected exceptions should remain non-retryable unless
     a domain policy explicitly classifies them as transient.
101. Durable queue schedulers must have explicit work budgets in addition to batch-size and
     dispatch-round limits. Valuation scheduler uses `VALUATION_SCHEDULER_POLL_BUDGET_SECONDS` and
     `VALUATION_SCHEDULER_DISPATCH_BUDGET_SECONDS`, emits poll-duration, claimed, dispatched,
     budget-exhausted, and producer-back-pressure metrics, and recovers claimed-but-undispatched
     jobs through the existing durable dispatch recovery path. Do not increase scheduler batch
     sizes or dispatch rounds without preserving time-budget stop behavior and source-safe
     carry-forward semantics.
102. Valuation backfill staging must aggregate generated jobs across states and write them through
     bounded chunks controlled by `VALUATION_SCHEDULER_BACKFILL_UPSERT_CHUNK_SIZE`. Keep duplicate
     idempotency and stale-epoch filtering in `ValuationJobRepository.upsert_jobs(...)`; do not
     reintroduce scheduler loops that call `upsert_jobs(...)` once per state or bypass the
     repository's correlation-lineage normalization.
103. Operator summary repositories should compose same-scope scalar aggregates into a bounded row
     query rather than awaiting many independent `db.scalar(...)` calls. `get_load_run_progress`
     now returns its 14 scalar facts through one composed scalar-row statement plus four explicit
     aggregate row queries; preserve that query-count test before adding new load-run progress
     facts.
104. Kafka consumer worker execution policy belongs in
     `portfolio_common.kafka_consumer_execution` and `BaseConsumer`, not in service-local poll
     loops. Defaults preserve serial processing with `poll_timeout_seconds=1.0` and
     `max_in_flight_messages=1`; operators may override profiles through
     `LOTUS_CORE_KAFKA_CONSUMER_EXECUTION_DEFAULTS_JSON` and
     `LOTUS_CORE_KAFKA_CONSUMER_EXECUTION_GROUP_OVERRIDES_JSON`. Concurrent profiles must preserve
     one active message per partition, pause polling for ordered pending work, commit offsets only
     after processing or DLQ publication succeeds, and expose in-flight, idle-poll, processing, and
     backlog-pressure metrics. Do not add worker-local concurrency or poll-timeout settings without
     extending the shared profile and tests.
105. Cashflow rule caching is governed reference-data caching, not hidden calculation state. Cached
     cashflow rules must carry the source rule-set version fingerprint and latest effective
     timestamp, verify the current source version before serving a fresh cache hit, reload on TTL
     expiry, source-version change, missing-rule refresh, or explicit process-local invalidation,
     and emit bounded `cashflow_rule_cache_events_total` outcomes. Multi-process invalidation is
     source-owned through `cashflow_rules.updated_at`; do not add rule caches that lack source
     version/effective metadata, stale-read behavior, invalidation ownership, and cache metrics.
     A five-second source-version validation interval reduced exact fan-in version queries from
     `999` to `19` but repeatedly regressed drain from `100.608s` to `110.821s` and `110.768s`; it
     was reverted forward. Do not reintroduce an interval based on query-count evidence alone.
     The active cache is an instance-owned `CashflowRuleCache` under
     `app/infrastructure/cashflow/`; its immutable snapshot and lock belong to the composed runtime.
     SQL rule access belongs to the adjacent singular `rule_repository.py`, with tests mirrored
     under `tests/.../infrastructure/cashflow/`. Do not restore module-global cache state, flat
     cashflow rule repositories, plural compatibility names, or tests that reset private state.
     Durable cashflow writes belong to adjacent `cashflow/persistence.py`; keep its SQLAlchemy
     session private, map ORM rows to `StoredCashflow` at the adapter boundary, and mirror adapter
     tests under the same infrastructure package. Do not restore flat cashflow persistence modules
     or place infrastructure tests beside domain calculation tests.
     Cashflow orchestration belongs in `application/cashflow_processing/` and may depend only on
     `BookedTransaction`, cashflow domain values, application errors/results, and protocols under
     `ports/cashflow/`. Keep SQLAlchemy sessions, ORM rows, Kafka/Pydantic events, outbox helpers,
     cache implementations, and transport mappers in infrastructure. Combined unit-of-work
     composition constructs `ProcessTransactionCashflowUseCase` with session-scoped adapters and a
     runtime-owned `CashflowRuleCache`; preserve one transaction for cashflow persistence and outbox
     staging. The #719 migration remains incomplete only until the unused compatibility workflow
     and adapter are deleted; do not add behavior to those retired-path candidates.
     Every ORM, repository, raw SQL, migration, and migration-downgrade rule mutation must advance
     `cashflow_rules.updated_at` explicitly; ORM `onupdate` does not apply to raw SQL.
106. Source-data read-model fallbacks must be source-owned and field-explicit. HoldingsAsOf now
     exposes reusable `SourceDataDegradationSummary` / `SourceDataDegradationDetail` metadata for
     fallback, stale, partial, unavailable, and empty evidence, plus deterministic content hash,
     source digest, source refs, and bounded source lineage. Do not add new fallback or
     supplemental read-model behavior that only changes aggregate `data_quality_status`, hides
     fallback-derived fields, emits the empty source metadata hash, or forces downstream consumers
     such as `lotus-idea` to infer Core freshness/provenance.
107. Degraded-state contract coverage belongs in representative source-data tests, not scattered
     incidental assertions. When adding or changing source-data fallbacks, stale observations,
     partial pages, missing reference profiles, unavailable source evidence, dependency timeout
     handling, or blocking control states, update
     `tests/unit/services/query_service/services/test_degraded_source_data_contracts.py` or an
     equivalent focused suite. Assert data-quality status, freshness/current evidence semantics,
     supportability, source hash/lineage or fallback detail where applicable, namespaced reason
     codes, and correlation ID. Also update the guarded API example catalog when the response
     pattern is public or downstream-facing.
108. Caller-controlled sorting must be typed, documented, and fail-fast. The strategic transaction
     ledger uses `query_service.app.application.transaction_sorting` for allowed sort fields,
     directions, defaults, and repository validation. Do not add route-local or repository-local
     silent fallback for unsupported `sort_by` / `sort_order`; publish allowed values in OpenAPI,
     reject invalid supplied values with structured 400 errors, and keep deterministic tie-breakers
     for every paginated ordering.
109. Raw series and collection reads must have an explicit bound. MarketPriceSeries, FxRateSeries,
     and PositionHistorySeries use `query_service.app.application.collection_window_policy` and
     require complete date windows capped at ten years before repository access. Future collection
     endpoints must use cursor/page-token pagination, offset pagination with a max limit, mandatory
     bounded windows, or a documented small-cardinality contract with tests. Do not add optional
     date filters that allow full-history scans by omission.
110. API/query filter, sort, and as-of policy must be application-owned before repository access.
     The transaction ledger uses `query_service.app.application.transaction_query` to build
     `TransactionLedgerFilters`, `TransactionSortSpec`, and `TransactionLedgerQuerySpec`; repository
     methods translate those typed specs to SQL and must not accept raw route/query parameters for
     ledger reads. Default business-calendar selection belongs in service date policy, passed
     explicitly to repository queries. Extend this spec pattern for future ledger-style reads rather
     than adding repository-local API vocabulary, silent fallbacks, or as-of default rules.
111. Governed event payloads must fail fast on unknown fields instead of silently dropping contract
     drift. `portfolio_common.events.CoreEventModel` uses `extra="forbid"`, and the shared event
     tests cover every current `CoreEventModel` subclass for unknown-field rejection with
     source-safe validation errors. Do not change governed event models to `extra="ignore"` or add
     local permissive parsers unless an explicit versioned compatibility contract preserves unknown
     fields as typed extension metadata and includes producer/consumer, DLQ, redaction, and replay
     tests.
112. Event-envelope metadata posture belongs in `portfolio_common.event_supportability`, not in
     scattered optional DTO fields or local consumer assumptions. Every event-family definition must
     require idempotency, correlation, schema versioning, and a source-data product or supportability
     evidence link; every direct Kafka topic must support idempotency and correlation headers; and
     supportability surfaces must remain operator-only and evidence-backed. Update the catalog and
     its tests before adding, renaming, or relaxing event families, topics, replay/supportability
     paths, or envelope metadata behavior.
     Event contract test-pack governance now lives in
     `docs/standards/event-contract-test-pack.v1.json` and is enforced by
     `make event-contract-test-pack-guard`, which is wired into `make lint`. Current governed
     event-family consumers use `portfolio_common.event_mapping.validate_kafka_event_payload(...)`
     with an expected event type so missing `event_type`, missing `schema_version`, unsupported
     schema versions, and event-type drift are rejected before application handlers run. Do not add
     a consumer-local permissive parser or local schema-version check; extend the shared validator,
     event catalog, contract pack, and focused tests instead.
113. Durable operational records that can persist without request correlation must record explicit
     missing-correlation diagnostics. Use `portfolio_common.durable_correlation` for nullable
     durable records so absent correlation IDs produce `correlation_missing_reason` and a
     deterministic `alternate_lookup_key` from stable business identifiers. Do not add new
     operator-searchable records with nullable `correlation_id` unless they either require
     correlation at the schema boundary or persist the same diagnostic fields with migration,
     backfill, index, and tests.
114. Cashflow event dates must be resolved through an explicit calculation policy, not by
     hard-coding `transaction_date` in cashflow assembly, query consumers, or downstream proof
     scripts. `CashflowLogic` now uses `synthetic_flow_effective_date` when supplied, uses
     `settlement_date` for settlement/value/payment-dated cash movements, and falls back to
     `transaction_date` only when the event lacks the relevant source timing field. Current Core
     events do not expose first-class `payment_date` or `value_date`; do not document or consume
     unsupported fields until the transaction-event schema is intentionally extended and tested.
115. FastAPI app bootstrap must not own endpoint-specific business-contract error mapping. QCP now
     registers exception handlers through `query_control_plane_service.app.exception_mappers`,
     where advisory simulation validation/execution mapping lives behind a typed endpoint mapper
     registry. Future endpoint-specific problem-details behavior should be added through a mapper,
     router-local exception type, or application error taxonomy, with tests proving the targeted
     endpoint contract and a non-target endpoint fallback. Do not reintroduce path-specific
     branches or route-contract imports in `main.py`.
116. Web-backed Kafka worker readiness must include `db`, `kafka`, and `worker_runtime` unless the
     worker has a documented exception. Use `portfolio_common.worker_readiness` and pass
     `readiness_service_name=WORKER_READINESS_SERVICE_NAME` into
     `wait_for_shutdown_or_task_failure(...)` so critical consumer, dispatcher, scheduler, and
     embedded runtime task exits surface as bounded readiness dependency states instead of leaving
     `/health/ready` green from database reachability alone. Keep liveness lightweight and do not
     expose raw exception strings or unbounded task details in readiness responses. Shared worker
     tasks use bounded source-safe identities: Kafka loops include consumer group and topic, while
     the dispatcher and health server use stable component names. Do not revert to generic
     `Task-N` identities that hide the failed runtime component during support triage.
117. Ingestion DTO domain validation must use
     `ingestion_service.app.DTOs.ingestion_validation_errors` for stable machine-readable codes,
     field paths, remediation hints, duplicate-source-key detection, effective-window checks,
     lineage checks, quality-status checks, and identifier/lifecycle-link validation. Do not add new
     local `ValueError` strings for reusable ingestion domain rules. Bulk upload row errors preserve
     the legacy `message` field but should carry `code`, `severity`, `field_path`, `record_key`,
     `remediation`, and source-safe `source_lineage` where available; update focused DTO,
     upload-validation, and OpenAPI contract tests when changing this behavior.
118. Capability and integration policy endpoints must keep source/config loading separate from
     policy resolution and response assembly. The integration capabilities API uses
     `query_control_plane_service.app.application.capability_policy` for its catalog,
     environment-backed policy
     source, tenant override parsing, policy resolver, and response assembler; keep env/settings
     reads in the policy source adapter, exercise policy logic with explicit in-memory inputs, and
     resolve persisted business dates through `BusinessDateProvider` with SQLAlchemy construction
     in QCP infrastructure and injection at delivery composition; application modules must not
     import `SessionLocal`, SQLAlchemy, or ORM models,
     preserve public capability DTO compatibility unless a contract change is intentional,
     documented, and tested. Effective snapshot policy is QCP-owned under
     `query_control_plane_service.app.application.integration_policy` with its public contract in
     `app.contracts.integration_policy`. QCP settings and clock construction belong in
     `app.dependencies`; the policy application receives immutable configuration and `Clock`, and
     must not read environment variables, construct wall-clock timestamps, or return through the
     broad Query Service integration facade. Query Service must not recreate policy/version or
     capability-override settings after those ownership moves.
119. Broad query/control-plane services should expose repository and port dependencies through
     explicit dependency bundles or use-case ports, not only by constructing repositories from raw
     `AsyncSession` inside service constructors. `CoreSnapshotDependencies`,
     `IntegrationServiceDependencies`, and `OperationsServiceDependencies` provide the current
     representative pattern: keep `from_session(...)` construction at the FastAPI/deployment wiring
     boundary, support fake dependencies in focused tests, and require repository additions to
     change a visible dependency factory or bundle. New Query Control Plane capabilities must use
     domain-named contract, application, domain, port, and infrastructure modules where those
     layers have real responsibilities. `PortfolioManagerBookService` is the representative
     source-read pattern: the router binds the API contract, the application service owns the use
     case and metadata, the port returns immutable domain records, and the SQL adapter alone maps
     persistence rows. Do not add new methods to `IntegrationService` or reproduce broad
     contract-family facades. `DpmReadinessIntegrationService` and
     `BenchmarkReferenceIntegrationService` are migration debt to be retired by complete vertical
     capability moves, not target-state examples.
     `PortfolioManagerBookService` and `DpmPortfolioPopulationService` demonstrate why source
     authority and domain language must determine module boundaries instead of legacy facade
     adjacency.
120. Kafka consumers must keep transport responsibilities separate from application orchestration.
     The active combined path uses `ProcessTransactionUseCase` and target ports. Cost-basis
     SQL/outbox staging belongs to the domain-owned `CostBasisProcessingAdapter`; the quarantined
     legacy consumer alone retains its physical idempotency claim, concrete repository construction, and
     retry/DLQ lifecycle for rollback characterization. Do not recreate
     `cost_calculation_processor.py` or copy this compatibility delivery shape into new consumers.
     New consumers with idempotency, repository, publication, or reconciliation behavior require a
     framework-neutral application use case plus ports and infrastructure composition.
121. Valuation job processing follows the same consumer/application split at greater depth:
     `ValuationConsumer` owns Kafka decode, correlation context, retry classification, and DLQ
     handoff only, while `ValuationJobProcessor` owns valuation state vocabulary, snapshot
     construction, missing-price and stale/current classification, missing-FX failure handling,
     no-position skip, job completion, unexpected-error failure marking, idempotency, and outbox
     staging. Production session and concrete repository/idempotency/outbox construction belong to
     `app/infrastructure`; tests and alternate entry points inject the provider and factory instead
     of patching processor globals. Future backfill, replay, or batch valuation entry points should
     reuse this explicit composition instead of copying consumer workflow logic.
122. Valuation orchestration scheduler refactoring is in progress under GitHub issue #545.
     `ValuationJobDispatcher` now owns valuation job dispatch payload mapping, correlation
     headers, dispatch-budget enforcement, publisher delivery confirmation, and dispatch recovery
     metadata. `ValuationBackfillPlanner` now owns backfill input flow, no-history normalization,
     reprocessing no-history deferral, backfill metrics, deterministic scheduler backfill
     correlation IDs, job request construction, bounded chunks, and job upsert staging.
     `ValuationWatermarkAdvancer` now owns latest-date input loading, lagging and terminal
     reprocessing reads, first-open-date support lookups, active reprocessing gauges, terminal
     normalization, contiguous snapshot lookup, epoch-fenced watermark update construction, and
     stale-skip warnings/metrics. `InstrumentReprocessingCoordinator` now owns pending trigger
     metrics, bounded instrument trigger claiming, durable `RESET_WATERMARKS` replay-job creation,
     trigger correlation propagation, and trigger consume logging. Keep publisher/Kafka flush
     logic, backfill planning, watermark policy, and instrument trigger coordination out of
     `ValuationScheduler`. `ValuationStaleJobResetter` owns stale valuation job reset invocation
     with scheduler-configured timeout and maximum-attempt policy. `ValuationDispatchCoordinator`
     owns claimed-job polling rounds, poll-budget enforcement, eligible-job claiming, dispatch
     callback orchestration, dispatch failure observation, and recovery repository calls through an
     explicit session provider and repository factory. Durable valuation claims must also respect
     `VALUATION_SCHEDULER_MAX_IN_FLIGHT_JOBS`; the repository serializes capacity checks and claims
     with a PostgreSQL transaction-scoped advisory lock so concurrent schedulers cannot turn broker
     backlog into unbounded `PROCESSING` rows that later fail the stale-worker policy. Keep this
     control separate from per-poll batch, round, and time budgets.
     `ValuationSchedulerRepositoryFactory` owns
     repository construction for scheduler DB steps, and the scheduler accepts an explicit session
     provider so the loop can be tested without real repositories or Kafka. Keep the scheduler as a
     small cadence/compatibility wrapper; do not reintroduce backfill, watermark, reprocessing,
     stale-reset, dispatch, publisher, or repository construction policy into the loop.
123. Core snapshot HTTP dependency factories belong in the query-control-plane dependency module,
     not in `CoreSnapshotService`. Keep `CoreSnapshotService` free of FastAPI dependency imports;
     bounded snapshot composition collaborators should remain delivery-framework agnostic. The
     complete snapshot application is owned by
     `query_control_plane_service/app/application/core_snapshot`; do not recreate snapshot DTOs,
     use cases, policies, or repository orchestration under `query_service`.
     Core snapshot governance mapping belongs in `core_snapshot/governance.py`; do not re-add
     request policy provenance, applied/dropped section, or inline-default governance mapping to the
     broad service.
     Core snapshot request identity and fingerprint construction belongs in
     `core_snapshot/identity.py`; do not re-add canonical request payload or governance-sensitive
     fingerprint payload assembly to the broad service.
     Core snapshot freshness-to-data-quality classification belongs in
     `core_snapshot/quality.py`; do not re-add `COMPLETE`/`PARTIAL`/`UNKNOWN` policy mapping to the
     broad service.
     Core snapshot response section assembly belongs in `core_snapshot/sections.py`; do not re-add
     requested-section branching, projected/delta/totals population, or snapshot enrichment field
     mapping to the broad service.
     Core snapshot projected valuation belongs in `core_snapshot/projected_valuation.py`; do not
     re-add simulation change normalization, new-security instrument seeding, price lookup,
     market-to-portfolio FX selection, or projected market-value calculation to the broad service.
     Shared FX lookup and decimal validation belong in `core_snapshot/market_data.py` rather than
     service-private helpers.
     Core snapshot simulation option/session validation belongs in
     `core_snapshot/simulation_validation.py`; do not re-add simulation option checks, session
     lookup, portfolio ownership validation, expected-version validation, or baseline-mode
     projected/delta section rejection to the broad service. Core snapshot exception classes belong
     in `core_snapshot/errors.py`; `core_snapshot/service.py` may re-export them only for
     compatibility with existing routers/tests.
     Repository-backed Core snapshot instrument enrichment belongs in
     `core_snapshot/instrument_enrichment_reader.py`; do not re-add security-id normalization,
     empty-request rejection, source lookup, or enrichment contract assembly delegation to the
     broad service. Pure enrichment record mapping remains in
     `core_snapshot/instrument_enrichment.py`. Application code consumes immutable records through
     `CoreSnapshotSourceReader` and `SimulationStore`; SQLAlchemy models, sessions, and concrete
     repositories remain in QCP infrastructure and dependency composition.
124. Reference integration DTO metadata must remain domain-neutral and source-authority oriented.
     Do not justify defaults or examples by naming a downstream Lotus application unless the field
     is explicitly a consumer-policy contract. Use neutral source-system examples, mandate-policy
     evidence language, request-context wording, and source-authority boundaries. The regression
     test in `tests/unit/services/query_service/dtos/test_reference_integration_dto.py` guards
     `reference_integration_dto.py` against reintroducing downstream app names or downstream-owned
     campaign/ranking/execution/client-communication workflow phrases.
125. Active/current source-data lifecycle predicates belong in
     `portfolio_common.source_lifecycle_predicates`, not as scattered persistence-model SQL strings
     or repository literals. Use the named predicate contract for DPM discretionary mandate
     authority, client restriction/preference/tax/income/reserve/withdrawal products,
     model-portfolio targets, benchmark definitions, and index definitions before adding or
     changing partial indexes or repository filters. Keep effective-window predicates explicit in
     repositories and index definitions, but share the governed status vocabulary and predicate
     intent through the contract module. Add or update
     `tests/unit/libs/portfolio-common/test_source_lifecycle_predicates.py`,
     `tests/unit/libs/portfolio-common/test_database_models.py`, and the relevant query repository
     tests when introducing a new active/current source-data family.
126. Backend dependency flow should move in one direction: external consumer -> API/controller/route
     -> request DTO mapper or command construction -> application use case -> domain model and
     domain service -> port/interface -> infrastructure adapter -> database, cache, queue, or
     external API. Ingestion routers must stay at the API/controller layer. Publish-backed
     transaction, portfolio, instrument, market-price, FX-rate, portfolio-bundle, and reprocessing
     routes use
     `IngestionPublishCommandHandler`; reference-data routes use
     `ReferenceDataIngestionCommandHandler`; business-date ingestion uses
     `BusinessDateIngestionCommandHandler`. Do not reintroduce job creation, request-lineage
     resolution, rate-limit enforcement, concrete publish/persist calls, job failure marking, or
     queue-bookkeeping into these routers. Extend the command-handler/use-case pattern and update
     `tests/unit/services/ingestion_service/routers/test_ingestion_router_command_boundaries.py`
     when adding or changing ingestion route families.
127. Cost, cashflow, and position processing are planned to converge into one
     `portfolio_transaction_processing_service` deployable under issue #468. Preserve three
     internal domain/application modules coordinated by one `ProcessTransactionUseCase`, one
     atomic normal-path unit of work, current compatibility Kafka topics during migration,
     explicit replay/DLQ semantics, module diagnostics/metrics, and state ownership. Do not merge
     calculation policies into one large service class or let the use case depend on concrete
     repositories/consumers. `position_valuation_calculator` remains
     independently deployable because its job-driven compute, market-data dependency, scaling,
     backfill, and failure-isolation profile differs from transaction processing. The authoritative
     migration and rollback gates are in
     `docs/architecture/calculator-runtime-consolidation-decision.md`; the current three-worker
     topology remains runtime truth until its parity gates pass. The target event anti-corruption
     boundary is
     `portfolio_transaction_processing_service.app.delivery.kafka.transaction_event_mapper`:
     it maps every governed `TransactionEvent` business field into immutable, framework-neutral
     `BookedTransaction` plus `ProcessTransactionCommand` metadata and fails on field drift. Keep
     `portfolio_common.events` out of the target domain/application packages. The canonical worker
     package direction is `app/delivery` -> `app/application` -> `app/domain` and `app/ports` ->
     `app/infrastructure` -> `app/runtime`. The old cost, cashflow, and position roots are explicit
     migration sources in `in-process-modularity-adoption-catalog.json`, not templates for new
     agent-generated code. `ProcessTransactionUseCase` owns normal-path ordering and atomicity;
     concrete repositories, Kafka, SQLAlchemy sessions, and compatibility event models remain
     behind ports/adapters. The concrete normal-path transaction owner is
     `app/infrastructure/transaction_processing/unit_of_work.py`: all module repositories and
     compatibility outbox writes use one session and one commit; new module-local commits or
     sessions are a boundary regression. The final live normal path has one target consumer of booked
     transactions using the application-owned `PreparedCostProcessingUseCase` and
     `ProcessTransactionCashflowUseCase`; separate calculator consumers are migration-only. Replay
     remains a separate use case/consumer in the same deployable because it has distinct epoch and
     backlog controls.
     `transactions.persisted` requires the canonical transaction row to exist first; ingestion owns
     that persistence, while combined processing atomically owns derived cost/lot, cashflow,
     position, idempotency, and compatibility outbox effects. Every transaction emitted by the cost
     stage, including an `AUTO_GENERATE` settlement cash leg, must traverse both cashflow and
     position before the single commit; aggregate result counts must include every emitted leg.
     Ordinary BUY, SELL, DIVIDEND, and INTEREST booking metadata, validation reason codes, cash-entry
     policy, generated settlement-leg economics, and upstream pairing belong under
     `app/domain/transaction`. These policies consume immutable `BookedTransaction`; infrastructure
     maps existing `TransactionEvent` envelopes at the boundary and must preserve all governed
     envelope fields. The retired `portfolio_common.transaction_domain` package has no remaining
     owner-neutral runtime contract. Corporate-action, FX, and effective-processing policy now
     belongs to the service-owned transaction domain. Do not restore Pydantic canonical models,
     per-type linkage/validation modules, cash-entry helpers, settlement-pairing facades, or
     calculation policy under the shared library. The transaction-domain structure guard makes
     that retirement executable. FX economics use immutable dataclass values; event and
     persistence representations must remain at delivery and infrastructure boundaries.
128. Cost-basis strategies must reconcile aggregate holdings with source-level lot evidence. FIFO
     returns actual remaining source-lot quantity and cost. AVCO returns deterministic pro-rata
     source quantity and local/base cost whose sums exactly equal pooled holdings after every
     disposal and subsequent buy. Do not use an empty source-state map to mean every lot is closed:
     `position_lot_state`
     drives OPEN/CLOSED status and portfolio-tax-lot source products. Any strategy that cannot
     produce truthful source allocation must expose an explicit unsupported/degraded state rather
     than silently zeroing persisted rows. Preserve exact Decimal reconciliation and add sequential
     buy/disposal tests when changing cost-basis strategy state.
129. The target booked-transaction replay request path uses
     `BookedTransactionReplayRequestConsumer` -> request mapper ->
     `ReplayBookedTransactionUseCase` -> replay port -> SQLAlchemy/canonical replay adapter. Delivery
     must not create sessions, repositories, or producers, and must not implement a second retry or
     DLQ loop. Map database and canonical publication failures to the application-owned dependency
     error. Canonical replay infrastructure belongs under
     `app/infrastructure/transaction_replay/booked_transaction.py`. The adapter owns its short-lived
     SQLAlchemy session, publisher delegation, dependency error mapping, and zero-or-one cardinality
     invariant behind `BookedTransactionReplayPort`; do not restore a flat replay adapter module or
     broad infrastructure-root export.
     Then let `BaseConsumer` own bounded retry, exhaustion, DLQ, and offset handling. Preserve
     header-first correlation, payload fallback, and acknowledged missing/not-found requests unless
     a future contract change is intentional and versioned. Keep replay as the second consumer in
     the combined deployable because its backlog and operator controls differ from normal booking.
     Compose the final pair only through
     `app.runtime.consumer_composition.build_transaction_processing_consumers`; construct each
     application use case once per process. Load and inject the live and replay execution profiles
     independently by consumer group so throughput tuning cannot silently couple normal booking to
     operator replay. `BaseConsumer.shutdown()` is a two-phase contract: request polling stop first,
     let the active run loop drain and commit already-polled work, then close Kafka and flush DLQ
     resources. Shared supervision must allow at least the configured consumer drain window; do not
     close the consumer from delivery code or add a second local drain loop. The manager has one
     composition path: the live transaction consumer plus replay-request consumer. The removed
     six-consumer registry must not be restored.
     Concrete live, replay, and AVCO-reconciliation dependency assembly belongs in
     `app/runtime/dependency_composition.py`. Runtime consumers, operator commands, and test support
     must import those builders directly from the composition root; do not restore infrastructure-
     root builder exports or place dependency assembly inside adapters.
     The `app/infrastructure` root is a namespace, not a public adapter facade. Callers must import
     from the owned capability package (`cashflow`, `cost_basis`, `position`, `idempotency`,
     `transaction_mapping`, `transaction_processing`, `transaction_readiness`, or
     `transaction_replay`); do not restore cross-capability root exports.
     Unit tests mirror production ownership: Kafka mapper/consumer tests belong under
     `tests/unit/services/portfolio_transaction_processing_service/delivery/kafka`, while consumer
     composition and lifecycle-manager tests belong under the sibling `runtime` package. Core
     transaction processing and booked-transaction replay use-case tests belong under the sibling
     `application` package and use production-aligned module names; position-history orchestration
     tests follow the same application ownership. Domain behavior and package-structure guards
     belong under the matching `domain/<capability>` or `domain/<capability>/<family>` test package.
     Cross-layer legacy import and retired-facade
     confinement belongs under the service's `architecture` test package. Runtime
     wheel, Docker source-closure, and image contract tests belong under the service's `packaging`
     test package. Worker health, readiness, metrics, version, and HTTP security contracts belong
     under `delivery/http`. Do not return delivery, runtime, application behavior, domain-structure,
     cross-layer architecture, or packaging tests to the flat service-test root; keep that root free
     of test modules so new coverage must declare an owned capability or layer.
     Consumer lag must be observed only after a successful offset commit using cached Kafka high
     watermarks. Keep lag labels bounded to service/topic/group/partition, never query the broker per
     message, and isolate missing watermark or metric failures from transaction outcomes.
     Sample async database pool state only from shared infrastructure/readiness after a successful
     dependency check. Use bounded pool/state gauges, normalize negative prefill overflow, and never
     let telemetry failure alter readiness or financial transaction behavior.
     Keep combined-runtime operating signals together in the focused transaction-processing
     dashboard. Do not invent lag, latency, pool, or outbox alert thresholds from unit/engine-only
     evidence; derive and review them from deployed baseline and failure-recovery measurements.
     Every broad app-local dashboard service filter must use the current Prometheus scrape-job
     inventory. A runtime cutover must replace retired worker job names in those aggregate filters
     and prove the target job is present; a focused dashboard alone does not preserve fleet-level
     uptime and request-rate visibility.
     Duplicate replay requests may carry distinct Kafka event IDs, but the combined processing
     authority applies one versioned semantic transaction exactly once. Preserve one semantic
     claim, one cashflow/final position state, and one compatibility processed fact. Keep governed
     replay request/audit evidence at the replay control boundary; do not use duplicate financial
     facts as delivery audit evidence.
     Backdated position handling is topology-specific: deployed compatibility consumers retain
     `QUEUE_REPLAY`, while `CombinedPositionCalculationWorkflow` must use `REBUILD_INLINE` to
     advance the compare-and-set epoch and rebuild ordered current-epoch history in the combined
     unit of work. Do not emit `ReprocessTransactionReplay` from the final two-consumer path because
     it intentionally has no `transactions.cost.processed` replay consumer.
     In the combined use case, position processing must determine any inline recovery epoch before
     cashflow staging. When position recovery returns rebuilt transactions, cashflow must stage the
     deduplicated rebuilt timeline in the new epoch, including the later suffix; otherwise
     current-epoch income and cashflow reads lose the rebuilt records.
     After cost, position, and cashflow effects succeed, the same deduplicated rebuilt transaction
     set must register current-epoch readiness through the transaction-processing readiness use
     case and ports before commit. Keep readiness claims and outbox staging in the combined unit of
     work so any financial-effect or readiness failure rolls back atomically. Do not broaden
     compatibility cost-topic publication to every recalculated suffix row; the topic has no active
     in-repo consumer and is not a readiness transport.
     The target health contract is locked by
     `test_web_health_contract.py`: readiness requires database, Kafka, and worker runtime; a failed
     runtime task returns 503; and `/version` must equal readiness build metadata for commit, branch,
     timestamp, repo, image version/digest, CI run ID, and OCI labels.
     Keep this surface registered as `health_only_worker_api` in
     `contracts/security/security-control-coverage.v1.json`. Adding any business route requires an
     intentional app reclassification, enterprise middleware, payload controls, and new tests.
     `ConsumerManager` uses `build_transaction_processing_consumers()` exclusively. Deployment must
     replace the three calculator workers atomically and must never run both topologies together.
     The target image must not install the three standalone calculator wheels: they expose
     overlapping top-level package names (`core`, `consumers`, and `repositories`) and can overwrite
     one another. Build one target wheel, install `portfolio-common`, and copy only the bounded
     calculator source closure under `src.services.calculators...`; never copy all Core services to
     make imports pass. The combined pipeline-stage adapter also requires the exact pipeline
     readiness service, repository, domain-policy, and event-mapping source closure, while legacy
     pipeline consumers and runtime modules remain excluded. The Docker build must import the real
     target entrypoint and unit of work after copying that closure. Keep
     `test_image_package_contract.py` and image provenance gates blocking.
     Combined-runtime business metrics must enter through the framework-neutral
     `TransactionProcessingObserver` port. Keep Prometheus and clocks in infrastructure; use only
     governed `stage` and `outcome` labels; never label by portfolio, transaction, event,
     correlation, trace, exception, or error text. Preserve target attribution for live/replay,
     idempotency, cost, cashflow, each position leg, and commit after service consolidation.
     Every transaction emitted by cost processing, including a generated settlement cash leg, must
     traverse both cashflow and position processing inside the same unit of work.
     Deterministic full-history cost recalculation remains the fallback correctness baseline and is
     supported by the normalized portfolio/security/date/transaction index. Strictly ordered,
     version-compatible events may restore durable open-lot state and calculate only the incoming
     row. For a backdated input, persist the
     incoming row and deterministic later suffix in engine order inside the combined unit of work,
     but publish only the incoming processed event so inline position rebuild is not double-applied.
     Any engine error in the recalculated timeline must fail closed before suffix persistence.
     Run `make test-transaction-processing-contract` for the complete DB-direct combined contract.
     PR Merge Gate and Main Releasability run this manifest-owned suite as blocking evidence.
     Do not add the target to Compose-backed CI service sets until the atomic deployment slice also
     removes cost, cashflow, and position legacy workers from those sets.
130. Full-history cost FX enrichment must batch authoritative effective-dated reads by normalized
     `(trade_currency, portfolio_base_currency)` pair. For `N` cross-currency transactions over `P`
     distinct pairs, issue `P` indexed seed-plus-window queries, then select the latest rate on or
     before each transaction date from immutable `EffectiveFxRate` domain records. The framework-
     neutral `application.cost_basis_processing.enrich_cost_basis_transactions_with_fx` policy owns
     this selection; infrastructure supplies the port and stages its result. Do not return
     SQLAlchemy `FxRate` rows from new repository methods, issue per-transaction FX queries, cache
     effective rates without explicit freshness/invalidation ownership, or substitute a future,
     default, or inferred rate when the seed is missing. Same-currency rows require no FX read.
     Preserve the deterministic full-history methodology until long-history capacity evidence or a
     parity-proven incremental-state decision supports changing it.
131. FIFO available quantity is maintained as exact aggregate state inside
     `FIFOBasisStrategy`; BUY acceptance increases it and successful disposal decreases it by the
     matched quantity. Do not reintroduce an open-lot scan into availability checks. Preserve the
     iteration-forbidden invariant test and use `make profile-cost-history-capacity` for the
     machine-readable parser/sorter/engine profile. This profile is engine characterization, not a
     production throughput SLO. AVCO uses lazy quantity and independent local/base basis scales;
     do not reintroduce per-disposal source scans. Materialization must preserve the exact pooled
     residual and source-state sums after sequential disposal, full close/reopen, and basis transfer.
132. Incremental cost processing is governed by `CostBasisProcessingCheckpoint` and the same
     `transaction_order_key(...)` used by engine sorting. Use it only when checkpoint version,
     portfolio/security identity, cost-basis method, registry lot behavior, and strict ordering all
     match. Missing, incompatible, same-order, backdated, or unsupported state must use deterministic
     full replay. Existing portfolios establish state through a full rebuild; never infer a current
     checkpoint or hide a missing table. Every full rebuild must persist the complete rebuilt lot
     snapshot, including a rebuild triggered by a non-lot event, before establishing its checkpoint;
     otherwise a later incremental disposal can restore stale quantity or cost. Persist checkpoint,
     affected cost suffix, lot state,
     cashflow, position, idempotency, and outbox effects in the combined unit of work. Use
     `make profile-cost-processing-modes` to keep ordered opening, state-dependent disposal, and
     backdated rebuild evidence separate. Large open-lot restore depth remains a measured hotspot;
     optimize it only with durable state ownership and exact quantity/local/base parity.
133. True corporate-action cash consideration is not income. `CASH_CONSIDERATION` is a zero
     quantity/zero price product marker classified as `CORPORATE_ACTION_PROCEEDS`; the actual cash
     account movement is a linked `ADJUSTMENT`. Require source-owned
     `allocated_cost_basis_local` and `allocated_cost_basis_base`. Same-currency processing derives
     capital P&L and zero FX P&L; cross-currency processing requires explicit capital and FX
     components and validates their totals. Bundle A must reconcile source basis to target basis
     plus cash-allocated basis and emit `insufficient_cash_basis` when evidence is absent. Keep the
     pure policy in `portfolio_transaction_processing_service.app.domain.cost_basis`, persist calculated
     extension fields through `Transaction.set_calculated_field(...)`, and prove changes through
     the mixed-demerger PostgreSQL contract. Do not map cash consideration back to generic income,
     infer missing basis. `CASH_IN_LIEU` is the separate fractional overlay: require positive
     fractional quantity/proceeds and explicit allocated local/base basis; consumed lot quantity and
     both basis values must match exactly. Classify its synthetic product flow as position-level
     `TRANSFER`, never income, and keep the linked `ADJUSTMENT` as the actual cash-account movement.
     Cross-currency adjustment legs must use latest-on-or-before FX, direction-aware signed
     local/base cash basis, and no realized P&L. Product and linked cash flows must sum to zero in
     settlement currency without double counting; preserve capital/FX/total P&L on the product leg.
134. Ordered FIFO `consume_lot` processing restores only the oldest positive source lots needed to
     cover the requested quantity. Repository ordering must match canonical transaction date,
     original quantity descending, and source transaction ID; insufficient holdings still flow to
     the domain engine for rejection. Carry selected-lot versus complete-snapshot update scope
     explicitly. Selected updates must fail on a missing source row and must never close omitted
     later lots. Keep AVCO, basis transfer, and full rebuild persistence as complete snapshots until
     a separate pooled-state design proves exact quantity plus local/base basis reconciliation.
     Preserve the matching database index and the profile restored-lot-count evidence.
135. Ordered AVCO `open_lot` and `consume_lot` processing restores the versioned
     `average_cost_pool_state` aggregate under a row lock scoped to that table. Treat this row as
     durable transactional cost-basis state, not a cache. Missing, incompatible, source-less,
     basis-transfer, or unsupported state must use deterministic full replay and establish a new
     checkpoint. `position_lot_state` remains externally visible source-lineage truth: reconcile
     existing rows with set-based quantity/local/base scaling, assign the exact Decimal residual to
     the representative source, and update explicit new sources separately. Pool checkpoint,
     source rows, transaction cost, cashflow, position, idempotency, and outbox writes share the
     combined unit of work and fail closed together. Do not replace AVCO with FIFO subset semantics,
     infer historical checkpoint currency, or claim current historical source evidence before the
     governed backfill passes.
136. Historical AVCO reconciliation must derive expected state from deterministic canonical
     transaction-history replay, never from summing potentially stale pool or source rows. Route
     operator execution through `ReconcileAverageCostPoolsUseCase` and its port; keep CLI/Make as
     delivery only. Dry-run is default. Candidate traversal is bounded, unique, and deterministic
     by portfolio/security keyset cursor. Apply one key per database transaction, reconstruct every
     canonical opening source with bounded bulk upserts, persist pool plus ordering checkpoints,
     and commit only after source count, quantity, local basis, and base basis all equal replay truth
     in both source and pool representations. A failed post-write check must roll back and report
     pre-write persisted evidence with a bounded reason code. Do not publish business events or
     silently delete unmatched lineage from this maintenance path.
137. Ordered AVCO disposal database round trips must remain independent of source-lot count. The
     governed local contract is five cost-state statements: locked pool read, set-based
     non-residual update, aggregate source read, representative residual update, and pool upsert.
     Do not reintroduce source-lot materialization into the application or per-source update loops.
     Keep normalized portfolio/security predicates compatible with
     `ix_position_lot_norm_port_sec`. Scope `FOR UPDATE` to `average_cost_pool_state` so unrelated
     keys remain available; same-key serialization is intentional and must be measured with
     connection-pool wait and partition-ordering evidence before cutover. Treat local query-count,
     index-plan, and lock-timeout tests as structural proof, not deployed p95/p99 certification.
138. App-local Compose and every Compose-backed CI lane use
     `portfolio_transaction_processing_service`; never add the legacy cost, cashflow, or position
     worker shells beside it. Cost, cashflow, and position remain separate financial modules behind
     `ProcessTransactionUseCase` and one SQLAlchemy unit of work; valuation remains a separate
     job-driven runtime. Before an environment cutover, quiesce producers, drain and stop legacy
     consumers, then use `scripts/operations/transaction_processing_cutover_offsets.py` in dry-run and explicit
     apply modes to verify inactive groups, zero source lag, aligned cost/cashflow offsets, and exact
     live/replay target offsets. Never use earliest/latest reset policy as a handoff. Load evidence
     must seed valid portfolio/instrument source facts, use the run business date, and measure through
     persisted cost, cashflow, position, and combined-idempotency completion; HTTP submission rate is
     not transaction throughput. Resolve support logs by Compose project and service identity, not
     generated container name. Failure recovery must interrupt the unified service and prove source
     persistence, committed live-group lag growth, exact domain/claim completion, live/replay lag
     return to baseline, and no incremental DLQ event; ingestion-job backlog is not a transaction
     recovery proxy and a timeout is never a passing result. Registry publication, controlled
     cluster rollout, shutdown-under-load and pool-pressure evidence, and canonical QA remain
     required before claiming production consolidation. The physical legacy transaction-calculator
     packages are removed locally and must not be restored. Kubernetes source
     must contain one
     digest-only `portfolio-transaction-processing` Deployment and one KEDA object with canonical
     live/replay groups; never restore the three legacy worker/scaler/image inventories. Render the
     deployable manifest only from the target CI release manifest after SBOM, scan, signature,
     provenance, digest, and same-image dev/UAT/prod checks pass. Treat the checked-in all-zero
     digest as a fail-closed template placeholder, never as a deployable image. Registry publication,
     server-side validation, controlled cluster rollout, and rollback evidence remain mandatory.
139. `ProcessedTransactionPersisted` from `portfolio_transaction_processing_service` is the
     authoritative in-repo transaction-completion fact because it is committed in the same unit of
     work as cost, cashflow, position, idempotency, and outbox effects. Pipeline transaction
     readiness consumes only that fact; do not restore a `cashflows.calculated` prerequisite,
     consumer group, second idempotency claim, or transaction-type-specific readiness branch.
     Inline backdated recovery may register a newer stage epoch before an older cost outbox event is
     dispatched. Serialize readiness registration for the exact stage/portfolio/transaction key,
     compare the incoming epoch with the latest registered epoch under that transaction-scoped lock,
     and reject only older epochs. Never emit superseded transaction or valuation readiness.
     Keep that coordination in the `application/transaction_readiness` use case behind the
     `ports/transaction_readiness.py` repository and event-staging contracts. Governed event DTOs,
     topics, payload mapping, and transactional outbox writes belong to
     `infrastructure/transaction_readiness`; do not restore readiness policy to a SQL/outbox adapter.
     `TransactionProcessingUnitOfWork.readiness` composes that application use case directly from
     the package-owned stage repository and event stager. Do not restore the ambiguous `pipeline`
     unit-of-work property or a flat compatibility adapter.
     Any facade or package-root re-export deletion must run `make warning-gate` before commit;
     focused owner tests do not prove that tests or tooling elsewhere in the repository stopped
     importing the retired surface.
     Transaction claim persistence, the stable `portfolio-transaction-processing` service identity,
     and repository-to-application claim outcome translation belong under
     `app/infrastructure/idempotency`. `SqlAlchemyTransactionProcessingUnitOfWork` owns one session,
     transaction lifecycle, and adapter composition; do not embed the idempotency adapter in that
     module or restore its broad infrastructure-root re-export. Tests and support queries that need
     the persisted service identity must import it from the idempotency package.
     Governed transaction-event and synthetic FX-instrument translation belongs under
     `app/infrastructure/transaction_mapping`, with explicit `booked_transaction.py` and
     `foreign_exchange_instrument.py` modules. Cost, cashflow, repository, and test consumers must
     use that anti-corruption boundary; do not restore flat `booked_transaction_event_mapper.py` or
     `fx_event_mapper.py` infrastructure roots or place Pydantic event mapping in domain/application
     modules.
     Aggregate live/replay stage telemetry belongs under
     `app/infrastructure/transaction_processing/observability.py` behind the application observer
     port. Corporate-action basis-reconciliation telemetry belongs with its financial capability at
     `app/infrastructure/cost_basis/corporate_action_observability.py`. Keep both adapters out of the
     broad infrastructure package root, mirror their tests under the owned packages, and do not
     restore flat generic or corporate-action observability modules.
     Retain `cashflows.calculated`, `transaction_processing.ready`, and compatible stage fields only
     until downstream usage and retention evidence permit governed retirement. Event supportability
     actor names and full-stack test service/port inventories must use current runtime-boundary
     identities. Static event guards must resolve dependency-injected consumer factory defaults so
     target DLQ wiring cannot disappear from certification. Full-stack tests must allocate the
     target's `LOTUS_TRANSACTION_PROCESSING_HOST_PORT`; never reintroduce deleted calculator ports
     or rely on the app-local default when parallel stacks may run. Compose-backed recovery restart
     sets and health checks must derive from `scripts/quality/ci_service_sets.py`, not duplicate a
     local service list. Compose-backed tests and operational drivers that select dynamic ports
     must call
     `prepare_test_runtime(...)`, export its environment when process-global consumers require it,
     and pass the complete `PreparedTestRuntime` to Compose helpers. Dynamic ports remain bound
     until each startup attempt; a recognized bind conflict reallocates the complete dynamic
     generation and refreshes PostgreSQL, Kafka, and HTTP endpoints before retry. Fixed endpoints
     remain valid only as explicit operator overrides and must never be changed by automatic
     reallocation. The suite launcher must let the pytest child own reservations rather than
     allocating and releasing ports in its parent process. Concurrent same-process projects must
     use their prepared runtime as the subprocess environment instead of mutating shared process
     state. When local startup requests image builds, build while reservations remain held and run
     Compose startup without `--build` only after release; do not widen the bind race with a long
     `up --build` operation.
     Latency, performance-load, Docker-smoke, institutional-completion, and failure-recovery
     drivers must compose through `ManagedComposeRun`; do not restore driver-local
     startup/retry/teardown helpers.
     Managed runs discard inherited parent-runtime ports, preserve explicit local endpoint URL
     overrides, inspect the exact project, capture project/file identity before teardown, and clean
     their stack by default. Workflow artifacts must upload the owner-produced diagnostic path and
     must not run default-project `docker compose logs` after the driver returns. Use
     `--skip-compose` only for an already-running target and keep-stack flags only for explicit local
     diagnosis. Failure recovery must pass its prepared runtime to migration polling and capture
     `output/task-runs/diagnostics/failure-recovery-gate-compose.log` before teardown.
     Its JSON and Markdown reports must retain field-level actual/target/comparison/satisfaction
     evidence plus source UTC last-change timestamps. Exact-count overshoot and source-owned DLQ
     growth are terminal evidence and must stop polling before another sleep. App certification
     delegates runtime ownership to the managed Docker-smoke driver; do not add a second lifecycle
     owner around it.
140. Active cost execution, SQL repositories, financial staging, AVCO/FIFO state, corporate-action
     reconciliation, and metrics belong to `portfolio_transaction_processing_service`: application
     execution and effect coordination live under `app/application/cost_basis_processing`; SQL,
     event, outbox, and Prometheus adapters live under `app/infrastructure/cost_basis`. The installed target image must not copy
     `calculators/cost_calculator_service`. The standalone `CostCalculatorConsumer` and its
     physical-idempotency, retry, and DLQ transaction boundary are retired. Unified Kafka delivery
     tests, `ProcessTransactionUseCase`, target adapters, and combined PostgreSQL tests are the
     authoritative delivery and atomicity evidence; do not recreate a calculator worker shell.
141. Cashflow source ownership belongs to
     `portfolio_transaction_processing_service`: vocabulary is under `app.domain.cashflow`, while
     calculation, rule caching, SQL persistence, epoch fencing, and compatibility outbox staging are
     under `app.infrastructure` behind `CashflowProcessingPort`. Do not recreate
     `calculators/cashflow_calculator_service`, a standalone cashflow consumer, or a second
     transaction/physical-idempotency boundary. Preserve the historical semantic-idempotency service
     name unless replay migration evidence explicitly approves a change. New cashflow tests belong
     with the target service. Rebuild the target image and prove the installed entrypoint after any
     source-ownership move; repo-root imports are insufficient.
142. Combined transaction idempotency is semantic as well as physical. Derive the versioned key and
     SHA-256 payload fingerprint from the framework-neutral `BookedTransaction`, never raw Kafka
     JSON. Claim it inside the same SQLAlchemy unit of work before cost, cashflow, position, or
     outbox staging. Distinguish `physical_duplicate`, `semantic_duplicate`, and
     `semantic_conflict` in bounded metrics. Identical cross-topic/offset replays return the existing
     duplicate result without another compatibility processed fact; materially changed content for
     the same portfolio/transaction/epoch fails terminally as `transaction_semantic_conflict`.
     Fingerprint source transaction intent, not processor-owned cost/P&L outputs or deterministic
     default lineage and policy enrichment added before persisted replay. Ordinary duplicate-
     delivery load gates must measure completed duplicate outcomes through
     `lotus_core_transaction_processing_operations_total{stage="transaction",outcome="duplicate"}`;
     they must not wait for new `processed_events` rows because successful semantic duplicates
     intentionally preserve the existing idempotency record. Canonical repair replay is different:
     it intentionally completes the unified financial flow and its drain probe must wait for the
     incremental `stage="transaction",outcome="processed"` count.
     Normalize `<transaction_id>-CASHLEG` only when `cash_entry_mode=AUTO_GENERATE`; caller-supplied
     external cash identifiers and generated-shaped identifiers in upstream-provided mode remain
     material conflict inputs.
     Canonical booked-transaction replay is the only path that may continue after an identical
     semantic claim or an explicit canonical correction. It must carry the exact internal
     `lotus-transaction-processing-intent=repair` delivery header. Identical repair payloads claim
     a separate physical repair-delivery fence; materially corrected payloads claim an immutable
     `transaction-correction:v1` semantic identity containing the canonical SHA-256 fingerprint,
     preserving the original semantic row and every distinct correction row. A standard changed
     delivery, correction-identity conflict, missing or unknown intent remains fail-closed;
     malformed or repeated intent headers fail closed too. Cashflow repair
     restores the canonical transaction/epoch row through an atomic PostgreSQL conflict-update
     keyed by the existing unique constraint instead of allowing its semantic fence to turn repair
     into a no-op or using a check-then-insert race for a missing row. Prove missing, corrupted, and
     concurrent derived-state repair, physical redelivery suppression, rollback retry, and conflict
     rejection against PostgreSQL.
     Existing physical-only consumers and pre-migration null semantic fences remain compatible.
     Any identity-version change requires migration, replay/downstream impact analysis, deterministic
     hash tests, PostgreSQL conflict/concurrency proof, and explicit documentation.
143. Every destructive `position_history` delete/reinsert window acquires the transaction-scoped
     PostgreSQL advisory lock for normalized portfolio/security/epoch before deleting or reading
     its replay window. Keep the lock inside the caller-owned combined SQLAlchemy transaction and
     recompute from canonical transactions after acquisition; never calculate a stale replacement
     set before waiting. Backdated epoch advancement remains compare-and-set: only a successful
     winner increments the epoch-bump metric, while a stale loser records bounded
     `coalesced/stale_epoch` coordination and performs no replay/rebuild work. Preserve concurrency
     across different securities and epochs. Any lock-key, ordering, or replay-window change needs
     same-key PostgreSQL overlap proof, different-key non-blocking proof, exact final row/value
     reconciliation, bounded lock-wait metrics, structured support logs, and deployed pool/latency
     evidence before cutover.
144. Every mutable cost-basis transition acquires the transaction-scoped PostgreSQL advisory lock
     for normalized portfolio/security before reading the processing checkpoint, transaction
     history, open lots, or AVCO aggregate. This includes FIFO selected-lot updates, full rebuilds,
     first-write upserts, replay, backdated processing, and historical AVCO reconciliation. Keep
     the lock inside the caller-owned SQLAlchemy transaction and recompute after acquisition; Kafka
     key ordering is not a database fence. Preserve parallelism across different securities.
     Audit current state through the source lot's calculation policy/version plus the aggregate
     checkpoint's cost-basis method, latest calculation transaction, and engine-state version.
     A full AVCO rebuild must refresh the complete persisted source-lot snapshot and the aggregate
     pool checkpoint in the same caller-owned transaction. Persisting only the pool can leave source
     lots stale and corrupt the next incremental allocation.
     Any lock-key or mutation-boundary change requires same-key PostgreSQL BUY/SELL/replay overlap
     proof, different-key non-blocking proof, exact lot/checkpoint reconciliation, bounded lock-wait
     telemetry, and deployed pool/latency evidence before cutover.
145. A backdated position trigger is zero-work when its transaction lineage already exists in the
     current portfolio/security epoch. Evaluate the pure backdated-date policy first, then use the
     indexed normalized portfolio/security/epoch/transaction existence query before compare-and-set
     epoch advancement. Record `coalesced/already_materialized`, do not read full history, advance
     epoch, delete/reinsert positions, or publish replay events, and keep normal ordered processing
     free of this extra query. This is safe because combined semantic idempotency rejects materially
     changed content outside the explicit correction workflow; an accepted correction has its own
     immutable identity and executes the governed rebuild. The cost-basis key lock serializes the
     caller-owned units of work. Any change requires concurrent committed backdated-trigger proof,
     exact current-epoch quantities/cost, one-winner epoch evidence, zero active-runtime replay
     fan-out, bounded recalculation work-volume metrics, and migration/index validation.
146. Position balance and deterministic history policy are owned by
     `portfolio_transaction_processing_service/app/domain/position`; caller-transaction
     orchestration is owned by `app/application/position_history.py`; contracts are owned by
     `app/ports/position_history.py`; SQLAlchemy, state-store, metric, and structured-log adapters
     are owned by `app/infrastructure/position`. The production unit of work must pass `BookedTransaction`
     directly to `PositionHistoryProcessor`; do not restore the
     `BookedTransaction -> TransactionEvent -> BookedTransaction` round trip or perform a second
     position-state read for epoch fencing. The former infrastructure workflow and repository are
     retired; canonical PostgreSQL tests exercise the application and adapter boundaries directly.
     Do not recreate `src/services/calculators/position_calculator`, copy it into the
     target image, or place framework, session, repository, metric, or logging concerns in domain
     or application code. Any replacement must preserve the production import inventory, focused
     domain/integration proof, downstream contract review, and the machine absence guard.
147. After cost, cashflow, and position target ownership and production evidence are complete,
     review the runtime boundaries among timeseries generation, valuation orchestration, pipeline
     orchestration, portfolio aggregation, and position valuation. Decide `keep`, `merge as
     in-process modules`, or `retire` per capability using trigger, state ownership, atomicity,
     ordering, scale and backfill, failure isolation, deployment cadence, SLO, security, and
     operating ownership evidence. Treat redundant pipeline stage gates as deletion candidates,
     not automatic merge candidates. Keep position valuation separate from transaction processing
     unless measured market/job workload evidence invalidates its independent scaling and isolation
     rationale.
148. Cost-basis models and deterministic policy are owned by
     `portfolio_transaction_processing_service.app.domain.cost_basis`. Import its public API; do
     not recreate `cost_engine`, generic `processing/parser/sorter/error_reporter` modules, or a
     second transaction calculation model. Every new target-owned module requires a responsibility
     docstring and framework-free domain proof. Keep transitional workflow, checkpoint, and
     repository code outside the domain until explicit application ports and infrastructure
     records exist. Database simplification follows ownership stabilization and requires additive
     migration, rollback, replay/backfill, query-plan, concurrency, and downstream read-contract
     evidence.
149. `transaction_costs` stores only positive normalized fee components. `position_lot_state`
     requires nonnegative open quantity and local/base basis, with open quantity no greater than
     original quantity. Preserve these checks in ORM metadata and migrations and prove rejection
     on PostgreSQL; application validation is not a database integrity boundary. Do not add accrued
     income sign constraints without bond ex-coupon methodology evidence. Before deployment,
     report violating keys through privacy-safe diagnostics and remediate through governed
     reconciliation, never silent migration coercion. Keep cost components, lot lineage,
     incremental checkpoints, and AVCO aggregates separate until cardinality, lifecycle,
     query-plan, and write-amplification evidence supports a different table boundary.
150. Incremental and average-cost checkpoint policies are owned by
     `portfolio_transaction_processing_service.app.domain.cost_basis` and imported through its
     public API. Domain code uses `calculation_state_version`; the compatible persistence column
     remains `engine_state_version` and must be mapped explicitly by the repository. Do not restore
     legacy checkpoint modules, reflect domain dataclasses directly into SQL payloads, or rename
     deployed storage as an incidental source move. A schema rename requires a separate migration,
     rollback, reader/writer inventory, and deployment proof. Keep Prometheus metrics, clocks,
     sessions, and SQL records outside checkpoint and calculation policy.
151. Cost timeline parsing, ordering, and calculation coordination is target application behavior
     owned by `portfolio_transaction_processing_service.app.application.CostBasisTimelineProcessor`.
     Depend on the framework-neutral `CostBasisCalculationObserver` port; only target
     infrastructure may adapt it to Prometheus and a wall clock. Preserve existing metric names
     through composition, isolate telemetry failure from financial processing, and do not recreate
     the legacy `transaction_processor.py` path or generic aliases. Workflow, SQL repository, and
     compatibility delivery remain separate migration slices with their own ports and transaction
     boundary proof.
152. Cost-basis and FX execution is application behavior owned by
     `PreparedCostProcessingUseCase`; settlement/reconciliation/outbox coordination crosses domain
     values through `coordinate_cost_processing_effects` and `CostProcessingEffectStagingPort`.
     `CostBasisProcessingAdapter` maps reference-data availability and application errors only. The
     combined path remains `ProcessTransactionUseCase` -> `CostProcessingPort` -> adapter ->
     application use case inside one SQLAlchemy unit of work. Never restore
     `cost_calculation_workflow.py`, `staged_effects.py`, framework-event round trips, generic
     processor aliases, or a second transaction boundary.
153. Every independently built service wheel must discover packages from the service root and
     explicitly include the runtime `app` namespace. Use setuptools `where = ["."]` with an
     `app*` include unless a separately proven packaging model replaces it. A Dockerfile entrypoint
     such as `python -m app.main` requires built-wheel or installed-image proof that `app/main.py`
     and imported subpackages are present; repo-root tests and bind-mounted Compose are not package
     closure evidence. Keep `tests/unit/test_service_wheel_package_contract.py` in the fast lane and
     extend it when adding service projects.
154. `ValuationJobProcessor` requires an injected session provider and dependency factory;
     `position_valuation_calculator.app.infrastructure` owns production defaults and concrete
     `ValuationRepository`, `IdempotencyRepository`, and `OutboxRepository` construction. Do not
     restore constructors or `get_async_db_session` in the processor or patch those globals in
     tests. The processor is not yet application-layer clean: keep it transitional until valuation
     persistence records, metrics, publication, and transaction ownership are behind typed ports
     and a unit of work. `POSITION_VALUATION_WORKER_COUNT` controls in-process Kafka worker count;
     app-local Compose pre-shards topics and runs eight workers so portfolio-keyed partitions can
     execute concurrently while each partition remains serial. Keep worker count at or below the
     available `valuation.job.requested` partitions and keep the publisher key portfolio-owned so
     one portfolio's valuation dates retain broker ordering. Position valuation remains a separate
     deployable unless workload and failure-isolation evidence justifies a boundary change.
155. `portfolio_common` is a shared distribution boundary, not an architecture layer or a default
     home for reusable-looking code. Put framework-independent cross-service domain policy under
     `portfolio_common.domain`; keep FastAPI, Pydantic, SQLAlchemy, Kafka, and HTTP dependencies out
     of that namespace. Before adding or moving another shared module, inventory production
     consumers and classify state ownership, transaction ownership, dependency type, and service
     lifecycle. Move service-owned workflow/repository code to its owning service when safe; retain
     stable event, identity, monetary, runtime-port, and supportability contracts when multiple
     deployables legitimately share them. Do not restore generic `portfolio_common.models`, root
     transaction control-code helpers, or duplicate compatibility facades.
     Shared cost-basis vocabulary, analytics cashflow semantics, currency normalization, and
     decimal amount policy live at `portfolio_common.domain.cost_basis_method`,
     `portfolio_common.domain.analytics.cashflow_semantics`, `portfolio_common.domain.currency`,
     and `portfolio_common.domain.decimal_amount`. Import those canonical owners directly; do not
     restore their deleted root modules. Query Service strict decimal acceptance remains
     service-owned under `query_service.app.domain.strict_decimal`, while SQL currency expressions
     remain repository infrastructure rather than domain policy.
156. Shared SQLAlchemy adapters belong under `portfolio_common.infrastructure.persistence` only
     while multiple deployables genuinely use the same behavior. Do not name concrete repositories
     `Base` or place them at the shared package root. Timeseries persistence is now service-owned;
     shared timeseries infrastructure is limited to typed instrument/FX reads and stateless upsert
     statement construction. Never move aggregation state into the generator merely because
     historical integration tests live under its test directory.
157. Portfolio aggregation job queue persistence is owned by
     `portfolio_derived_state_service.app.infrastructure.PortfolioAggregationRepository`. Keep
     eligible-job claiming, `FOR UPDATE SKIP LOCKED`, deterministic claim ordering, dispatch
     recovery, stale retry/failure policy, and queue diagnostics out of `portfolio_common` and
     position-timeseries repositories. Aggregation tests belong under the target's mirrored
     application/domain/infrastructure test paths. Do not restore the generic aggregation `TimeseriesRepository` wrapper or queue
     methods on a shared repository; preserve existing metric labels until an intentional
     observability-contract migration is approved and tested.
158. Timeseries data persistence is service-owned. Use
     `TimeseriesGenerationRepository` for generator snapshot/cashflow/position-timeseries access
     and `PortfolioAggregationRepository` for aggregation queue/portfolio/as-of persistence. Shared
     infrastructure is limited to `TimeseriesMarketDataReader`, immutable timeseries market-data
     records, `TimeseriesMarketDataPort`, and stateless upsert statement builders. Do not restore
     `SharedTimeseriesRepository`, either generic service `TimeseriesRepository` wrapper, or the
     dead generator copy of portfolio aggregation logic. This ownership cleanup enables but does
     not approve a runtime merge; use `lotus-core-end-state-runtime-vision.md` and measured load,
     backfill, fan-in, failure, SLO, and rollback evidence.

159. Generic simulation is owned end to end by `query_control_plane_service`: API contracts under
     `app/contracts`, commands/results and orchestration under `app/application`, immutable state
     and transaction-effect policy under `app/domain`, dependency contracts under `app/ports`, and
     SQLAlchemy mapping/query/UoW behavior under `app/infrastructure`. Routers map requests to
     commands and results to response DTOs. Do not restore query-service simulation DTO/workflow or
     generic UoW files, import query-service repositories from QCP, or mix advisory suitability and
     recommendation logic into generic projection. The old QS `SimulationRepository` is temporary
     Core-snapshot compatibility only and must retire with that ownership move. QCP `app.main`
     remains package-closure incomplete until analytics, integration/Core snapshot,
     operations/support, and advisory compatibility no longer import QS implementation modules.
160. Source-data product runtime metadata is a stable cross-service contract owned by
     `portfolio_common.source_data_product_metadata` beside the source-product catalog. Query
     Service and Query Control Plane response contracts may import its Pydantic metadata models,
     product identity field helpers, deterministic content hash, lineage normalization, and
     freshness builder. Do not recreate service-local metadata helpers or use this shared boundary
     for service-owned API DTOs, workflows, repositories, settings, or SQL adapters.
161. Analytics input and export ownership belongs to `query_control_plane_service`: public DTOs
     under `app/contracts/analytics_inputs.py`, orchestration/policy under
     `app/application/analytics`, immutable portfolio/export records under `app/domain`, reader,
     export-store, and unit-of-work contracts under `app/ports/analytics.py`, and SQLAlchemy
     adapters under `app/infrastructure`. Do not restore Query Service analytics contracts,
     workflow, repositories, or export settings; Query Service operations may read export-job
     support state only until the operations family moves. Position valuation, prior-EOD,
     cashflow, FX, portfolio, and export persistence results must be mapped to immutable records
     inside infrastructure adapters before crossing ports. The complete analytics boundary is
     enforced by configured `make typecheck`; do not reintroduce attribute-shaped `object` rows,
     broad `Any` port returns, or application dependencies on SQLAlchemy result shapes.
162. `ClientRestrictionProfile:v1` is the first reference integration source product owned end to
     end by `query_control_plane_service`: public DTOs under `app/contracts`, selection and
     supportability policy under `app/application`, immutable mandate/restriction records under
     `app/domain`, the source reader under `app/ports`, and deterministic effective-dated SQL under
     `app/infrastructure`. Do not restore its Query Service DTO, mapper, repository method,
     application module, or broad integration-facade method. Core owns source restriction evidence;
     `lotus-manage` owns DPM interpretation, enforcement, workflow, and user-facing conclusions.
     Preserve the public route and response contract while moving the remaining reference families
     through complete vertical slices.
163. `SustainabilityPreferenceProfile:v1` is also QCP-owned end to end. Client-profile products
     share `EffectiveMandateBinding` resolution, typed evidence timestamp policy, and deterministic
     effective-row query helpers, but retain product-specific contracts, domain records, source
     ports, SQL adapters, supportability reasons, and field mapping. Do not restore sustainability
     DTOs, mapper, repository method, application service, or facade methods under Query Service.
     Core owns captured sustainability preference evidence; `lotus-manage` owns construction and
     rebalance interpretation and must not infer unstated preferences.
164. `ClientTaxProfile:v1` is QCP-owned end to end and composes the shared effective-mandate,
     evidence-timestamp, effective-window, and deterministic-ranking boundaries. Keep its contract,
     application service, immutable records, source port, and SQL adapter out of Query Service.
     Core publishes bounded tax-reference evidence only; do not add tax advice, after-tax
     optimization, tax-loss-harvesting suitability, client approval, or jurisdiction-specific
     recommendations to this source product.
165. `ClientTaxRuleSet:v1` is QCP-owned end to end and shares the same profile foundation while
     retaining rule-set, tax-year, jurisdiction, rule-code, rate, threshold, and version semantics
     in its own contract/domain/port/adapter. Do not restore its Query Service path. Core publishes
     reference rules only; tax advice, approval, optimization, suitability, reporting
     certification, and jurisdictional recommendations remain outside Core.
166. `ClientIncomeNeedsSchedule:v1`, `LiquidityReserveRequirement:v1`, and
     `PlannedWithdrawalSchedule:v1` form one QCP-owned `client_liquidity_evidence` capability. Keep
     separate API contracts, immutable records, selection predicates, ordering, lifecycle filters,
     supportability reasons, and source identity while sharing mandate resolution, runtime evidence,
     the source-reader port, and SQL adapter. Do not restore Query Service DTOs, response modules,
     mappers, ORM repository methods, facade methods, or output-shape exceptions. Core owns captured
     source facts only; financial planning, suitability, funding recommendations, treasury
     instructions, OMS acknowledgement, and downstream DPM decisions remain outside Core.
167. External currency exposure, hedge policy, eligible hedge instrument, FX forward curve, hedge
     execution readiness, and OMS acknowledgement contracts form one QCP-owned
     `external_hedge_posture` capability while their sources remain un-ingested. Keep each product's
     request/response contract, missing families, blocked capabilities, source system, fingerprint,
     lineage, and unavailable reason explicit. Use the effective-mandate port only for
     portfolio-scoped identity and do not invent an external repository, client, adapter, domain
     record, or deployment boundary before governed source ingestion exists. Do not restore the
     deleted Query Service DTO/service/facade paths. Forward pricing, exposure calculation, hedge
     advice or approval, suitability, counterparty selection, order generation/routing, best
     execution, OMS acknowledgement, fills, settlement, and autonomous action remain non-claims.
168. `TransactionCostCurve:v1` and `PerformanceComponentEconomics:v1` form one QCP-owned
     `transaction_economics` capability. Public contracts live under QCP `app/contracts`; frozen
     booked-transaction, cashflow, and cost-component evidence records live under `app/domain`; the
     application package owns keyset paging, fee-component identity, row mapping, component totals,
     supportability, and response assembly; `TransactionEconomicsReader` is the source port; and
     `SqlAlchemyTransactionEconomicsReader` owns grouped keys, bounded evidence reads, latest
     cashflow-epoch selection, and ORM mapping. Do not restore the deleted Query Service DTOs,
     facade methods, economics services, read records, or repository methods. Runtime metadata must
     use an injected UTC clock and source-owned deterministic SHA-256 content hash, digest,
     fingerprint, source reference, lineage, and current freshness derived from durable evidence.
     Core publishes observed cost and transaction component evidence only; market-impact prediction,
     execution quality, best execution, contribution/attribution calculation, performance returns,
     and tax advice remain explicit non-claims.
169. `DpmModelPortfolioTarget:v1`, `DiscretionaryMandateBinding:v1`,
     `InstrumentEligibilityProfile:v1`, `PortfolioTaxLotWindow:v1`,
     `MarketDataCoverageWindow:v1`, and `DpmSourceReadiness:v1` form one QCP-owned
     `dpm_source_readiness` capability. Keep public contracts, constituent and aggregate policies,
     immutable source evidence, source ports, deterministic effective-date/latest-observation/
     keyset SQL, continuation-token scope, and dependency composition under QCP. Do not restore
     Query Service DTOs, mappers, read records, repository methods, facade methods, or policy
     modules. Runtime metadata uses an injected UTC clock and deterministic SHA-256 source proof;
     aggregate `CURRENT` requires all five source families to be `READY` and durable constituent
     evidence time. Preserve fail-closed precedence and keep mandate approval, suitability,
     valuation, tax advice, liquidity analysis, execution quality, best execution, and OMS
     acknowledgement outside this readiness product.
170. Dependency-health proof uses a content-addressed ignored environment under
     `.cache/dependency-health`. Its SHA-256 identity covers Python implementation/version,
     platform, invoking pip version, root/service packaging manifests, dependency/test/tooling
     inputs, and cache implementation files. Reuse requires an exact marker, existing interpreter,
     and successful `pip check`; failed or corrupt staging never receives a success marker.
     `make verify-dependencies` is the reusable feature/PR path, while
     `make verify-dependencies-clean` is the mandatory main/scheduled clean-install path. Keep the
     clean-install and audit JSON reports separate under `output/dependency-health/` so cache reuse
     cannot overwrite clean proof. Do not add a cache input without extending deterministic
     invalidation tests and the CI cache key.
171. Required external Docker images for compose-backed tests use
     `DockerImagePullPolicy`: three attempts, explicit 120-second subprocess timeout, exponential
     backoff with bounded jitter, retryable timeout/rate-limit/transient-registry classification,
     bounded retry for unknown/empty failures, explicit permanent-marker fail-fast behavior, and
     source-safe diagnostics. Do not expose raw pull stderr, registry tokens, or authentication
     URLs. GitHub matrix cells have isolated Docker daemons;
     retain per-cell bounded acquisition unless a governed registry mirror or runner-level
     immutable image cache provides truthful shared evidence.
172. Canonical cashflow amount, fee, sign, timing, level, transfer, income, synthetic-flow, and
     corporate-action duplicate-flow semantics live in
     `portfolio_transaction_processing_service.app.domain.cashflow.calculation`. The policy consumes
     `BookedTransaction` plus immutable `CashflowRule` and returns `CalculatedCashflow`; it must not
     import event DTOs, SQLAlchemy models/sessions, repositories, metrics, logging adapters, or
     infrastructure packages. Event mapping and observability remain in infrastructure, while the
     cashflow repository maps calculated results to existing SQLAlchemy rows. The retired
     event-to-ORM `CashflowCalculator` facade must not return: framework callers map once to
     `BookedTransaction`, application coordination invokes domain policy, and persistence maps the
     domain result at its adapter boundary. Domain monitoring imports are rejected by the global
     in-process boundary guard.
173. Canonical INTEREST net and settlement-cash semantics live in
     `portfolio_transaction_processing_service.app.domain.transaction.settlement.interest`.
     `net_interest_amount` means gross interest less withholding tax and other interest deductions,
     before separately reported transaction fees. Income settlement subtracts the resolved fee;
     expense settlement adds it; cashflow sign then represents inflow or outflow. Validation,
     generated settlement legs, and cashflow materialization must consume this one policy so
     equivalent explicit and derived net-interest inputs remain invariant. Preserve the stable
     `INTEREST_015_NET_RECONCILIATION_MISMATCH` reason code. For current newly claimed or repair
     deliveries, reject a mismatched explicit net after idempotency classification and before
     financial work; do not let a supplied net override gross-less-deductions economics. Only the
     explicit historical-rebuild context may reproduce a previously accepted mismatch. Keep the
     independent Decimal golden vectors in the governed INTEREST contract when extending this
     methodology.
     The governed transaction-economics oracle now also includes the DIVIDEND settlement pack at
     `tests/fixtures/transaction_economics/dividend_settlement.v1.json`, with an independent
     Decimal-only evaluator and cross-layer warning-strict conformance tests. This bounded evidence
     covers currently supported gross-minus-fee DIVIDEND settlement, settlement/payment-date
     cashflow with canonical `EOD` timing, vector-fee-neutral trade/local cost basis, and zero
     trade/local P&L impact only; withholding tax, return of capital, basis reduction, and broader
     timing policy remain open under #448 and are not promoted by the pack.
174. Canonical ordinary signed settlement cash lives in
     `portfolio_transaction_processing_service.app.domain.transaction.settlement.cash_movement`.
     Resolve component fees before aggregate `trade_fee`; BUY and INTEREST expense include the fee
     in an outflow, while SELL, DIVIDEND, and INTEREST income subtract it from available proceeds.
     The three inflow families must remain strictly positive before direction is applied. Open the
     combined unit of work and classify physical and semantic idempotency first so harmless
     historical duplicates remain acknowledgements. Reject a newly claimed or repair delivery with
     a zero or negative result before cost, position, cashflow, or commit, preserve the stable family
     reason code as a bounded non-retryable application rejection, and roll back the uncommitted
     claim. Never use absolute-value normalization to manufacture an inflow. Generated cash legs,
     product cashflows, validators, adapters, and independent Decimal golden vectors must consume or
     prove this one policy. BUY, FEE, FX, ADJUSTMENT, and corporate-action cash retain their
     documented family-specific representations; do not broaden this rule without a separate domain
     decision.
     Preserve bounded application reason codes through Kafka DLQ and operations-API evidence. The
     current DIVIDEND available-proceeds input remains booked gross amount pending net-dividend,
     withholding, and return-of-capital work under #448. FX does not use this generic arithmetic:
     its phase-1 policy rejects non-zero embedded fees and represents supported charges as separate
     linked `FEE`/`TAX` postings under the FX domain rule below.
175. Corporate-action Bundle A validation and basis reconciliation are owned by
     `portfolio_transaction_processing_service.app.domain.transaction.corporate_action` and
     `.domain.cost_basis.corporate_action_reconciliation` over immutable `BookedTransaction`.
     Deterministic run/finding assembly and per-batch group coordination belong in the application
     coordinator behind typed repository and observer ports. ORM mapping and evidence persistence
     belong in the SQLAlchemy repository adapter; metrics and logs belong in the observer adapter
     and run only after persistence succeeds. Do not restore the retired
     `portfolio_common.ca_bundle_a_validation`, `ca_bundle_a_reconciliation`, or reason-code facades.
     This is design modularity inside the unified transaction-processing deployable, not a new
     runtime service. Issues #450, #480, and #481 retain partial-allocation, parent-event graph, and
     lot-lineage closure.
176. Transaction and product lifecycle publication is governed by
     `contracts/transaction-processing/transaction-capability-catalog.v1.json`, refreshed with
     `python scripts/transaction_processing/generate_capability_catalog.py`, and blocked by
     `make transaction-capability-catalog-guard`. Every canonical transaction code must appear once
     with registry-exact lifecycle, economic-role, support, and production-booking posture. Limited,
     default-strategy, migration-only, and target-not-implemented codes require issue ownership.
     Generic `BUY`, `SELL`, `INTEREST`, or `DIVIDEND` support must never be presented as complete
     product-specific maturity, exercise, barrier, payoff, commitment, return-of-capital, or
     correction lifecycle support.
177. Domain-specific automation belongs under a domain-owned `scripts/<domain>/` package, mirrored
     under `tests/unit/scripts/<domain>/`; generic `quality/` and `generators/` directories are not
     ownership buckets. Transaction-processing capability generation and validation live under
     `scripts/transaction_processing/`. Keep implementation filenames action-oriented and avoid
     repeating the full parent-domain name in every file.
178. `portfolio_common.domain.transaction.type_registry` is the sole transaction-code vocabulary owner.
     Do not add service-local transaction enums or repeat generic registry projections. Strategy
     maps may bind canonical string codes to owned behavior; reusable classification selectors
     belong beside the registry. Local sets are acceptable only for explicit domain policy such as
     ordering, same-instrument quantity treatment, generated-leg behavior, or basis transfer, and
     must have registry-conformance tests plus a documented reason they are not generic metadata.
179. Corporate-action basis-transfer classification and linked-leg ordering are owned by
     `portfolio_transaction_processing_service.app.domain.transaction.corporate_action`.
     Cost-basis and position-history ordering consume that policy over explicit transaction model
     fields. Do not restore `portfolio_common.ca_bundle_a_constants`,
     `portfolio_common.ca_bundle_a_ordering`, or the unused
     `portfolio_common.events.transaction_event_ordering_key`. Shared event models own payload and
     boundary normalization, not calculation replay ordering.
180. Foreign-exchange validation, linkage, contract-instrument construction, baseline P&L policy,
     reason codes, and models are owned by
     `portfolio_transaction_processing_service.app.domain.transaction.fx`. Effective processing
     type selection is owned by the parent transaction domain and is shared by cost, cashflow, and
     position policies in-process. Do not restore `portfolio_common.transaction_domain` or import
     service-owned FX policy through a shared compatibility facade. FX canonical values are
     immutable and framework-independent; do not reintroduce Pydantic, event-envelope, ORM, or
     transport models into the domain package. Resolve optional FX fee evidence inside canonical
     construction without widening the required source protocol. Phase-1 FX fee/tax policy is
     separate linked `FEE`/`TAX` posting: reject every non-zero resolved inline fee with
     `FX_025_NON_ZERO_EMBEDDED_FEE` before booking, cost-basis mutation, or cashflow sign
     normalization. Preserve absent/zero inline fees and require separate charges to retain the FX
     `economic_event_id` and `linked_transaction_group_id`; never infer fee currency or charged leg
     from the transaction `currency` field.
181. Framework-independent transaction vocabulary and policies shared by multiple Core boundaries
     belong under `portfolio_common.domain.transaction`, with tests mirroring that package path.
     Do not add new transaction modules to the `portfolio_common` root. Migration re-exports must
     be bounded to one active sequence, explicitly named transitional, and deleted with retired-path
     guards once consumers move. Keep calculation policy owned by one service, such as cost basis,
     position, cashflow, settlement, FX P&L, or corporate-action reconciliation, in that service's
     domain package; shared placement requires demonstrated cross-boundary ownership rather than
     convenience.
182. Framework-independent market-data policies shared by valuation, reconciliation, and
     aggregation belong under `portfolio_common.domain.market_data`, with singular domain modules
     such as `fx_rate`, `market_price`, and `valuation_unit_price` and tests mirroring that package.
     Do not restore flat `portfolio_common.fx_rates`, `market_prices`, or `valuation_prices` roots.
     Product-specific quote conventions and valuation methodology require an explicit governed
     domain decision; the current legacy bond quote heuristic remains tracked under #451 and must
     not be generalized during structural moves.
183. Timeseries instrument/FX records shared by generation and aggregation belong under
     `portfolio_common.domain.market_data.timeseries`. The SQL reader remains shared infrastructure
     because both service-owned repositories reuse it. `TimeseriesMarketDataPort` belongs under
     `portfolio_derived_state_service.app.ports.timeseries_market_data` because portfolio aggregation
     is its only application consumer; shared records or adapters do not justify a shared port.
     Keep generation and aggregation persistence service-owned, and keep #714 open until measured
     daily-volume, backfill, fan-in, recovery, isolation, rollback, and SLO evidence certifies the
     consolidated runtime.
     Position-timeseries Kafka delivery is a transport adapter only. Map
     `DailyPositionSnapshotPersistedEvent` into the framework-neutral command under
     `portfolio_derived_state_service.app.application.position_timeseries`; keep current-day and
     bounded backdated materialization in that application package, immutable records and pure
     calculation policy under `app.domain.position_timeseries`, persistence contracts under
     `app.ports`, and SQLAlchemy transaction/ORM/job-staging behavior under `app.infrastructure`.
     Do not restore the ambiguous `app.core` package or flat `app.domain.timeseries_records` module.
     Treat the persisted snapshot as authoritative and fail
     closed before writes when repeated trigger portfolio, security, date, or epoch identity differs.
     Keep the portfolio-timeseries stage separate as a testable module while #714 consolidates the
     runtime; do not move either workflow into Kafka consumers or `portfolio_common`.
     Portfolio aggregation delivery follows the same rule: claim durable jobs with lease owner,
     token, and UTC expiry; map each claim into `MaterializePortfolioTimeseries`; coordinate fan-in
     and typed queue outcomes through application ports; and compose output plus
     completion/reconciliation outbox evidence through one infrastructure unit of work. Terminal
     writes require job id plus lease token. Required instrument and FX reference data is fail-closed;
     never skip a position contribution and publish an incomplete portfolio aggregate.
     Resolve batched instrument data and cached positive FX rates in
     `app.application.portfolio_timeseries.CalculatePortfolioTimeseries`; keep synchronous
     portfolio-currency arithmetic in the pure
     `app.domain.portfolio_timeseries.calculate_portfolio_timeseries` function. Reject missing
     portfolio/instrument currencies, blank portfolio identity, cross-portfolio contributions,
     future-dated or future-epoch contributions, duplicate normalized security contributions, and
     non-positive FX before persistence. Prior-date and prior-epoch rows are valid when selected by
     the repository's latest-state-at-or-before target-window query. Do not restore
     `app/core/portfolio_timeseries_logic.py` or the empty `app/repositories` compatibility package.
184. Cost-basis lot behavior belongs under `app/domain/cost_basis/lot_behavior.py`. Deterministic
     AVCO rebuild planning belongs under `app/application/cost_basis_processing`. Upstream linked
     cash-leg resolution and pairing belongs under `app/application/settlement_processing` and uses
     the narrow `ports/settlement/transaction_lookup.py` contract. Both operate on canonical booked
     transactions through ports. Open-lot persistence scope and FIFO/AVCO checkpoint decisions also
     belong in the cost-basis application package; concrete SQL persistence remains infrastructure.
     SQL-backed AVCO reconciliation belongs under `app/infrastructure/cost_basis`. Mirror these
     packages in tests. Pure cost-basis calculation policy tests belong under
     `tests/unit/services/portfolio_transaction_processing_service/domain/cost_basis/calculation`;
     do not restore calculator, strategy, disposition, parser, ordering, engine-input, error,
     source-allocation, or property-invariant suites to the generic `tests/.../cost` root.
     Do not return these responsibilities to an infrastructure workflow, create flat compatibility
     modules, or place application behavior in infrastructure.
     Generated settlement cash-leg validation, creation, ordered persistence, and product-leg
     linking belong in `app/application/settlement_processing/cash_leg_linking.py` over the narrow
     settlement lookup and persistence ports. Processed transaction and FX-contract instrument
     effects cross `ports/cost_basis/effect_staging.py` as domain values; governed event mapping,
     topic selection, payload serialization, BUY/SELL outbox metrics, and transactional outbox writes
     belong in `app/infrastructure/cost_basis/effect_staging.py`. Corporate-action reconciliation
     persistence remains an infrastructure concern.
     Validated FX transaction persistence and optional synthetic contract-instrument derivation
     belong in `app/application/foreign_exchange_processing/booking.py` over the narrow foreign-
     exchange persistence port. Baseline FX economics and validation remain domain policy under
     `app/domain/transaction/fx`; governed transaction/instrument event mapping remains infrastructure.
     Cost-basis timeline orchestration belongs at
     `app/application/cost_basis_processing/timeline.py`. Average-cost-pool reconciliation must use
     the same explicit capability name under `domain/cost_basis`, `ports/cost_basis`,
     `application/cost_basis_processing`, and `infrastructure/cost_basis`; do not restore flat
     application/port modules or a vague domain `reconciliation.py`.
     Cost-basis observation protocols belong under `app/ports/cost_basis/observability.py`;
     Prometheus instruments and their adapter belong under `app/infrastructure/cost_basis` as
     `metrics.py` and `observability.py`. Preserve the existing metric contracts while keeping
     framework dependencies outside domain and application code. Ordered-append/full-rebuild mode
     and restored-open-lot counts must cross the typed calculation observer; application or workflow
     code must not import Prometheus counters or histograms directly.
     Corporate-action basis-reconciliation metrics and support logs use the same cost-basis
     infrastructure ownership through `corporate_action_observability.py`; keep its observer port in
     application-facing contracts and contain telemetry failures outside domain policy.
     Calculated transaction-cost persistence belongs in
     `app/application/cost_basis_processing/transaction_persistence.py`: it accepts domain
     transactions and persistence ports, writes only the affected deterministic suffix, and returns
     immutable `BookedTransaction` values. Event DTO mapping and transactional outbox staging remain
     behind the domain-valued effect-staging port and infrastructure adapter. Persistence lifecycle
     observations use typed stage/status records;
     the Prometheus/log adapter must contain telemetry failures so support tooling cannot roll back
     financial writes. Mirror persistence tests under the application package and do not test this
     behavior through private orchestration methods.
     Incremental-versus-full-rebuild selection, compatible FIFO/AVCO checkpoint restoration, FX
     enrichment, and timeline execution belong in
     `app/application/cost_basis_processing/calculation.py` over `BookedTransaction` and cost-basis
     ports. `PreparedCostProcessingUseCase` must acquire the key lock before invoking that
     coordinator; infrastructure must not reintroduce calculation policy or framework event DTOs
     into the application package.
185. `make ci-local` must not run the complete unit or integration-lite corpus twice solely to
     collect different evidence. `scripts/quality/coverage_gate.py` owns the local unit execution,
     enforces the zero-warning budget through `warning_budget_gate.run_suite_with_warning_budget`,
     collects unit and integration-lite coverage, and emits aggregate/critical-path reports.
     Hosted `CI_GATES` retains the standalone `warning-gate` for earlier failure isolation. Preserve
     this single-execution local contract with cross-platform command tests; do not mitigate Windows
     socket exhaustion with sleeps, retries, reduced test selection, or weakened warning/coverage
     thresholds.
186. Node-based quality gates must execute repository-owned tooling from a committed lockfile.
     OpenAPI Spectral tooling belongs under `tools/api_governance`; the Python gate installs it with
     `npm ci` in that directory and invokes only its local binary. Do not restore unversioned `npx`
     package resolution, global installs, or an unlocked transitive dependency graph. Compatibility
     overrides must be exact, tested on the governed Node runtime, security-audited, and removed when
     the upstream package contract is repaired and the clean lock can be upgraded safely.
187. Destructive E2E fault scenarios must own unconditional, idempotent recovery of every shared
     runtime dependency they stop. Reconcile Compose services with `up --detach --no-deps --wait`,
     prove backing-resource readiness, restart the governed dependent service set, and prove service
     readiness before returning control. Keep reusable lifecycle support under
     `tests/test_support/runtime` with mirrored unit tests. Preserve the original test failure when
     cleanup also fails, attaching cleanup diagnostics instead of replacing root-cause evidence.
188. A service/package/runtime migration is not integration-tested by successful collection alone.
     When repository, port, lease, transaction, or session contracts change, scan every migrated
     integration test for retired symbols and execute the focused suite against real PostgreSQL.
     Concurrency claimants and application unit-of-work providers must use independent sessions;
     retain immutable identifiers before rollback rather than reading expired ORM instances outside
     an async database context. Keep a unit-lane no-return guard when a removed facade can remain
     syntactically collectable.

189. Accepted effective-dated FX corrections are source-owned valuation triggers. Persistence must
     atomically stage the versioned persisted observation with normalized direct pair, effective
     date, observation identity, UTC generated time, deterministic content hash, and correlation
     evidence. Valuation orchestration must apply one temporal scheduling policy to price and FX
     observations. Backdated and future observations must record durable pair/date or instrument/date
     work before acknowledgement. Current-business-date observations must queue currently visible
     positions without durable replay; positions created later are covered by the transaction-owned
     valuation-readiness fact and read the already committed source observation. Select only
     positions whose instrument and portfolio currencies match the direct pair, and fail closed for
     unsupported inverse or triangulated paths. Coalescing preserves the
     earliest impacted date independently from the newest deterministic source-lineage tuple; never
     let database conflict arrival order select lineage. A direct pair with no affected positions
     may retry a bounded visibility race, but must complete as an observable no-op at the configured
     attempt limit rather than spin in `PENDING`. Use
     `make profile-derived-state-fx-restatement` to prove exact affected rows, corrected market
     value, unrealized price/FX/total P&L, exactly-once observation/replay counts, closed queues,
     reconciliation, and resource evidence. A price-restatement profile is not FX proof.
     The certifying FX profile must commit the correction while valuation orchestration is stopped,
     restore the service unconditionally, and prove the recovered result from durable evidence.
     Record measured stop/healthy-restore UTC timestamps and outage duration; a requested-restart
     boolean is not recovery evidence.
     Certification artifacts must not persist credentialed database URLs or raw process
     configuration. Emit only a safe database target (backend, host, port, database), and run the
     synthetic-fixture leakage guard against generated evidence before retaining or sharing it.
190. Valuation scheduling and watermark contiguity must use the seeded
     `DEFAULT_BUSINESS_CALENDAR_CODE` date set, not calendar-day iteration. Resolve eligible dates
     once per scheduler batch and filter them per position; do not introduce a query per position.
     Calendar-day fallback is permitted only when the governed calendar is entirely empty. A newer
     authoritative valuation snapshot must refresh position-timeseries freshness and rearm
     portfolio aggregation even when instrument-local values are unchanged by portfolio-base FX.
     Compare source and materialization timestamps so duplicate delivery remains a no-op after the
     derived row catches up. Prove this with weekend/holiday, empty-calendar, PostgreSQL lifecycle,
     and exact FX-restatement tests.
191. Do not treat a current-date source observation with no visible position as a replay race.
     Transaction processing is the authoritative creator of later position valuation readiness, so
     current price and FX facts must not reset position epochs merely because reference data arrived
     first. Preserve durable replay for backdated/future observations and prove the distinction with
     domain policy tests plus workload event-amplification evidence. Immediate source-trigger
     repositories must compare the persisted source row's update time with the same-day valuation
     snapshot: queue missing/older snapshots, suppress notifications already reflected by a newer
     snapshot, and re-open work when a later correction updates the source row. A current-date
     source correction that arrives while the natural-key valuation job is `PROCESSING` must use
     the explicit source-correction requeue fence. Keep the active row `PROCESSING` until its owner
     reaches a terminal transition, then atomically return the row to `PENDING` under the newer
     source observation/content identity and make the stale owner skip snapshot/outbox side
     effects. Never compare transport `correlation_id` as correction identity: distinct accepted
     source observations may share correlation, and one source observation may be redelivered under
     a different trace. Each outbox-backed transaction-readiness event is also a source mutation:
     hash its durable `outbox_id` header to rearm `COMPLETE` work or fence a different mutation that
     arrives during `PROCESSING`. Redelivery of the same outbox event must remain non-disruptive,
     while headerless compatibility events retain the legacy non-rearming behavior. Never infer
     mutation identity from Kafka offset, trace, or correlation. Claim, stale-reset, and
     dispatch-recovery paths must clear a consumed fence without discarding a newer source mutation,
     including at the normal retry limit.
192. Correlation ids are diagnostic lineage, not authorization to replay completed work. Valuation
     scheduler, recovery, duplicate delivery, and headerless readiness paths must leave an existing
     `COMPLETE` same-scope job unchanged even when their correlation differs. A source correction
     may explicitly rearm completed valuation after source-owned freshness proves that the
     authoritative price or FX observation is newer than the materialized snapshot. A distinct
     outbox-backed transaction-readiness mutation may do the same because position/cash state has
     changed for that valuation scope. Preserve both identities in PostgreSQL conflict-lifecycle,
     consumer, duplicate-delivery, and workload evidence; do not infer replay intent from
     correlation inequality.
193. Transaction raw landing must resolve portfolio, instrument, and optional effective
     cash-account reference availability as one repository read before transaction upsert. Preserve
     portfolio visibility retry, provisional instrument/cash reference policy, idempotency, outbox,
     and event behavior. Do not reintroduce one existence query per reference family on the
     bank-day hot path; prove the one-read shape in repository tests and the behavior against
     PostgreSQL.
194. Transaction ingestion, raw persistence, and repair replay must use one shared partition-key
     policy. Unlinked transactions use `portfolio_id|security_id`. A non-blank
     `linked_transaction_group_id` uses
     `portfolio_id|transaction-group|linked_transaction_group_id`, scoped by portfolio, so a
     canonical parent-before-dependent-leg producer sequence cannot split across Kafka partitions.
     Dates and epochs remain outside both identities. This preserves same-position ordering and
     linked cross-security ordering while allowing independent securities to use governed capacity.
     Dependency references, deterministic domain ordering/rebuild, reconciliation, and
     portfolio-security database locks remain mandatory; do not restore portfolio-wide transport
     serialization or treat the group key as a substitute for those domain controls.
195. `transactions.raw.received` / `persistence_group_transactions` and
     `transactions.persisted` / `portfolio_transaction_processing_group` use twelve aligned
     partitions and in-flight tasks with `per_key_concurrency=1`. This is a measured
     transaction-only capacity decision: exact fan-in reduced drain `13.61%`, peak active database
     connections remained `11`, and lock/blocked peaks remained `2/2`. Do not change only one side
     of the topic/group contract, apply twelve as a global topic default, or increase beyond twelve
     without exact reconciliation plus pool, lock, lag, CPU, recovery, and daily-volume evidence.
     `market_prices.raw.received` / `persistence_group_market_prices` and
     `market_prices.persisted` / `valuation_orchestrator_group_price_events` also use twelve aligned
     partitions/in-flight tasks. This is a separate source-bootstrap decision: eight partitions
     placed five of ten canonical security series (`1,880/3,760` facts) on one ordered lane;
     twelve reduces the hottest lane to three series (`1,128` facts), or `40%` less serial work.
     Preserve the `security_id` key, pinned CRC32 partitioner, and per-partition serialization.
196. Cost-basis processing and AVCO rebuild must resolve portfolio policy and optional instrument
     facts through one typed application-port bundle and one repository statement. Preserve the
     distinct missing-portfolio retry and missing-instrument preparation/rebuild behavior. Do not
     restore one database round trip per reference owner on the transaction-processing hot path;
     prove the one-statement shape against real PostgreSQL as well as port-level behavior.
197. Bank-day workload artifacts must record the emitting checkout's exact Git revision and a
     non-sensitive `source_tree_state` of `clean`, `dirty`, or `unavailable` when repository metadata
     can be resolved. Never retain changed file names, Git command output, credentials, or raw
     process configuration in the artifact. Source provenance improves reproducibility but does not
     promote local evidence to trusted CI, deployment, or production certification.
198. Position-state acquisition must use the conflict-aware insert result as the authoritative
     newly-created state and perform a fallback read only when another transaction already owns the
     natural key. Preserve one state row per portfolio/security/account boundary, caller-owned
     transaction semantics, and the conflict fallback. Guard the absent-key path with a real
     PostgreSQL statement-shape test; do not restore an unconditional post-insert reread.
199. Cost persistence may skip the complete opening-lot snapshot reread only when the complete cost
     timeline contains exactly one initial opening transaction. Continue to write the AVCO pool
     checkpoint, and retain complete-snapshot reconstruction for existing, backdated, correction,
     reversal, restatement, and other rebuilt timelines. Keep this scope explicit in the application
     port rather than inferring it inside the repository adapter.
200. A direct statement-count reduction is sufficient to retain a simpler hot-path ownership shape,
     but not to claim end-to-end throughput. Require an exact clean fan-in comparison before spending
     another two-hour daily run; if fan-in is neutral or slower, record the result and pause further
     query-level micro-optimization until timing or equivalent stage evidence identifies a material
     bottleneck.
201. Governed bank-day evidence must scrape the combined transaction-processing runtime before
     teardown and retain bounded operation counts, duration observation counts, cumulative duration,
     and mean duration by stage/outcome. Never add business identifiers to these metrics or artifacts.
     Treat missing samples as a certifying failure and treat cumulative/mean values as bottleneck
     attribution rather than latency percentiles or SLOs. Also retain existing bounded cost execution
     mode/method counts, recalculation duration/depth, and restored-open-lot statistics so calculator
     work can be separated from the wider cost stage before changing persistence or coordination.
     Current exact fan-in evidence attributes only about `0.16s` of `194s` wider cost-stage time to
     FIFO calculation across 1,000 opening transactions. Do not optimize calculator arithmetic from
     the aggregate cost-stage label; obtain database, persistence, or coordination evidence first.
     The same certifying artifact must retain the existing low-cardinality
     `db_operation_latency_seconds` count, sum, and mean by repository/method, deterministically
     sorted and without query text or business identifiers. Treat missing, incomplete, or
     zero-observation series as absent evidence. Current exact evidence attributes `139.978303s`
     across eleven repository operations while FIFO arithmetic remains `0.152853s`; use the
     repository series to choose targeted statement or coordination proof, not as permission to
     collapse domain locks or transaction boundaries.
202. A `COMPLETE` valuation job and its portfolio/security/date/epoch snapshot are one atomic unit
     of work. When a governed workload has all expected transactions durable, no pending or
     processing valuation work, and an empty outbox, a completed job without its matching snapshot
     is irrecoverable terminal evidence rather than normal lag. Fail fast with the exact count,
     preserve worker ownership logs, attempt counts, processed-event fences, and Kafka lag, and do
     not raise the timeout or claim capacity. Diagnose the ownership path before changing valuation
     semantics; an isolated successful repository probe is not sufficient runtime proof. Exact run
     `20260717T180631Z` reproduced the contradiction for all 1,000 jobs at a clean signed SHA after
     a prior exact run converged, so treat the defect as nondeterministic and reproducible until the
     worker transition has targeted concurrency proof. Signed `45295cf24` now classifies the
     internal transition as `TERMINAL_APPLIED`, `REQUEUED`, or `NOT_OWNED`, gates all completion
     side effects on the first outcome, and fails closed on an unsupported applied status. Exact
     clean fan-in runs `20260717T193156Z` and `20260717T194013Z` then reconciled all `1,000` rows
     with zero requeue/lost-ownership suppression warnings; the repeat drained in `95.645s` with
     exactly one aggregation completion. Treat this as bounded ownership-observability and repeat
     evidence, not as a substitute for daily, recovery, poison, duplicate, correction, or
     restatement certification.
203. Inside the unified transaction-processing unit of work, cashflow may reuse a position epoch
     only when position materialization conditionally rearmed generation for that exact expected
     epoch through the position-state `UPDATE`. A successful compare-and-set holds the state-row
     write lock until the caller-owned commit, so the proven epoch is safe for the same transaction
     and position key. A concurrently advanced epoch affects zero rows and must fall back to the
     database-backed `EpochFencer`, as must no-record, stale, coalesced, and other unsuccessful-
     rearm paths. Do not reuse a pre-update epoch merely because a later write touched the row, or
     cache an epoch across unit-of-work boundaries; both weaken correction and concurrent-
     reprocessing fences.
204. Position valuation and financial reconciliation share only the framework-independent valuation
     vocabulary, immutable values, deterministic calculation policy, and assignment-resolution
     contract under `portfolio_common.domain.valuation`. This is a bounded cross-deployable domain
     contract, not permission to put valuation workflow in `portfolio_common`. Ingestion DTOs,
     assignment persistence, approval/migration workflow, impact preview, replay scheduling, caches,
     Kafka/HTTP adapters, and orchestration stay with their owning services. Runtime wiring must
     demonstrate both production consumers; otherwise move single-consumer policy into the owning
     service domain. Explicit quote representation, principal basis, accrued treatment, scaling,
     and FX direction must replace the legacy bond price-magnitude/cost-basis heuristic—never sit
     beside it as a hidden fallback.
205. Valuation day-count policy resolves an exact governed convention code and version; unknown
     conventions and versions fail closed. `ACT/365.FIXED` and `ACT/360` use actual elapsed calendar
     days with their fixed denominators. `BUS/252` requires a source-owned, versioned business-day
     calendar whose declared validity covers the calculation interval and counts supplied business
     dates start-inclusive/end-exclusive. Never replace missing calendar evidence with weekday or
     process-local holiday assumptions. Keep `30/360.US`, `30E/360`, and `30E/360.ISDA` distinct:
     U.S. basis applies the governed February/31st sequence, Eurobond basis adjusts 31st dates, and
     ISDA basis requires the contractual termination date to apply its February exception.
     `ACT/ACT.ISDA` splits elapsed days by the applicable calendar-year denominator.
     `ACT/ACT.ICMA` requires source-owned regular or quasi-coupon reference periods and contractual
     frequency whose overlap covers the calculation interval exactly once; do not generate missing
     reference periods or infer frequency from broad product type. Regular and short/long stub
     calculations use the same explicit overlap rule.
206. Gross contractual accrued income is the sum of contiguous source-owned segments' signed
     accrual principal multiplied by supplied annual effective rate and governed year fraction.
     Segment whenever principal or the fixed/supplied-floating all-in rate changes; require separate
     rate, principal, and schedule lineage; reject gaps, overlaps, mixed currencies, non-finite
     values, or unsupported day counts. Do not divide annual rate by coupon frequency, derive a
     floating reset, or silently apply tax, default/non-accrual, PIK, inflation, compounding, or
     rounding policy. Day-count and accrual kernels use a fixed 50-digit local Decimal
     precision; rounding belongs to an explicit persistence/API boundary. Runtime integration must
     bulk-resolve source facts and prove mixed-book capacity—domain microbenchmarks alone are not
     release evidence. Zero-coupon/stripped discount positions use a named no-periodic-accrual
     clean-price policy for the applicable principal basis. Do not run them through coupon accrual
     or infer discount accretion, effective-interest accounting, tax amortization, or yield from
     clean price.
     Ex-coupon settlement requires a separately assigned treatment plus a source-owned entitlement
     carrying the ex-date, next coupon payment date, and complete full-coupon segments. Require
     settlement strictly after the ex-date and before payment, prove the elapsed segments are an
     economic prefix of the full coupon, and calculate signed settlement accrual as elapsed gross
     accrual minus the full signed coupon. Preserve gross accrual, entitlement adjustment, and
     settlement accrual as separate outputs and lineage facts. Never infer an ex-period from product
     class, market, settlement cycle, or a process-local calendar.
207. Financial calculation lineage has three deterministic layers: canonical normalized input
     content, algorithm/version/precision-bound calculation identity, and output values bound to
     that calculation identity. Use separate lowercase SHA-256 hashes for all three. Prohibit
     binary floats, non-finite Decimal values, naive timestamps, ambiguous mapping keys, and
     unsupported objects from lineage payloads; normalize aware timestamps to UTC before hashing so
     equivalent instants cannot create false revisions. Persist and expose policy/assignment/source
     references with the hashes; correlation and trace IDs are operational request evidence, not a
     substitute for financial input, calculation, or output lineage. Source references used by a
     calculation carry source-record identity/revision, source-content hash, and aware observation
     time. Precompute immutable reference-data content hashes, such as a business-calendar digest,
     when constructing or loading the value object; bind that digest on the high-volume calculation
     path instead of repeatedly serializing the complete reference dataset. Position-valuation
     lineage binds the exact policy and assignment plus only the price/value, currency,
     position/principal/factor, multiplier, accrued-income, and FX evidence that policy consumes.
     When accrued income is calculated separately, bind its calculation lineage as a derived input
     rather than relabeling it as a source record. Run position scaling, aggregation, and FX
     conversion in the governed 50-digit local Decimal context; the returned reporting values and
     output hash must use those same intermediates.
208. Repository-native Python quality evidence is valid only when the active interpreter's tool
     version exactly matches `requirements/ci-tooling.lock.txt`. Route module-backed Ruff, MyPy,
     Bandit, Vulture, Deptry, Xenon, Radon, Interrogate, and pip-audit commands through
     `scripts/quality/ci_tooling.py`; verify import-linter and other embedded tools before importing
     them. Missing, ranged, duplicate, or mismatched pins fail with the repository bootstrap
     remediation. Build subprocess argument lists and reuse the current interpreter; do not create
     shell strings, separate terminal windows, global-tool assumptions, or a second version source.
     Quality Baseline workflow jobs must install from the same lock even when a step remains
     report-only. Tool-version changes require an intentional lock update and the workflow/tooling
     contract tests; they must not alter application runtime dependencies or lint rules implicitly.
209. The root pytest session owns the module-level `PreparedTestRuntime` reservation independently
     of Docker fixture selection. Release still-held host-port sockets from `pytest_sessionfinish`;
     make `docker_services` use the same idempotent release path before project-scoped Compose
     teardown. Unit-only, collection-only, fixture-failure, and Docker-backed sessions must not
     depend on interpreter finalization for socket cleanup. Preserve held-port protection until
     Compose is ready to bind, and do not weaken collision resistance by releasing reservations at
     collection time.
210. Asset-allocation contributor lineage is owned by Query Service source mapping and the shared
     framework-independent allocation kernel. Every direct contribution binds portfolio, booked
     security, and exact position snapshot; every decomposed contribution additionally binds the
     component security to its booked parent and exact component record, effective interval,
     weight, and available upstream source reference. Bucket totals include every contribution,
     while response rows are bounded by `contributor_limit_per_bucket`; returned values plus the
     signed omitted residual must reconcile exactly. Preserve deterministic descending-absolute-
     value/source-identity ordering and the established 28-digit allocation-weight precision.
     Publish normalized-input, algorithm/version/precision, and output hashes from the cross-domain
     financial calculation-lineage primitive. Reporting workflow, DTOs, repository reads, and
     OpenAPI stay in Query Service; do not move them into `portfolio_common` or ask downstream
     consumers to reconstruct discarded look-through lineage from holdings.
211. Cashflow operational reads publish product-owned trust receipts rather than claiming current
     evidence from successful serialization alone. `PortfolioCashflowProjection:v1` reconciles
     SQL-owned booked/projected totals to its 50-digit Decimal accumulation;
     `PortfolioCashMovementSummary:v1` reconciles SQL source-row count and per-currency totals to
     returned buckets and never nets unlike currencies. Both bind tenant, bounded request scope,
     exact source rows/controls, algorithm/version/precision, and returned values through separate
     input, calculation, and output SHA-256 hashes. A zero-row source window is explicitly
     `COMPLETE`, `SUPPORTED`, `EMPTY_SOURCE_WINDOW` with no invented evidence timestamp. Populated
     windows missing a timestamp or mismatching a count/total fail closed as `BLOCKED` and
     `UNAVAILABLE`. Keep the narrow shared cashflow-window trust policy in Query Service; do not
     move cashflow workflow or product calculations into `portfolio_common`, and do not treat
     correlation ids as financial lineage.
212. `PortfolioStateSnapshot:v1` is a QCP-owned portfolio-state calculation receipt. Extract exact
     business-date/epoch scopes from the selected snapshot or history rows and read all matching
     `FINANCIAL_RECONCILIATION` controls in one set-based adapter query. Missing, in-flight, failed,
     unknown, or source-older controls fail closed; successful response construction is not proof
     of reconciliation. Bind portfolio, tenant, as-of date, mode, current restatement version,
     normalized request, selected position/instrument source facts, scope/control hashes,
     governance policy, valuation context, and simulation session version in input lineage. Bind
     `PORTFOLIO_STATE_SNAPSHOT`, algorithm version, and 28-digit intermediate precision in
     calculation lineage, and enforce that precision with local Decimal contexts across totals,
     weights, deltas, projected quantity/value scaling, and price/FX valuation; bind returned
     sections and trust posture in output lineage. Derive the deterministic snapshot id from the
     output hash. Generation time and correlation ids remain operational evidence and must not alter
     identity. Keep the DTO/workflow/source extraction in QCP; share only framework-independent
     reconciliation and calculation-lineage primitives.
213. App-local Compose must start every worker-capable service through the same owned runtime entry
     point as its Dockerfile. Do not override `financial_reconciliation_service` with the pure HTTP
     `app.main` application: `app.runtime` owns the reconciliation-request consumer, outbox
     dispatcher, and supervised HTTP server. Compose must declare Kafka topic creation as a
     dependency and use the internal `kafka:9093` bootstrap address. Health-only HTTP startup is not
     evidence that the service's owned consumer is running; stack contract tests must bind the
     command, Kafka address, and dependency set so canonical holdings cannot remain silently
     `UNRECONCILED` after aggregation completes.
214. Authoritative instrument valuation-policy history is resolved through the position-valuation
     service's application port and SQLAlchemy adapter. Rank the latest correction for each exact
     tenant/legal-book/instrument/source-system/source-record identity before filtering ACTIVE
     lifecycle and inclusive effective dates; then use the framework-independent assignment domain
     to reject gaps/overlaps and the exact-version policy registry to reject unsupported authority.
     Do not move SQLAlchemy selection into `portfolio_common`, infer legal book from booking centre,
     revive an older ACTIVE row after a later suspension/retirement, or fall back to product type.
     The current single-scope resolver is a migration primitive, not approval for per-position N+1
     reads: production cutover requires authoritative portfolio scope, complete valuation facts,
     bulk/cache invalidation proof, both valuation/reconciliation consumers, heuristic deletion, and
     exact-SHA mixed-book capacity evidence under #788.
215. Portfolio aggregation claim generation is the authoritative processing sequence for
     reconciliation within one portfolio/business-date/epoch scope. Preserve the positive durable
     `portfolio_aggregation_jobs.attempt_count` as `aggregation_revision` through aggregation
     completion, reconciliation request/run/completion, control evidence, and support APIs. New
     automatic runs dedupe per reconciliation type plus portfolio/date/epoch/revision; legacy
     revision `0` retains its prior key. Only a higher revision may replace same-epoch control
     status; older and identical revisions are no-ops, and contradictory outcomes for one revision
     fail closed. Do not substitute Kafka arrival order, timestamps, debounce, or severity merging
     for this database-backed generation.
216. Canonical repair replay load gates issue requests that intentionally complete the unified
     financial flow. Their request-count threshold must use the incremental
     `stage="transaction",outcome="processed"` count. A global `transaction/duplicate` count cannot
     satisfy that threshold because unrelated at-least-once redelivery could mask a missing repair;
     duplicate evidence is valid only when the gate is explicitly testing ordinary duplicate
     delivery or can correlate the evidence to each issued request. Preserve the governed replay
     volume and timeout, and use heavy PR/main runtime lanes to prove the drain. Concurrent Kafka
     consumers must retain the configured idle
     poll timeout while bounding polls to 100 milliseconds whenever processing tasks are active;
     otherwise a paused busy partition can add the full idle timeout between ordered messages even
     after the prior task completed. This scheduling rule does not relax per-partition ordering,
     in-flight capacity, retry, or offset-commit contracts. E2E readiness predicates must prove the
     materialized state their scenario asserts. Position valuation readiness must require the exact
     expected `valuation.market_price` in addition to derived market-value/P&L fields, because query
     continuity may publish cost-basis market values and zero unrealized P&L before a daily
     valuation snapshot exists. Reuse `has_expected_valuation_snapshot` for this proof and scan
     adjacent E2E predicates for the same fallback-readiness defect.
217. Destructive app-local canonical reseed cleanup must align every reset Kafka topic family with
     every consumer that persists the physical `topic-partition-offset` identity. Portfolio-scoped
     row deletion is insufficient after offset reuse: a stale fence from another demo portfolio can
     collide before semantic portfolio/transaction identity is evaluated. The canonical
     `transactions.persisted` reset therefore includes `portfolio-transaction-processing` in the
     existing volatile service/topic fence cross-product. Preserve semantic-conflict protection in
     production; do not generalize this local reset into runtime fence deletion or a daemon-wide
     Kafka/PostgreSQL cleanup.
218. E2E module cleanup must observe both sides of the quiescence contract. Active-row timestamp
     queries remain predicate-scoped so completed history cannot create false cleanup timeouts. If
     an all-zero blocking snapshot has no active timestamp, it must still remain continuously zero
     for the configured quiet interval before destructive truncation; `None` is not permission to
     bypass the fence. Do not replace this with whole-table timestamp history or weaker readiness
     timeouts.
219. Current-booking DIVIDEND settlement consumes the existing source-recorded
     `withholding_tax_amount` as separate evidence and computes cash as gross dividend less
     withholding less the resolved transaction fee. Null/zero withholding preserves the prior
     gross-minus-fee result. Negative withholding, withholding above gross, and non-positive
     resulting settlement fail closed with stable `DIVIDEND_014`, `DIVIDEND_015`, and
     `DIVIDEND_013` reason codes before derived writes. Generated cash legs and product cashflows
     consume the same transaction-domain result. When current acceptance triggers an inline
     rebuild, every output produced by the current cost-processing step retains current-booking
     economics, including transformed or split identities. Previously accepted suffix rows use
     the explicit historical-rebuild context: source-recorded positive DIVIDEND withholding stays
     in product-cashflow economics so it continues to reconcile with its generated cash leg, while
     null/zero withholding and rows that predate current settlement fences retain legacy arithmetic. This
     does not implement withholding-rate derivation, other receipt deductions,
     a supplied-net identity, jurisdiction-specific tax policy, return-of-capital, basis reduction,
     or advanced timing; keep those residuals under #448.
220. Canonical front-office seed success requires stable terminal derived state. Pending,
     processing, stale-processing, or failed valuation or aggregation work are all blockers.
     Require three consecutive all-zero observations at the
     configured poll interval; reset the fence if any work reopens, and keep it inside the existing
      900-second readiness deadline. Polling must sleep for the configured interval rather than busy-looping
      against Core, Gateway, or downstream analytics. A populated Workbench response while queues
      still drain is diagnostic progress, not canonical certification.
221. The app-local demo-data loader decides restart work from source-owned pack completeness, not
     portfolio existence or prior idempotency acknowledgements alone. Model each generated write
     as one immutable content-addressed segment, evaluate every segment against its authoritative
     query surface, publish only missing/evolved segments, and emit `unchanged_pack_present` only
     after complete evaluation. Portfolio-bundle completeness includes the exact generated
     business-calendar window, cardinality, and exact ordered identity digest through the QCP
     analytics source product. At least one returned observation must match a governed business
     date, and that filtered projection must form the complete ordered suffix from the first holding date and terminate without a continuation
     page; additional ordered in-window non-business observations are valid, while pre-holding
     business dates are valid calendar facts but do not imply portfolio observations. A terminal position or count
     alone cannot prove calendar continuity. Treat non-404 read failures as fatal
     and fail closed when a segment has no evaluator. Explicit `DEMO_DATA_PACK_FORCE_INGEST=true`
     may bypass the reads and publish the complete pack; it is an operator repair control, not the
     restart default. Generate against RFC-0076's fixed canonical as-of date and the deployed v1
     economic anchor (`2023-07-20`): transaction identities and overlapping market, FX, index,
     benchmark, and risk-free observations must not move when wall-clock time or requested history
     depth changes. Partition
     market and FX writes by logical security/currency-pair identity, keep rows date-ordered, and use
     the `lotus-demo-pack:v2` content namespace for this intentional generator evolution. Verify
     terminal quantities through one explicit as-of `HoldingsAsOf` read per portfolio; do not require
     a transaction-history row to exist exactly on the as-of date or reintroduce per-security polling
     reads. The additive analytics diagnostics digest is backward compatible; this app-local
     behavior does not change event/database schemas, production calculations, or ingestion
     idempotency contracts.

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
