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
12. RFC-0083 Slice 8 now records endpoint-consolidation disposition, deprecates selected pre-live reporting convenience routes in OpenAPI while preserving tested handlers, and enforces the endpoint-consolidation watchlist through `docs/standards/endpoint-consolidation-watchlist.json`, `scripts/endpoint_consolidation_watchlist_guard.py`, and `make endpoint-consolidation-watchlist-guard` so monitored convenience-route families cannot grow without source-data product identity or approved bounded-use rationale,
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
    drift,
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
   `output/coverage/critical-path-coverage-report.json` so aggregate, changed-code, and
   critical-path coverage cannot be conflated,
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
    family through `make live-dpm-source-validate`. `PortfolioManagerBookMembership:v1` is the
    first RFC41-WTBD-001 source-owner foundation and resolves portfolio master rows by
    `advisor_id` without claiming a broader relationship-householding hierarchy.
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
    workflow-provided `lotus-platform` checkout for domain-product contract validation.
27. Boundary mapping conformance now has a repo-native command,
    `make test-boundary-mapping-conformance`, backed by the test manifest and documented in
    `docs/architecture/mapping-anti-corruption-boundary.md`; `make architecture-guard` also runs
    `scripts/mapping_anti_corruption_guard.py` as the representative contract index. It currently
    protects representative transaction event, persistence event-envelope, portfolio tax-lot, and
    performance-economics source-data mappings.
    Ingestion publish workflows must route API DTO serialization through
    `ingestion_service.app.services.ingestion_event_payloads` before Kafka publication; do not add
    new inline DTO `model_dump()` publish payloads in `IngestionService`.
    Valuation, pipeline, persistence, and future event-consuming services must use
    `portfolio_common.event_mapping` or a narrower service adapter around it for Kafka bytes,
    deterministic message identity, governed Pydantic event validation, outbox event payload
    serialization, and explicit correlation/idempotency metadata before opening database units of
    work. Persistence repositories must consume adapter-owned event record values and keep only
    table-specific SQL conflict/update policy locally.
    `PortfolioTaxLotWindow:v1` uses `PortfolioTaxLotReadRecord` as the typed
    repository-to-source-data boundary. `PerformanceComponentEconomics:v1` uses
    `PerformanceEconomicsTransactionReadRecord`, `PerformanceEconomicsCashflowReadRecord`, and
    `PerformanceEconomicsCostReadRecord` so latest optional cashflow evidence and transaction-cost
    component evidence are modeled explicitly before source-data response assembly. Its source-data
    builder is split into row mapping, source-evidence policy, and response-envelope assembly
    modules; preserve that shape before adding component-family, supportability, lineage, runtime
    metadata, or response DTO behavior. Extend this pattern before adding new high-value
    source-data mappers that would otherwise accept raw ORM rows, ORM relationship objects, or
    tuple-shaped SQL results.
    Repository output-shape governance now also has `make repository-output-shape-guard`, wired into
    `make lint`, backed by `scripts/repository_output_shape_guard.py`, and documented in
    `docs/architecture/repository-output-shape-standard.md`. It blocks new public repository methods
    from exposing SQLAlchemy ORM return annotations unless the method is explicitly registered as a
    transitional exception, and it fails stale exceptions after future typed-record conversions.
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
    Shared private-banking value objects now live in
    `portfolio_common.domain_value_objects` for `CurrencyCode`, `MoneyAmount`, `FxRate`,
    `CurrencyBasis`, `Quantity`, `UnitPrice`, and named monetary aliases. New calculation and
    reporting-currency paths should normalize DTO/ORM primitives into these value objects at the
    boundary, keep domain rules framework-free, and serialize back to primitive payloads only at
    API/event/persistence edges.
    Cost-engine domain models now follow
    `docs/standards/cost-engine-domain-model-standard.md`: `cost_engine/domain` must stay free of
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
    failures default to no-commit redelivery; operators can set
    `KAFKA_CONSUMER_DLQ_FAILURE_MAX_ATTEMPTS` to a positive value to stop the consumer with
    `DlqPublicationBudgetExhausted` and bounded `dlq_failure_budget_exhausted` telemetry after
    repeated DLQ failure for the same topic/group/partition/offset/key. Do not claim durable local
    quarantine unless a separate service-owned quarantine store exists. Retryable consumer failures
    default to uncommitted redelivery; operators can set
    `KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ATTEMPTS` and/or
    `KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ELAPSED_SECONDS` to route repeatedly retryable messages
    to DLQ after a bounded in-process budget, committing only after DLQ success.
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
    `portfolio_common.transaction_type_registry`. New or changed transaction types in cost,
    cashflow, position, query, validation, or RFC target work must be classified there first.
    `OTHER` is migration-only and not production-booking allowed. Redemption and
    conversion/exercise target types are known but not implemented until dedicated runtime slices
    add validation, cost, position, cashflow, supportability, and downstream compatibility proof.
    `SPIN_IN` and `DEMERGER_IN` are position transfer inflows; keep position rule tables aligned
    with registry-classified target-security inflow legs.
    The cost engine must fail closed for registry-classified migration-only or target-not-implemented
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
5. targeted unit gate
   `make test`
6. database-backed unit gate
   `make test-unit-db`
7. integration-lite suite
   `make test-integration-lite`
8. boundary mapping conformance
   `make test-boundary-mapping-conformance`
9. E2E smoke
   `make test-e2e-smoke`
10. Docker smoke
   `make test-docker-smoke`
11. repo-native domain-product validation
   `make domain-product-validate`
12. app-level supported-surface validation
   `make lotus-core-validate`
13. documentation release evidence pack
   `make docs-evidence-pack`
14. verified API example catalog
   `make api-example-catalog-guard`
15. generated API route catalog
   `make api-route-catalog-guard`
16. front-door synchronization guard
   `make front-door-sync-guard`

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
   plus a focused runtime import proof such as `PYTHONPATH=src/services/<service>;src/libs/portfolio-common python -c "import app.main"` for the affected service.
7. PR documentation acceptance is explicit: if a change affects routes, contracts,
   supported features, operational behavior, security posture, validation lanes, service
   boundaries, README, architecture docs, API catalog, RFCs, runbooks, wiki source,
   repository context, or platform context, update the relevant source-of-truth docs in the
   same slice or record a concrete no-doc-change rationale in the PR template. Wiki source
   changes require a post-merge publication evidence plan.
8. Supported-feature publication is manifest-backed. Keep
   `contracts/supported-features/lotus-core-supported-features.v1.json`,
   `docs/supported-features.md`, and `wiki/Supported-Features.md` aligned through
   `make supported-features-guard`. The manifest is the canonical place to record capability
   owner, implementation modules/routes, source-data products, tests, validation evidence,
   current status, fail-closed limitations, safe demo claims, prohibited claims, and downstream
   ownership caveats.
9. Incident playbooks are contract-backed. Keep
   `contracts/operations/incident-playbooks.v1.json`,
   `docs/operations/Incident-Playbooks.md`, `docs/operations-runbook.md`,
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
    workload: use `scripts/bank_day_load_reconciliation_report.py` against the completed `run_id`
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
    `PortfolioManagerBookMembership:v1`, `CioModelChangeAffectedCohort:v1`, and
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
    cost-engine processing, transaction-cost persistence, BUY lot-state persistence, or processed
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
47. FX contract lifecycle rows use shared transaction-domain cashflow semantics. `FX_CONTRACT_OPEN`
    and `FX_CONTRACT_CLOSE` are non-cashflow processing types: they carry position exposure, while
    settlement cash movements are represented by separate FX cash settlement rows. Cashflow
    consumers, pipeline readiness, reconciliation, and future supportability code must use
    `portfolio_common.transaction_domain.requires_cashflow_processing(...)` instead of duplicating
    local FX lifecycle skip lists.
48. Runtime CI gates that bring up the compose-backed stack must prebuild schema/topic bootstrap
    images with the app service images. Keep `kafka-topic-creator` and `migration-runner` in the
    shared runtime prebuild subset for Docker smoke, E2E smoke, latency, performance,
    failure-recovery, and institutional-completion gates. E2E diagnostics should be captured by the
    pytest fixture through `LOTUS_TESTS_COMPOSE_LOG_FILE` before compose teardown; workflow-level
    `docker compose logs` capture is only fallback evidence after fixture ownership is gone.
    Service Dockerfiles must keep the governed image provenance block: OCI labels and matching
    runtime environment values for Git commit SHA, Git branch, build timestamp, repo URL, image
    version, image digest, and CI pipeline/run ID. `configure_standard_http_app` registers
    `GET /version` so API services and worker health web apps expose the same metadata plus the
    OCI label map used for release-manifest parity checks. `/health/live` and `/health/ready`
    expose a bounded runtime block with the same build metadata, service app version, environment,
    runtime profile, started-at time, and uptime for safe incident diagnostics.
    `scripts/prebuild_ci_images.py` supplies build args in CI, `scripts/write_build_provenance.py`
    records the same metadata in build evidence, `.github/workflows/image-release.yml` is the only
    image-push path, and `scripts/write_image_release_manifest.py` records digest, OCI label
    parity, SBOM, scan, signing, provenance-attestation, digest-deploy, and same-image-promotion
    evidence across `dev`, `uat`, and `prod`. `make image-provenance-guard` blocks drift,
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
    and request-fingerprint lineage, and prevents downstream services such as `lotus-idea` from
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
61. Cost-calculator FX processing uses the shared canonical FX baseline helper. `FX_SPOT`,
    `FX_FORWARD`, and `FX_SWAP` must route through
    `portfolio_common.transaction_domain.build_fx_baseline_processing_update(...)` after canonical
    FX validation instead of service-local pending strategies or duplicated realized-P&L mode
    branches. Baseline engine and consumer paths support `NONE` and `UPSTREAM_PROVIDED`
    `fx_realized_pnl_mode`; `CASH_LOT_COST_METHOD` remains an explicit future extension that must
    not be simulated without a governed cash-lot ledger, methodology, and tests.
62. Local cleanup is governed by `scripts/clean_generated_artifacts.py` and exposed through
    `make clean`. Keep cleanup policy explicit, repo-root scoped, and test-backed. It may remove
    ignored local caches, Python bytecode, build/package byproducts, coverage files, and generated
    `output/` evidence artifacts, but must preserve source, docs, wiki source, migrations,
    contracts, `.git`, virtual environments, and dependency directories. Do not reintroduce opaque
    inline cleanup commands in `Makefile`. `make generated-artifact-tracking-guard` is the
    source-truth companion: it must fail if generated build, cache, package, coverage, or output
    evidence paths are tracked by Git. A local ignored `src/services/query_service/build/lib` tree
    is disposable workspace output, not authored implementation truth.
63. Ingestion audit and idempotency workflows must use explicit store ports before reaching
    SQLAlchemy helper functions. `IngestionJobStore` owns same-key idempotency replay/conflict
    semantics; `ReplayAuditStore` owns replay-audit duplicate lookup, audit persistence, audit
    reads, fail-closed typed audit-write behavior, and source-safe diagnostic metadata. Default
    runtime wiring may use SQLAlchemy-backed adapters, but `IngestionJobService` must call the
    ports for job creation/idempotency and replay audit workflows. `make architecture-guard` now
    runs `scripts/ingestion_store_port_guard.py`; keep it green when adding diagnostics, DLQ event,
    ops-control, unit-of-work, or publisher ports.
64. Application event publishing must use `portfolio_common.event_publisher` ports rather than
    concrete Kafka producer APIs. `EventPublishRequest` carries topic, key, payload, headers,
    outbox id, and delivery callback metadata. `EventPublishResult` reports `success`,
    `retryable_failure`, `terminal_failure`, or `uncertain` delivery state. Ingestion publish paths
    map those results back to existing `IngestionPublishError` contracts; valuation job publishing
    uses the same port behind the scheduler-specific publisher wrapper. `make architecture-guard`
    now runs `scripts/event_publisher_port_guard.py` to block governed ingestion and valuation
    application publisher paths from importing `KafkaProducer` or `get_kafka_producer` directly.
    Runtime dispatchers, consumer managers, aggregation scheduler publishing, and outbox
    publication are separate follow-up slices.
65. Application/source-data repository dependencies should use capability-specific ports before
    broad concrete repositories. `PortfolioTaxLotWindow:v1` now depends on
    `PortfolioTaxLotReader`, and financial reconciliation service orchestration now depends on
    reconciliation run-writer and evidence-reader ports through `ReconciliationRepositoryPort`
    instead of the concrete `ReconciliationRepository` type. Concrete SQLAlchemy repositories may
    implement multiple ports, but new use cases should name the narrow read/write capability they
    need, add fake-port behavior tests, and keep `make architecture-guard`
    (`scripts/repository_port_guard.py`) green. This is design modularity inside existing
    deployables, not approval for a runtime service split.
66. Governed application ports are cataloged in
    `docs/architecture/application-port-capability-catalog.json` with the human companion
    `docs/architecture/application-port-capability-catalog.md` and standard
    `docs/standards/application-port-layer-standard.md`. Service-local ports should live under
    `src/services/<service>/app/ports/`; shared cross-service ports should live in the narrow
    shared library that owns the reusable contract. `make architecture-guard` now runs
    `scripts/application_port_catalog_guard.py` before the specific port-regression guards, so new
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
    `scripts/application_dependency_inversion_guard.py`, which protects the representative
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
    `make architecture-guard` now runs `scripts/infrastructure_adapter_layer_guard.py` so migrated
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
    `scripts/repository_transaction_boundary_guard.py`; direct repository `commit()` or
    `rollback()` calls are blocked unless explicitly registered as transitional. The current
    transitional exception is `query_service/app/repositories/operations_repository.py` for
    operator control-plane status updates.
71. Application command workflows should model idempotency, audit, correlation, command identity,
    and recovery evidence as reusable application policies instead of repeated local parameter
    plumbing. `docs/standards/application-workflow-policy-standard.md` defines the repo-local rule.
    The first representative workflow lives in
    `src/services/ingestion_service/app/application/workflow_policies.py`:
    `CorrelationContext`, `ApplicationCommandEnvelope`, `IdempotencyWorkflow`, and `AuditWorkflow`.
    `IngestionJobService` preserves its router-facing method signatures but now routes ingestion
    job duplicate/conflict behavior through `IdempotencyWorkflow` and consumer-DLQ replay audit
    writes through `AuditWorkflow`. `make architecture-guard` now runs
    `scripts/application_workflow_policy_guard.py` so the representative path cannot bypass those
    policies. Broader command-handler extraction from routers and cross-workflow concurrency
    certification remain follow-up issue scope.
72. Application services should raise framework-independent application errors and leave HTTP,
    worker, consumer, and operator mapping to their entrypoint adapters. The first representative
    taxonomy lives in `src/services/ingestion_service/app/application/errors.py` with
    `ApplicationError`, `ValidationRejected`, and `UnsupportedOperation`. `UploadIngestionService`
    now raises those errors for upload validation failures, while
    `src/services/ingestion_service/app/routers/uploads.py` maps reason codes back to the existing
    HTTP 400/422 detail contract. `make architecture-guard` now runs
    `scripts/application_error_taxonomy_guard.py` so the representative path cannot reintroduce
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
    `src/services/query_service/app/application/core_snapshot.py` instead of API DTO JSON
    serialization side effects.
    `make architecture-guard` now runs `scripts/application_command_result_guard.py` so the
    migrated representative services cannot reintroduce API DTO imports or response DTO return
    contracts, and core snapshot fingerprinting cannot return to `request.model_dump(mode="json")`.
    Remaining API DTO usage in broader application services is transitional backlog and should not
    be copied into new use cases.
74. The application layer now has a first-class repo-local contract in
    `docs/standards/application-layer-contract.md`. `app/application` and future `app/use_cases`
    packages own command/query handling, use-case orchestration, workflow policies, application
    errors, and calls to ports. They must not import FastAPI/Starlette, SQLAlchemy, concrete Kafka
    producers, repository implementations, producer infrastructure, or consumer infrastructure.
    `make architecture-guard` runs `scripts/application_layer_contract_guard.py` to enforce this
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
    `scripts/ingestion_service_framework_guard.py` to prevent FastAPI imports, `Depends(...)`,
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
    `scripts/upload_component_boundary_guard.py` so upload parsing and entity-specific publish
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
    architecture-guard` runs `scripts/transaction_replay_boundary_guard.py` so event planning,
    deduplication, and correlation header construction do not drift back into the compatibility
    repository adapter.
78. Portfolio aggregation scheduler policy is split from global database sessions, concrete
    repositories, raw metric functions, system clocks, and concrete Kafka publication. The
    repo-local standard lives at
    `docs/standards/aggregation-scheduler-boundary-standard.md`.
    `portfolio_aggregation_service.app.ports.aggregation_scheduler_ports` owns repository-provider,
    repository, metrics-sink, and clock contracts; `app.infrastructure.aggregation_scheduler_adapters`
    owns SQLAlchemy, Prometheus, and system-clock adapters; and `app.core.aggregation_job_publisher`
    owns aggregation job record-key/header/payload planning plus dispatch failure classification
    behind an aggregation-job publisher port. `AggregationScheduler` preserves its default runtime
    constructor while accepting injected settings, repository provider, metrics sink, clock, and
    publisher for fake-port tests. `make architecture-guard` runs
    `scripts/aggregation_scheduler_boundary_guard.py` so DB session factories, concrete
    repositories, concrete Kafka producers, direct publish/flush calls, and raw metric functions do
    not drift back into scheduler orchestration.
79. Position calculation rules are split from database sessions, concrete repositories, outbox
    staging, metrics, epoch fencing, and position-history persistence orchestration. The repo-local
    standard lives at `docs/standards/position-reducer-boundary-standard.md`.
    `position_calculator.app.core.position_reducer` owns `PositionBalanceState`,
    `BackdatedReplayDecision`, buy/sell transitions, cash movement deltas, transfer and
    corporate-action quantity policy, FX contract/cash settlement behavior, flat-position cost
    zeroing, and deterministic backdated replay planning without SQLAlchemy, repositories, outbox,
    metrics, `EpochFencer`, persistence models, Pydantic DTOs, or correlation context.
    `PositionCalculator` remains the application orchestrator and compatibility entry point: it
    performs epoch-fencing checks, repository reads/writes, position-history persistence, outbox
    staging, metric emission, replay event ordering, and DTO adaptation. `make architecture-guard`
    runs `scripts/position_reducer_boundary_guard.py` so reducer transaction-type sets, cash delta
    helpers, buy/sell/transfer/corporate-action state helpers, and backdated replay decision
    helpers do not drift back into `position_logic.py`.
80. Protected business logic modules must stay directly testable without FastAPI, real databases,
    Kafka, Redis, cloud SDKs, or downstream clients. The repo-local standard lives at
    `docs/standards/testability-architecture-standard.md`, and the machine-readable contract lives
    at `docs/standards/testability-architecture-contract.json`. `make architecture-guard` runs
    `scripts/testability_architecture_guard.py`, which currently protects domain, application,
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
    `make architecture-guard` runs `scripts/runtime_boundary_decision_guard.py`, which discovers
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
    architecture-guard` runs `scripts/in_process_modularity_guard.py`. The standard recommends
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
    architecture-guard` runs `scripts/in_process_boundary_guard.py`. Domain packages must stay
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
    `scripts/proof_builder_pattern_guard.py`. The first contract families cover source-data
    supportability, ingestion/replay evidence, reconciliation evidence, and app validation
    evidence. Proof builders accept application/domain/support inputs and return typed artifacts;
    routers map artifacts to API DTOs, repositories own persistence reads, and runbooks document
    operator behavior. A separate proof service requires the runtime-boundary decision process.
86. API adapters should keep DTO-to-command, application-result-to-response, and typed
    error-to-HTTP translation in bounded mapper modules when the mapping is reused, non-trivial, or
    representative for a route family. The repo-local standard lives at
    `docs/standards/api-mapper-pattern-standard.md`; current representative modules cover lookup,
    reconciliation, event-replay command errors, and query-service read error mapping; and `make
    architecture-guard` runs `scripts/api_mapper_pattern_guard.py`. Keep this context entry as
    navigation only: detailed mapping rules belong in the standard and executable guard, not
    duplicated prose.
87. Runtime current-time, elapsed-duration, and generated-ID access should flow through
    `portfolio_common.runtime_providers` in provider-migrated application workflows. The repo-local
    standard lives at `docs/standards/runtime-provider-port-standard.md`; current representative
    coverage includes financial reconciliation elapsed-duration/finding IDs, core snapshot
    generated metadata, and simulation session/change IDs plus TTL/expiry decisions; and `make
    architecture-guard` runs `scripts/runtime_provider_port_guard.py`. Legacy analytics and
    operations services still have direct wall-clock usage and remain explicit migration scope.
88. Query-control-plane analytics-input responses use response-level `lineage` for reproducibility
    and source-data runtime metadata uses `source_lineage` for source proof. Do not let runtime
    metadata helpers return or unpack a raw `lineage` key into
    `PortfolioAnalyticsTimeseriesResponse`, `PositionAnalyticsTimeseriesResponse`, or
    `PortfolioAnalyticsReferenceResponse`; that collision causes unhandled constructor failures in
    downstream performance, risk, and idea proof generation. `AnalyticsTimeseriesService` routes
    those responses through a guarded metadata helper and has canonical
    `PB_SG_GLOBAL_BAL_001` regression tests for the issue #705 proof path.
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
91. Ingestion write APIs use a service-local enterprise-readiness wrapper over
    `portfolio_common.enterprise_readiness` with default capability rules for every canonical
    `/ingest/*` and `/reprocess/*` write route. Future ingestion write routes must update
    `ingestion_write_capability_rules()` and keep the route-coverage test green; do not rely on
    `ENTERPRISE_CAPABILITY_RULES_JSON` alone for production write-plane policy. Shared enterprise
    middleware keeps health, metrics, OpenAPI, docs, ReDoc, and version endpoints on an explicit
    unauthenticated operational allowlist even when read authorization is enabled.
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
