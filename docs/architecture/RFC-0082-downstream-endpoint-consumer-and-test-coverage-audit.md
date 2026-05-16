# RFC-0082 / RFC-0083 Downstream Endpoint Consumer And Test Coverage Audit

Status: Draft implementation audit  
Owner: lotus-core  
Last reviewed: 2026-04-18  
Scope: query-control-plane source-data products and downstream integration posture

## Purpose

This audit records which downstream systems are expected to consume each governed lotus-core endpoint, where direct integration evidence exists, and whether the API documentation and tests are strong enough for production-grade use.

The source of truth for product identity, route family, route ownership, paging/export posture, and intended consumers remains `portfolio_common.source_data_products.SOURCE_DATA_PRODUCT_CATALOG`. This document is a review artifact layered on top of that catalog so that reviewers can reason about consumer readiness without reading every downstream repository.

## Summary

The query-control-plane API is the correct surface for cross-application integration. Downstream systems should call governed `/integration`, `/support`, and `/lineage` contracts rather than query-service convenience reads when they need analytics input, simulation state, benchmark/reference data, data-quality evidence, or operational lineage.

Current posture:

| Area | Assessment |
| --- | --- |
| Route ownership | Clear. lotus-core owns all listed source-data products. |
| Consumer metadata | Clear. Every catalog product exposes `x-lotus-source-data-product` and `x-lotus-source-data-security` in OpenAPI. |
| Swagger readability | Strong for the governed routes covered by RFC-0082/RFC-0083. Endpoint descriptions explain when to use the route, intended consumers, request attributes, response attributes, examples, and error examples. |
| Test pyramid | Strong at catalog/static guard and core integration-test levels. Direct downstream client tests exist for the active consumers found during review. |
| Registered-route coverage | Complete for the downstream-facing query and query-control-plane apps in this pass. A route inventory comparison on April 17, 2026 found every non-health/non-metrics registered route represented in this audit. |
| Platform live proof | Passed on 2026-04-15 for `PB_SG_GLOBAL_BAL_001`; see `docs/architecture/RFC-0083-platform-e2e-runtime-validation-evidence.md`. |

Important boundary reminder:

1. `lotus-core` publishes source-data products and evidence for downstream analytics workflows.
2. `lotus-core` does not own downstream performance-output contracts such as a portfolio workspace
   `Performance Snapshot`.
3. Portfolio return, benchmark return, excess return, attribution totals, and similar
   calculation outputs remain owned by the authoritative downstream analytics service, usually
   `lotus-performance`.

## Certified Endpoint Slice: Analytics Input Family

This certification pass covers the current strategic analytics-input contracts:

1. `POST /integration/portfolios/{portfolio_id}/analytics/reference`
2. `POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries`
3. `POST /integration/portfolios/{portfolio_id}/analytics/position-timeseries`
4. `POST /integration/exports/analytics-timeseries/jobs`
5. `GET /integration/exports/analytics-timeseries/jobs/{job_id}`
6. `GET /integration/exports/analytics-timeseries/jobs/{job_id}/result`

### Route Contract Decision

These are the correct live routes. The legacy convenience reads that downstream systems sometimes
expected in earlier probes are not the governed integration contract:

1. `GET /integration/portfolios/{portfolio_id}/timeseries` is not the strategic route.
2. `GET /integration/positions/{portfolio_id}/timeseries` is not the strategic route.
3. Consumers requiring analytics input must use the `POST /integration/.../analytics/...`
   control-plane contracts so request scope, lineage, reporting-currency conversion, filters,
   dimensions, paging, and source-data metadata remain explicit and reproducible.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /integration/portfolios/{portfolio_id}/analytics/reference` | `lotus-performance`, `lotus-gateway` | Correct. `lotus-performance` uses the route for stateful portfolio lifecycle/reference metadata. `lotus-gateway` uses it for workspace source context and does not attempt to compute analytics itself. |
| `POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries` | `lotus-performance` | Correct. This is the canonical upstream source for stateful portfolio-level return inputs. No gateway direct use was found, which is appropriate. |
| `POST /integration/portfolios/{portfolio_id}/analytics/position-timeseries` | `lotus-performance`, `lotus-risk` | Correct. `lotus-performance` uses it for contribution/attribution-style sourcing. `lotus-risk` uses it for historical attribution exposure history. |
| analytics export create/status/result | `lotus-performance` | Correct. These adjunct routes support large-window extraction and batch retrieval workflows when direct paged polling is not the right fit. Swagger now makes the create/status/result split explicit so downstreams can distinguish interactive page traversal from durable export-job hand-off. |

### Upstream Integration Assessment

The analytics-input family is on the correct serving plane for upstream callers:

1. query-control-plane, not query-service convenience reads
2. `POST` contract shape, not `GET`, because these routes support governed request bodies
3. explicit request lineage through `consumer_system`
4. deterministic paging via `page.page_token` and `request_scope_fingerprint`
5. reproducible currency scope via `reporting_currency`
6. durable export lifecycle and result retrieval for large-window downstream extraction

For this family, the upstream contract is already aligned with the architecture target in
RFC-0082/RFC-0083. The remaining risk is not route placement; it is keeping economic correctness
and downstream adoption synchronized as the analytics stack evolves.

### Swagger / OpenAPI Assessment

For the analytics-input family, Swagger is now production-grade on the following dimensions:

1. route descriptions explain when to use each endpoint and who should consume it;
2. request fields and response fields carry explicit descriptions;
3. canonical examples/defaults are present across the schema family;
4. source-data product metadata and security metadata are published in OpenAPI extensions;
5. invalid-request and not-found examples are published for the operator-facing failure modes.

Automated proof now includes a recursive analytics-input schema completeness assertion in
`tests/integration/services/query_control_plane_service/test_control_plane_app.py` so regressions
in field descriptions/examples are caught even when nested models change.

The HTTP dependency lane now also proves route-level error semantics across the strategic
analytics-input family: invalid analytics request shape maps to `400`, missing portfolio reference
maps to `404`, and insufficient source data maps to `422`, so downstream consumers do not need to
infer those statuses only from OpenAPI examples.

The same dependency lane now covers the adjunct analytics export contract family, including create,
status lookup, JSON result retrieval, NDJSON result retrieval with gzip transport, `404` for
missing jobs, `422` for incomplete export payload state, and `422` for export-result
serialization requests that the persisted job cannot satisfy.

### Issue Disposition For This Endpoint Family

Reviewed open `lotus-core` issues tied directly to these contracts:

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `#233` position-timeseries missing `position_currency` | Addressed in the live contract. `PositionTimeseriesRow.position_currency` is present in the public schema, documented, and regression-covered. | Closure comment posted with implementation evidence; issue should now be closed. |
| `#259` need explicit flow provenance beyond plain external flow | Closed. `CashFlowObservation` now exposes `cash_flow_type`, `flow_scope`, and `source_classification`, with OpenAPI descriptions covering semantics. | Keep closed unless fresh downstream evidence shows internal/external flow provenance has regressed. |
| `#250` acquisition-day position cash flows missing for newly opened positions | Closed. Current service-layer evidence shows funded acquisition-day stock positions emit `internal_trade_flow` cash flows rather than an empty list. | Re-open only if fresh live cross-app artifacts again show `cash_flows=[]` on the acquisition day. |
| `#253` portfolio-timeseries versus position-timeseries reconciliation mismatch | Closed. Current service-layer evidence shows day-boundary capital continuity repair and internal cash-book settlement neutralization in portfolio observation aggregation. | Re-open only if fresh live cross-app artifacts show the reported begin/end mismatch again. |
| `#254` fresh seeded analytics windows do not mature beyond day one | Closed. Query-service maturity reporting now derives `performance_end_date` from the latest available analytics horizon across portfolio-timeseries and position-timeseries publication, so synthesized portfolio windows no longer appear stalled behind lagging persisted portfolio aggregate rows. | Re-open only if fresh canonical/live validation again shows newly seeded analytics windows stuck on day one. |
| `#258` internal trade legs misclassified as `external_flow` | Closed. Unit/service evidence now shows distinct `internal_trade_flow` versus `external_flow` behavior for the funded buy scenario. | Re-open only if fresh live cross-app artifacts contradict the service tests. |
| `#260` staged external cash flows doubled in cash-only windows | Closed. Unit/service evidence now shows portfolio and position staged external flows remain `10000`, `5000`, `-2000` rather than doubling. | Re-open only if fresh live cross-app artifacts contradict the service tests. |

No new gateway issue is required from this slice. Gateway is using the strategic analytics-reference
route correctly for source context, and no duplicate or stale gateway usage of legacy analytics
paths was found during review.

## Certified Endpoint Slice: Benchmark Assignment

This certification pass covers the strategic benchmark-resolution contract:

1. `POST /integration/portfolios/{portfolio_id}/benchmark-assignment`

### Route Contract Decision

This is the correct benchmark-assignment route for downstream consumers that need effective
portfolio-to-benchmark mapping before benchmark-aware analytics or workspace composition.

The contract is intentionally assignment-resolution only. It does not replace:

1. benchmark definition contracts,
2. benchmark composition-window contracts,
3. benchmark market-series contracts,
4. downstream benchmark math owned by `lotus-performance`.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /integration/portfolios/{portfolio_id}/benchmark-assignment` | `lotus-performance`, `lotus-gateway` | Correct. `lotus-performance` uses the route as benchmark context for stateful benchmark-aware analytics. `lotus-gateway` uses it for workspace composition context. |

Catalog-intended consumers also include `lotus-risk` and `lotus-report`, but no direct active code
path was found in this pass that should be overstated as live validated.

### Upstream Integration Assessment

The current implementation resolves benchmark assignment by:

1. `portfolio_id`
2. `as_of_date`
3. effective-date ordering
4. assignment-version ordering for ties

`reporting_currency` and `policy_context` are currently caller-context fields, not assignment
selection keys. This is now documented explicitly in the request schema and route description so
the public contract is truthful. The endpoint remains correctly placed on the query-control-plane.

### Swagger / OpenAPI Assessment

For this endpoint, Swagger now makes the following explicit:

1. when to use the endpoint;
2. that assignment resolution is keyed by `portfolio_id` plus `as_of_date`;
3. that `reporting_currency` and `policy_context` do not currently alter assignment selection;
4. response field descriptions and examples for assignment-capture metadata such as
   `assignment_recorded_at` and `contract_version`.

Automated proof now includes a benchmark-assignment schema-family completeness assertion in
`tests/integration/services/query_control_plane_service/test_control_plane_app.py`.

The dependency lane now also exercises the ASGI surface for benchmark-assignment and adjacent
shared reference-source routes used by `lotus-performance` and `lotus-risk`, including raw
risk-free series, risk-free coverage, and classification taxonomy. That closes the previous gap
where these contracts had router-function and OpenAPI proof but lighter HTTP-level dependency
coverage.

### Issue Disposition For This Endpoint

Reviewed benchmark-assignment-related issues:

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `#237` grouped benchmark analytics contract | Closed on GitHub. This is broader than assignment resolution and should not be treated as an active benchmark-assignment defect in this slice. | Keep closed unless fresh downstream evidence shows attribution consumers again lack a governed benchmark-source path. |
| `#246` broader benchmark source-contract hardening | Closed on GitHub. The current benchmark-source family now covers window-aware composition, component market-series paging, targeted index catalog metadata, and explicit normalization policy. | Keep closed unless fresh benchmark-calculation evidence exposes a remaining source-contract gap. |
| `#249` benchmark-assignment ingest optional timestamp mismatch | Already addressed in the ingestion path. The reference-data ingestion service defaults `assignment_recorded_at` when omitted, and integration coverage proves the omitted-field request persists a non-null value. | Closure comment posted with service and integration-test evidence; close as implemented unless fresh contrary evidence appears. |

No downstream migration issue is required from this slice. `lotus-performance` and `lotus-gateway`
are both calling the strategic route, and no duplicate/stale benchmark-assignment consumer path was
found during review.

## Certified Endpoint Slice: Benchmark Source Family

This certification pass covers:

1. `POST /integration/benchmarks/{benchmark_id}/composition-window`
2. `POST /integration/benchmarks/{benchmark_id}/market-series`
3. `POST /integration/benchmarks/{benchmark_id}/coverage`

### Route Contract Decision

These are the correct benchmark-source contracts for downstream benchmark-aware analytics.

The contract split is intentional:

1. `composition-window` is the strategic source for cross-rebalance benchmark composition history;
2. `market-series` is the strategic source for raw component market series plus optional
   benchmark-to-target FX context;
3. downstream benchmark calculation still belongs to `lotus-performance`, not `lotus-core`;
4. single-date benchmark definition reads are useful reference context, but are not a substitute
   for long-window benchmark calculation across composition changes.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /integration/benchmarks/{benchmark_id}/composition-window` | `lotus-performance` | Correct. `lotus-performance` uses the route in its stateful benchmark input path for rebalance-aware benchmark sourcing. |
| `POST /integration/benchmarks/{benchmark_id}/market-series` | `lotus-performance` | Correct. `lotus-performance` uses the route for component weights, raw component series, and FX-context-aware benchmark exposure/build flows. |

`lotus-risk` is catalog-intended for this family, but current live risk architecture deliberately
consumes performance-aligned benchmark exposure context rather than orchestrating core benchmark
market-series directly.

### Upstream Integration Assessment

The current benchmark-source family is aligned with the intended boundary:

1. `composition-window` returns effective-dated segments and avoids daily-expanded duplication;
2. `market-series` returns native component series plus explicit normalization metadata;
3. deterministic paging exists for large component universes via `ReferencePageRequest` and
   `ReferencePageMetadata`;
4. `indices/catalog` now also supports optional targeted `index_ids`, so attribution consumers that
   already know the benchmark component universe can fetch canonical classification labels without
   scanning the full effective index catalog;
5. current `fx_rate` semantics are benchmark-currency-to-target-currency context only and should
   not be mistaken for component-to-benchmark normalization.

The benchmark market-series contract now also publishes an explicit
`component_metadata_policy` telling consumers to use targeted `indices/catalog` lookup when they
need canonical classification labels or other component metadata alongside raw series.

That last point is important enough to make explicit: the contract is strong and truthful today,
but it is not a fully normalized benchmark-engine output contract. That remains a valid future
enhancement area under the broader benchmark-source program.

### Swagger / OpenAPI Assessment

For this family, Swagger now makes the following explicit:

1. `composition-window` is the strategic cross-rebalance source;
2. `market-series` exposes native component series, not benchmark-currency-normalized component
   outputs;
3. benchmark math ownership remains with `lotus-performance`;
4. deterministic paging, request fingerprints, and normalization metadata are first-class parts of
   the public schema.

Automated proof now includes a benchmark-source schema-family completeness assertion in
`tests/integration/services/query_control_plane_service/test_control_plane_app.py`.

HTTP-level dependency proof now also exercises both benchmark-source routes in
`tests/integration/services/query_control_plane_service/test_integration_router_dependency.py`,
including route-success payload shape and route-specific `404` or `400` mapping for downstream
integration failures.

The same dependency lane now also covers the adjacent benchmark-definition and raw index or
benchmark series contracts that lotus-performance and lotus-risk depend on when they need
point-in-time reference context or provider-return evidence alongside the strategic source routes.
Discovery catalog routes for benchmarks and indices are exercised in the same lane so downstream
lookup and selection workflows are covered before they branch into definition, composition, or
series retrieval.

### Issue Disposition For This Endpoint Family

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `#246` broader benchmark source hardening | Closed on GitHub. The source family now has the requested window-aware composition contract, deterministic component market-series paging, request fingerprints, normalization metadata, and targeted index catalog lookup. | Keep closed unless fresh long-window benchmark-calculation evidence exposes a new source-contract gap. |
| `#237` grouped benchmark analytics contract | Closed on GitHub. Targeted `indices/catalog` plus the governed composition-window and market-series contracts give attribution consumers a reusable benchmark-source path without full catalog scans. Grouped benchmark math remains downstream analytics ownership rather than a lotus-core output obligation. | Keep closed unless a future RFC deliberately moves grouped benchmark analytics input ownership back into lotus-core. |

No new downstream migration issue is required from this slice. The active downstream consumer is
already using the strategic routes rather than a stale or duplicate benchmark path.

The certification lane now also protects the adjacent benchmark definition, benchmark catalog,
index catalog, and raw return-series schema family with recursive OpenAPI guards so nested
reference/publication fields do not drift silently while benchmark sourcing evolves.

Swagger now also makes the supporting-route boundary clearer for this adjacent family:

1. benchmark definition is point-in-time benchmark context, now explicitly documents direct
   `lotus-performance` stateful benchmark-sourcing usage, and is not the strategic cross-window
   benchmark calculation contract;
2. benchmark catalog is discovery-first, now explicitly documents `lotus-gateway` workspace
   benchmark-selection usage, and should give way to targeted benchmark routes once an identifier
   is known;
3. index catalog is the governed metadata and classification lookup for benchmark component
   identities, now explicitly documents direct `lotus-performance` benchmark exposure and
   attribution sourcing usage, and should be preferred over downstream local classification maps;
4. raw index price-series and benchmark return-series routes now also document the active
   `lotus-performance` calculated-benchmark and vendor-series sourcing modes they support, while
   remaining evidence/reference contracts rather than substitutes for composition-window plus
   market-series sourcing when lower-level benchmark reconstruction is required.

## Certified Endpoint Slice: Benchmark And Index Reference Family

This certification pass covers:

1. `POST /integration/benchmarks/{benchmark_id}/definition`
2. `POST /integration/benchmarks/catalog`
3. `POST /integration/indices/catalog`
4. `POST /integration/indices/{index_id}/price-series`
5. `POST /integration/indices/{index_id}/return-series`
6. `POST /integration/benchmarks/{benchmark_id}/return-series`

### Route Contract Decision

These remain valid supporting downstream contracts, but they are not the strategic benchmark
calculation seams.

The intended split is now explicit:

1. benchmark definition is point-in-time reference context;
2. benchmark catalog is discovery-first selection support;
3. index catalog is governed metadata and classification lookup for known benchmark components;
4. raw index and benchmark return-series routes are vendor/reference evidence inputs;
5. cross-window benchmark calculation still belongs to `lotus-performance` and should prefer
   composition-window plus market-series when lower-level reconstruction is required.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /integration/benchmarks/{benchmark_id}/definition` | `lotus-performance` | Correct. Performance uses the route for point-in-time benchmark reference context before broader benchmark sourcing. |
| `POST /integration/benchmarks/catalog` | `lotus-gateway` | Correct. Gateway uses the route for workspace benchmark-selection and discovery flows before targeted benchmark routes are known. |
| `POST /integration/indices/catalog` | `lotus-performance` | Correct. Performance uses targeted `index_ids` lookup to resolve governed classification labels for benchmark component grouping. |
| `POST /integration/indices/{index_id}/price-series` | `lotus-performance` | Correct. Performance uses the route for component-level benchmark source pricing when reconstructing benchmark inputs. |
| `POST /integration/indices/{index_id}/return-series` | No active direct caller evidenced in this pass | Catalog-intended and contract-valid. Current direct code evidence remains stronger for index price-series and benchmark market-series than for raw index return-series itself. |
| `POST /integration/benchmarks/{benchmark_id}/return-series` | `lotus-performance` | Correct, with discipline. Performance uses the route as vendor/reference benchmark return evidence and explicit override-style sourcing, not as the default benchmark-math path. |

`lotus-risk` remains catalog-intended for parts of this family, but this pass did not find active
direct raw definition, catalog, or return-series calls that should be described as live production
dependencies here.

### Upstream Integration Assessment

The family is now aligned with the intended downstream boundary:

1. benchmark definition returns effective point-in-time context and clean `404` semantics;
2. benchmark catalog is explicitly discovery-first and should give way to targeted routes once a
   concrete identifier is known;
3. index catalog supports optional targeted `index_ids`, so downstream consumers do not need full
   catalog scans just to resolve known benchmark component metadata;
4. raw index price-series and benchmark return-series remain source/reference evidence contracts,
   not substitutes for the strategic benchmark-source family;
5. current downstream performance usage matches that split: benchmark grouping relies on targeted
   index-catalog metadata, benchmark reconstruction uses price-series plus composition/market
   contracts, and vendor benchmark return-series stays non-default evidence input.

### Swagger / OpenAPI Assessment

For this family, Swagger now makes the following explicit:

1. benchmark definition is point-in-time reference context, not the strategic cross-window
   calculation contract;
2. benchmark catalog is for discovery and selection before targeted benchmark routes are known;
3. index catalog is the governed source for benchmark component metadata and classification labels;
4. raw index price-series and raw return-series contracts are evidence/reference inputs with
   explicit downstream usage notes;
5. the nested benchmark reference, catalog, and raw-series schema family is protected by recursive
   OpenAPI completeness guards.

Focused HTTP-level dependency proof exists in
`tests/integration/services/query_control_plane_service/test_integration_router_dependency.py` for
benchmark definition, benchmark catalog, index catalog, raw index price-series, raw index
return-series, and raw benchmark return-series success and not-found behavior where applicable.

Schema-quality proof exists in
`tests/integration/services/query_control_plane_service/test_control_plane_app.py`, including route
descriptions, response examples, and nested component schema completeness for the broader benchmark
reference/catalog family.

### Issue Disposition For This Endpoint Family

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core #237` grouped benchmark analytics contract | Closed on GitHub. Targeted `index_ids` removes the old full-catalog-scan pain, and grouped benchmark math remains downstream analytics ownership. | Keep closed unless a future source-contract RFC changes benchmark grouping ownership. |
| `lotus-core #246` broader benchmark source hardening | Closed on GitHub. The supporting benchmark source/reference contracts are truthful and covered by the current certification evidence. | Keep closed unless fresh benchmark-source evidence shows a regression. |
| `lotus-performance #125` downstream adoption of latest lotus-core benchmark/reference hardening | Closed on April 16, 2026. Current performance repo truth on `main` includes merge commit `3d48e79` plus follow-up commits `6210e33` and `bf178e3`, and active client/tests still bind to the strategic benchmark, index, analytics-reference, and risk-free routes. | Keep closed unless fresh performance code or runtime evidence drifts from the governed route split. |

No new downstream migration issue is required from this slice. The active consumers reviewed here
are already using the governed routes rather than a stale duplicate seam.

## Certified Endpoint Slice: Risk-Free Reference Family

This certification pass covers:

1. `POST /integration/reference/risk-free-series`
2. `POST /integration/reference/risk-free-series/coverage?currency=...`

### Route Contract Decision

These are the correct strategic routes for risk-free reference sourcing and readiness diagnostics.

The contract split is intentional:

1. `risk-free-series` publishes raw source series plus convention metadata and lineage;
2. `coverage` publishes readiness diagnostics for the same currency/window;
3. downstream analytics services decide whether they can proceed, fail closed, or omit dependent
   metrics based on the returned data availability.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /integration/reference/risk-free-series` | `lotus-performance`, `lotus-risk` | Correct. Both services use the route as a source input rather than computing or inventing risk-free assumptions locally. |
| `POST /integration/reference/risk-free-series/coverage?currency=...` | `lotus-risk` | Correct. `lotus-risk` uses coverage diagnostics to produce deterministic readiness and dependency-failure behavior for rolling Sharpe. |

Gateway is not a direct caller of these endpoints. Its current follow-on issue is product-surface
messaging alignment, not route misuse.

### Upstream Integration Assessment

The current risk-free family is structurally correct and on the right serving plane. The important
contract truth is:

1. an empty `points` list means the route is reachable but usable source data is absent for the
   requested currency/window;
2. `coverage` with `total_points = 0` and null observed bounds means the same thing in readiness
   form;
3. these responses should be treated as upstream data-availability gaps, not as permission for
   downstream zero-risk-free fallback math unless a downstream service explicitly governs that mode.

### Swagger / OpenAPI Assessment

For this family, Swagger now makes the following explicit:

1. raw series publication versus readiness diagnostics;
2. that empty series responses are data-availability signals, not alternate methodology signals;
3. that zero-point coverage with null observed bounds indicates upstream data absence for the
   requested currency/window.

The adjacent benchmark and risk-free coverage routes now also publish the same boundary more
plainly:

1. coverage routes are source-data readiness evidence for downstream analytics and operator flows;
2. they are not benchmark-return outputs, risk metrics, or a substitute for the downstream
   analytics engines that consume them.

Automated proof now includes a risk-free schema-family completeness assertion in
`tests/integration/services/query_control_plane_service/test_control_plane_app.py`.

Focused certification evidence on April 18, 2026 rechecked the coverage surfaces directly:

1. Downstream code scan still shows direct product usage only for `lotus-risk` risk-free coverage (`src/app/integrations/lotus_core_client.py`, `src/app/services/rolling_mode_adapter.py`, and related unit/integration tests). No active direct benchmark-coverage client binding was found in gateway, manage, report, advise, or performance during this pass.
2. Live probe: `POST /integration/reference/risk-free-series/coverage?currency=USD` with `window.start_date=2026-03-19` and `window.end_date=2026-04-17` returned `200 OK` with `product_name=DataQualityCoverageReport`, `product_version=v1`, and a current `latest_evidence_timestamp`.
3. Live probe: `POST /integration/benchmarks/BMK_PB_GLOBAL_BALANCED_60_40/coverage` over the same window returned `200 OK` with `product_name=DataQualityCoverageReport`, `product_version=v1`, and a current `latest_evidence_timestamp`.
4. Contract probe: the risk-free coverage route rejects an incorrect body shape with `422`, confirming the public contract remains `CoverageRequest` in the body plus `currency` as a query parameter rather than an undocumented mixed payload mode.

### Issue Disposition For This Endpoint Family

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core #294` risk-free data missing for USD live window | Closed. Current repo and recorded live evidence indicate the issue was stale rather than a standing publication defect: the canonical front-office seed bundle extends USD risk-free series through `2026-05-10`, and the 2026-04-15 production-readiness closure records live USD coverage of `90` points with zero missing dates for `2026-01-01` to `2026-03-31`. | Re-open only if fresh canonical/live probes again show empty USD series for the governed window. |
| `lotus-risk #77` rolling Sharpe follow-up after upstream fix | Stale. `lotus-risk` now records the canonical portfolio as live validated for stateful `ROLLING_SHARPE` in `docs/operations/live-risk-validation-matrix.md`, so the original follow-up condition has already been satisfied. | Close in `lotus-risk` unless fresh live validation again fails for the governed canonical scenario. |
| `lotus-gateway #112` stale zero-risk-free fallback wording | Closed on April 16, 2026. Fresh gateway evidence on April 17, 2026 confirms rolling-risk supportability now treats risk-free dependency failure as Sharpe omission/unavailability rather than a zero-risk-free methodology fallback. | Keep closed unless gateway reintroduces zero-risk-free fallback wording or behavior without a governed methodology contract. |
| `lotus-gateway #114` stale zero-risk-free fallback wording in summary supportability | Closed on April 16, 2026. Fresh gateway evidence on April 17, 2026 confirms risk summary supportability no longer claims a zero-risk-free Sharpe fallback; the only remaining source reference says gateway does not assume that fallback. | Keep closed unless summary supportability again implies an ungoverned zero-risk-free Sharpe methodology. |

No new downstream migration issue is required from this slice. The known work here is live data
availability and downstream messaging alignment, not route replacement.

## Certified Endpoint Slice: Simulation Session Family

This certification pass covers:

1. `POST /simulation-sessions`
2. `GET /simulation-sessions/{session_id}`
3. `DELETE /simulation-sessions/{session_id}`
4. `POST /simulation-sessions/{session_id}/changes`
5. `DELETE /simulation-sessions/{session_id}/changes/{change_id}`
6. `GET /simulation-sessions/{session_id}/projected-positions`
7. `GET /simulation-sessions/{session_id}/projected-summary`

### Route Contract Decision

These are the correct strategic control-plane routes for deterministic portfolio what-if state.

The boundary is now made explicit in Swagger and tests:

1. use these routes for sandbox state creation, mutation, and projected booked-state inspection;
2. do not use them as analytics-input publication routes;
3. do not use them for advisory recommendation, suitability, or proposal-decision logic;
4. portfolio-state projections may be consumed by downstream workflows, but recommendation logic
   remains outside `lotus-core`.

### Downstream Consumer Reality

| Route family | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `/simulation-sessions/*` | `lotus-gateway` direct; `lotus-workbench` indirect through gateway | Correct. Gateway currently calls create-session, add-change, projected-positions, and projected-summary through the control-plane base path; Workbench consumes the sandbox flow only through the governed gateway contract. Direct session read/close are available for future workflow expansion but are not overstated as live gateway calls in this pass. |
| `/integration/advisory/proposals/simulate-execution` | `lotus-advise` | Separate but related strategic route. Advise does not call raw simulation-session lifecycle routes directly for canonical proposal execution. |

`lotus-manage` remains an intended consumer in the RFC-0082 inventory, but no active direct code
path was found in this review that should be overstated as live validated.

### Upstream Integration Assessment

The simulation-session family remains on the correct serving plane and behind the correct base path:

1. query-control-plane, not query-service convenience reads;
2. control-plane sandbox lifecycle for booked-state projections;
3. deterministic projected state, not analytics output;
4. downstream advisory execution goes through the separate canonical
   `/integration/advisory/proposals/simulate-execution` route.

During this pass, a real runtime defect was also corrected: unknown `portfolio_id` on
`POST /simulation-sessions` now fails as a clean not-found error instead of falling through to a
database foreign-key violation path that could leak internal details.

### Swagger / OpenAPI Assessment

For this family, Swagger is now production-grade on the following dimensions:

1. create and projection route descriptions explain when to use the routes and when not to use
   them;
2. create-session now documents the portfolio-not-found failure mode;
3. internal server failure text is sanitized rather than exposing raw exception content;
4. the full simulation schema family is covered by a recursive documentation/example guard in
   `tests/integration/services/query_control_plane_service/test_control_plane_app.py`.

The HTTP dependency lane now also covers the practical lifecycle that gateway-style consumers
actually execute: create, read, close, add-change, delete-change, projected-positions, and
projected-summary responses all have direct router-level success or failure proof in
`tests/integration/services/query_control_plane_service/test_simulation_router_dependency.py`.
Mutation routes now also distinguish missing session or change state (`404`) from inactive-session
or invalid mutation requests (`400`) instead of collapsing those outcomes into one generic client
error bucket.

### Issue Disposition For This Endpoint Family

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `#54` simulation OpenAPI error-response gap | Closed. Negative response codes are documented and guarded by integration tests. | Keep the OpenAPI integration assertions as the regression guard. |
| `#52` unknown portfolio leaks raw DB 500 on create-session | Closed. Service now prevalidates portfolio existence and the router returns a sanitized 404/500 contract. | Keep the router dependency proof to prevent a DB-leak regression. |

## Certified Endpoint Slice: Advisory Simulation Execution

This certification pass covers:

1. `POST /integration/advisory/proposals/simulate-execution`

### Route Contract Decision

This is the strategic canonical execution-projection route for `lotus-advise`.

The boundary remains explicit:

1. use it after advisory context resolution, request hashing, and idempotency orchestration;
2. do not use it as a generic simulation-session lifecycle route;
3. do not use it as a gateway-facing workspace read;
4. do not treat it as ownership of advisory recommendation logic.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /integration/advisory/proposals/simulate-execution` | `lotus-advise` | Correct. `lotus-advise` sends the canonical contract header, request hash, idempotency key, correlation id, and validates both response header and payload contract version fields. |

### Swagger / OpenAPI Assessment

For this endpoint, Swagger now makes the following explicit:

1. execution projection belongs to `lotus-core`, while recommendation ownership does not;
2. error responses are published as canonical problem-details payloads;
3. problem-details fields now carry explicit examples for contract-version mismatch handling;
4. the control-plane OpenAPI regression suite now asserts the contract-version header semantics and
   the route-purpose wording that fences this endpoint away from generic simulation-session usage.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-advise #93` canonical core advisory simulation execution contract review | Closed on April 17, 2026. Current advise client/tests already cover the certified route, contract-version header, request hash, idempotency key, correlation id, response header validation, lineage/allocation-lens contract-version validation, and 412/422-style problem-details handling. | Keep closed unless a future lotus-core advisory simulation contract version or problem-details shape changes. |

## Certified Endpoint Slice: Classification Taxonomy

This certification pass covers:

1. `POST /integration/reference/classification-taxonomy`

### Route Contract Decision

This is the strategic route for shared classification labels across Lotus applications.

The contract is intentionally source-owned:

1. it returns effective taxonomy entries by `as_of_date` and optional `taxonomy_scope`;
2. it is the governed source for shared labels used by performance, risk, gateway, and advise;
3. it does not synthesize missing labels for unsupported dimensions or incomplete source coverage.

That final point matters. Downstream consumers should use absence of a governed label as a visible
coverage signal, not silently invent fallback labels that blur source truth.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /integration/reference/classification-taxonomy` | `lotus-advise` | Correct after downstream fix. Advise now uses the route as a best-effort governed instrument-taxonomy source during stateful context resolution, caches taxonomy by as-of date, and keeps fallback labels visible as supportability signals rather than authoritative taxonomy output. |

`lotus-performance`, `lotus-risk`, and `lotus-gateway` remain catalog-intended consumers because
they rely on the same governed vocabulary, but this pass did not verify live direct calls from
those services that should be overstated as endpoint-specific production adoption.

### Upstream Integration Assessment

The taxonomy route is correctly placed on the query-control-plane and currently behaves as a
truth-preserving vocabulary surface:

1. effective-dated taxonomy entries are returned without caller-side inference;
2. `taxonomy_scope` is a filter over governed source scopes, not a remapping layer;
3. missing labels remain absent, which allows downstream consumers to distinguish unsupported or
   incomplete classification coverage from valid source-owned classifications.

### Swagger / OpenAPI Assessment

For this endpoint, Swagger now makes the following explicit:

1. the route exists to prevent local taxonomy drift;
2. `taxonomy_scope` is an optional governed-scope filter;
3. missing labels remain absent rather than synthesized;
4. the taxonomy contract version is explicit and exampled.

Automated proof now includes a classification-taxonomy schema-family completeness assertion in
`tests/integration/services/query_control_plane_service/test_control_plane_app.py`.

The HTTP dependency lane now proves both the all-scope path and the explicit `taxonomy_scope`
filter path so downstream consumers can rely on the route for either full vocabulary hydration or
narrow governed-scope reads such as index-only classification pulls.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core #306` missing sector labels for canonical benchmark indices | Closed. Current repo truth indicates the issue was stale rather than an active contract defect. The canonical demo/seed bundle now publishes governed broad-market sector labels for `IDX_GLOBAL_EQUITY_TR` and `IDX_GLOBAL_BOND_TR`, repository coverage proves effective-dated index catalog resolution keeps those labels, and the `indices/catalog` contract now documents that broad benchmark component indices can legitimately publish broad-market sector labels instead of issuer sectors. | Re-open only if fresh live ingestion/runtime evidence again omits the labels. |
| `lotus-advise #94` adopt lotus-core classification taxonomy to reduce local advisory label drift | Closed on April 17, 2026. `lotus-advise` commit `e5d3de1` makes stateful context resolution perform a best-effort control-plane call to `POST /integration/reference/classification-taxonomy`, caches the effective instrument taxonomy by as-of date, normalizes asset-class and product-type shelf labels against governed taxonomy records when available, and exposes `UNKNOWN` plus supportability attributes when upstream labels are missing from the governed taxonomy. Advisory docs/tests now record that local fallback is supportability-only rather than authoritative classification logic. | Keep closed unless advise removes the taxonomy fetch or starts presenting fallback labels as authoritative taxonomy output. |

The active need here is continued downstream taxonomy adoption and classification-coverage quality,
not route replacement inside lotus-core.

## Certified Endpoint Slice: Support And Lineage Evidence

This certification pass covers the operator-evidence family around:

1. `GET /support/portfolios/{portfolio_id}/overview`
2. `GET /support/portfolios/{portfolio_id}/readiness`
3. `GET /support/portfolios/{portfolio_id}/calculator-slos`
4. `GET /support/portfolios/{portfolio_id}/control-stages`
5. `GET /support/portfolios/{portfolio_id}/valuation-jobs`
6. `GET /support/portfolios/{portfolio_id}/aggregation-jobs`
7. `GET /support/portfolios/{portfolio_id}/analytics-export-jobs`
8. `GET /support/portfolios/{portfolio_id}/reconciliation-runs`
9. `GET /support/portfolios/{portfolio_id}/reconciliation-runs/{run_id}/findings`
10. `GET /support/portfolios/{portfolio_id}/reprocessing-keys`
11. `GET /support/portfolios/{portfolio_id}/reprocessing-jobs`
12. `GET /lineage/portfolios/{portfolio_id}/securities/{security_id}`
13. `GET /lineage/portfolios/{portfolio_id}/keys`

### Route Contract Decision

These are support-plane and lineage-plane contracts, not business-calculation inputs.

They exist to publish:

1. operator evidence for blocked controls and replay workflows,
2. deterministic lineage state for recovery and investigation,
3. durable support metadata without requiring direct database access.

The single-key lineage route remains an operational lineage-evidence endpoint rather than a full
source-data-product envelope. The governed `IngestionEvidenceBundle` product covers the paged
lineage/reprocessing evidence routes, while this route stays documented as a focused
portfolio-security investigation helper.

They should not be presented to downstream teams as calculation-grade portfolio analytics APIs.

### Downstream Consumer Reality

| Route family | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| portfolio support overview/readiness | `lotus-gateway` direct; `lotus-workbench` indirect through gateway | Active direct use exists in gateway for workspace supportability and readiness context. Workbench depends on the governed gateway contract rather than calling lotus-core directly. |
| deeper reconciliation / replay / lineage evidence | no strong active direct consumer found in this pass | Contract is published and documented, but live product-flow evidence remains limited. Treat these routes as support-plane ready, not fully downstream-proven product surfaces. |

This is an important distinction: the endpoints are useful and intentionally governed, but the
consumer proof is still lighter than the core integration-contract families above.

### Upstream Integration Assessment

The support and lineage routes are correctly placed and modeled, but their main risk is overclaiming
runtime maturity. The current contract now states more explicitly that:

1. reconciliation runs and findings are operator evidence,
2. replay keys/jobs are operational evidence,
3. lineage routes are operational lineage evidence,
4. none of these routes should be treated as business-calculation inputs,
5. `overview` is the backlog/control/replay support surface while `readiness` is the
   source-owned front-office readiness and workflow-gating surface.

### Swagger / OpenAPI Assessment

For this family, Swagger now makes the operator-only boundary clearer and recursive schema-family
tests protect the evidence bundle models from documentation drift.

The first-hop gateway or operator routes are now more explicit too:

1. `overview` is published as supportability evidence for gateway support panels, operator
   consoles, and incident workflows, not as a business-calculation input;
2. `readiness` is published as source-owned readiness posture for UI and operator flows, not as a
   substitute for calculation-grade portfolio analytics.
3. deeper control-stage, reconciliation, and replay routes are now explicitly documented as
   second-hop operator investigation surfaces to use after `overview` or `readiness` exposes
   blocking, lagging, or replay-related problems.
4. calculator SLOs, valuation jobs, aggregation jobs, and analytics export-job listings now also
   document the escalation path from fleet-health baselining into specific stuck-workload
   investigation surfaces.

Malformed operator date filters are now also contractually separated from missing-portfolio
conditions: support routes that parse caller-supplied dates return `400 Bad Request` with an
explicit field-level message instead of collapsing malformed dates into `404 Not Found`. Support
overview is intentionally excluded from that list because it does not accept a caller-supplied
date filter. Reprocessing-job listings are also excluded because the route does not accept a
caller-supplied date filter.

Automated proof now includes:

1. reconciliation-evidence schema-family completeness checks;
2. ingestion-evidence schema-family completeness checks.

The HTTP dependency lane now also proves the default-query behavior for the two gateway-facing
support entry points: `overview` and `readiness` both have direct router-level coverage for the
canonical default stale-threshold and failed-window parameters, and readiness also proves the
`as_of_date=None` path used by callers that want source-owned latest-state evaluation.

The reconciliation-findings OpenAPI example now also reflects the more precise missing-run failure
mode instead of collapsing that route into a generic portfolio-only not-found example.

Fresh downstream validation on April 17, 2026 rechecked the active gateway path:

1. `lotus-gateway`: `python -m pytest tests\unit\test_upstream_clients.py::test_lotus_core_query_client_support_routes_use_control_plane_contract tests\unit\test_portfolio_service.py::test_portfolio_readiness_returns_compact_indicators tests\unit\test_portfolio_service.py::test_portfolio_service_reuses_support_overview_cache_across_workspace_as_of_dates tests\unit\test_portfolio_service.py::test_portfolio_readiness_surfaces_upstream_client_errors tests\unit\test_portfolio_service.py::test_portfolio_workspace_preserves_support_overview_partial_failure -q`
2. `lotus-gateway`: `python -m ruff check src\app\clients\lotus_core_query_client.py src\app\services\portfolio_service.py tests\unit\test_upstream_clients.py tests\unit\test_portfolio_service.py`

That evidence confirms gateway calls `overview` on the control-plane contract without unsupported
date shaping, calls `readiness` with the canonical optional `as_of_date` query parameter, preserves
support-overview partial failures in workspace composition, and surfaces upstream readiness
rejections instead of swallowing them.

Focused certification evidence on April 18, 2026 rechecked the deeper evidence routes directly:

1. `lotus-core`: `python -m pytest tests\unit\services\query_service\services\test_operations_service.py tests\unit\services\query_service\repositories\test_operations_repository.py tests\integration\services\query_control_plane_service\test_operations_router_dependency.py tests\integration\services\query_control_plane_service\test_control_plane_app.py -q`
2. Live probe: `GET /support/portfolios/PB_SG_GLOBAL_BAL_001/reconciliation-runs` returned two completed `timeseries_integrity` runs for `business_date=2026-04-17`, `epoch=13`, with `product_name=ReconciliationEvidenceBundle` and `product_version=v1`.
3. Live probe: `GET /support/portfolios/PB_SG_GLOBAL_BAL_001/reprocessing-keys` returned eleven current keys with explicit watermark dates, stale-state classification, and `product_name=IngestionEvidenceBundle`.
4. Live probe: `GET /support/portfolios/PB_SG_GLOBAL_BAL_001/reprocessing-jobs` returned an empty-but-explicit list with `total=0`, confirming the route publishes a truthful zero-backlog state rather than a missing-resource error.
5. Live probe: `GET /lineage/portfolios/PB_SG_GLOBAL_BAL_001/keys` returned eleven lineage keys with latest history/snapshot/valuation evidence and operator-facing `operational_state`.
6. Downstream code scan: `rg -n "reconciliation-runs|reprocessing-keys|reprocessing-jobs|lineage/portfolios" C:\Users\Sandeep\projects\lotus-gateway C:\Users\Sandeep\projects\lotus-risk C:\Users\Sandeep\projects\lotus-manage C:\Users\Sandeep\projects\lotus-report C:\Users\Sandeep\projects\lotus-advise` found no active direct product client binding for the deeper reconciliation, replay, or lineage routes.

### Issue Disposition For This Endpoint Family

| Issue | Status in this pass | Action |
| --- | --- | --- |
| `lotus-gateway #116` | Closed on April 16, 2026. Gateway has already adopted the main support/readiness hardening posture, so this broader umbrella issue is no longer the active tracking record for the family. | Keep closed unless a fresh broader support/readiness regression appears. |
| `lotus-gateway #124` | Closed on April 17, 2026. Gateway commit `d63d8e5` removed unsupported `as_of_date` shaping from `GET /support/portfolios/{portfolio_id}/overview`, stopped varying support-overview cache keys by workspace date, and kept readiness as the route that owns date-scoped validation. | Keep closed unless fresh gateway code reintroduces unsupported support-overview query shaping. |
| `lotus-manage #32` | Closed on April 17, 2026. Current manage repo truth still has no active outbound lotus-core support/source-data client, and the future-adoption posture is captured in manage's RFC-0082 upstream contract map rather than as an active defect. | Re-open only when a direct manage operator workflow binds to these routes and concrete client/test work is needed. |
| `lotus-report #37` | Closed on April 17, 2026 as completed review / no current direct adoption. Current report mainline has no direct benchmark, support, lineage, reconciliation, risk-free, classification, or `core-snapshot` client evidence; the only benchmark-related code found is an empty `benchmarkReturns` risk payload placeholder, not a lotus-core benchmark integration. | Re-open or replace only when report adds a direct benchmark/support/lineage workflow and concrete contract-alignment work exists. |
| `lotus-report #38` | Closed as stale adoption guidance. Report remains a catalog-intended support/evidence consumer, but no active direct client code was found and there is no live report-side workflow to fix. | Re-open or replace only when report adds a direct support/readiness/lineage workflow. |

## Certified Endpoint Slice: Holdings Operational Read Family

This certification pass covers:

1. `GET /portfolios/{portfolio_id}/positions`

### Route Contract Decision

The strategic route in this family is `GET /portfolios/{portfolio_id}/positions`.

The boundary is now explicit:

1. use `GET /portfolios/{portfolio_id}/positions` for governed HoldingsAsOf operational reads,
   including booked as-of state and optional projected holdings state;
2. use `as_of_date` when the consumer needs booked state on or before a specific business date;
3. use `include_projected=true` only when the consumer intentionally wants future-dated projected
   holdings beyond the latest booked business date;
4. do not treat this route as a substitute for performance, risk, or reporting-specific
   aggregations.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `GET /portfolios/{portfolio_id}/positions` | `lotus-gateway` | Correct. Gateway uses the strategic positions route for portfolio position-book workflows. |

Earlier gateway holdings-flow dependence on the deprecated sibling convenience route
`POST /reporting/cash-balances/query` has now been resolved in current local gateway repo truth and
is recorded later in this audit under the dedicated cash-balances slice and closure posture for
`lotus-gateway #119`.

### Upstream Integration Assessment

The current holdings route is strong and production-grade for the operational read purpose:

1. latest booked state resolves from daily position snapshots when available;
2. missing snapshot rows are supplemented from position history so downstream holdings reads do not
   collapse while snapshot materialization catches up;
3. fallback valuation continuity is preserved through latest snapshot valuation metadata when
   history-only rows are surfaced;
4. data-quality posture distinguishes `COMPLETE`, `PARTIAL`, `STALE`, and `UNKNOWN` instead of
   collapsing mixed-quality holdings into one opaque status;
5. held-since dates are derived per active epoch so downstream suitability, concentration, and
   private-banking review surfaces can reason about continuous holding periods correctly.

The main remaining risk is downstream route choice, not core implementation correctness.

### Swagger / OpenAPI Assessment

For this family, Swagger now makes the following explicit:

1. `GET /portfolios/{portfolio_id}/positions` is the strategic `HoldingsAsOf` operational read;
2. booked historical state versus projected-state usage is explicit in the route description and
   parameter descriptions;
3. the route is fenced away from performance, risk, and reporting-specific aggregation contracts;
4. the response schema now describes holdings rows as the governed `HoldingsAsOf` scope rather than
   a generic positions list.

Focused HTTP-level dependency proof exists in
`tests/integration/services/query_service/test_positions_router_dependency.py` for success, 404,
500, `as_of_date`, and `include_projected` forwarding behavior.

Service-level proof exists in `tests/unit/services/query_service/services/test_position_service.py`
for snapshot-backed latest state, history fallback, valuation continuity, held-since derivation,
projected-mode unbounded reads, and holdings data-quality classification.

OpenAPI proof exists in `tests/integration/services/query_service/test_main_app.py`, including the
route purpose, parameter descriptions, and `HoldingsAsOf` product identity.

### Issue Disposition For This Endpoint Family

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core #312` retire deprecated `POST /reporting/holdings-snapshot/query` compatibility route | Closed on 2026-04-16. The deprecated handler, DTOs, service path, route-catalog entries, and direct router/OpenAPI coverage were removed after fresh local scans showed no active downstream binding. | Keep closed unless fresh evidence shows a real consumer still depended on the retired compatibility route. |
| `lotus-gateway #119` deprecated `cash-balances/query` usage in holdings flows | Closed on 2026-04-16. Current gateway repo truth and remote issue closure both align to strategic `GET /portfolios/{portfolio_id}/cash-balances` adoption. | Keep closed unless fresh route-level evidence shows gateway reintroduced deprecated `cash-balances/query` usage. |

## Certified Endpoint Slice: Cash Balances Operational Read

This certification pass covers:

1. `GET /portfolios/{portfolio_id}/cash-balances`

### Route Contract Decision

`GET /portfolios/{portfolio_id}/cash-balances` is now the strategic `HoldingsAsOf` cash-account
balance publication route.

The boundary is now explicit:

1. use `GET /portfolios/{portfolio_id}/cash-balances` for new operational-read adoption that needs
   per-account cash balances or translated cash totals;
2. do not use the route as a substitute for broad holdings publication, performance output, or report
   composition;
3. use `GET /portfolios/{portfolio_id}/cash-accounts` only for cash-account identity and lifecycle
   metadata, not balances.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `GET /portfolios/{portfolio_id}/cash-balances` | `lotus-gateway`, `lotus-advise` | Active direct consumers are now evidenced on the strategic route. Gateway local repo truth uses `get_portfolio_cash_balances(...)` for workspace, book, and liquidity cash-account views, and advise stateful context uses the same route for per-currency cash balances. |

No active direct `lotus-report` consumer was evidenced in this pass.

### Upstream Integration Assessment

The strategic route is now strong for the intended contract:

1. it publishes per-account native cash balances together with portfolio-currency and
   reporting-currency restatement;
2. it exposes enough per-currency detail for advisory state and gateway liquidity views;
3. it keeps cash-account balance publication explicit instead of forcing downstream reconstruction
   from broad holdings payloads or account master records;
4. `GET /portfolios/{portfolio_id}/cash-accounts` intentionally remains identity metadata only.

Fresh live evidence on April 18, 2026 for `PB_SG_GLOBAL_BAL_001` shows the strategic route
returning two populated operating cash accounts with truthful translated totals:

1. `CASH-ACC-USD-001` / `CASH_USD_BOOK_OPERATING` = `101347.0000000000` USD;
2. `CASH-ACC-EUR-001` / `CASH_EUR_BOOK_OPERATING` = `19805.5000000000` EUR,
   `21943.7611965000` USD translated;
3. `totals.total_balance_portfolio_currency` = `123290.7611965000`.

### Swagger / OpenAPI Assessment

For this endpoint, Swagger now makes the following explicit:

1. `GET /portfolios/{portfolio_id}/cash-balances` is the strategic `HoldingsAsOf` balance read;
2. broader holdings or reporting composition should not anchor on this route;
3. endpoint-specific cash balance fields carry clearer examples for cash-account identity,
   balances, totals, portfolio currency, reporting currency, and resolved as-of date.

Focused HTTP-level dependency proof exists in
`tests/integration/services/query_service/test_cash_balances_router.py` for strategic route
routing, parameter forwarding, shared `500` envelope behavior, and 404/400 mapping behavior.

Service-level proof exists in `tests/unit/services/query_service/services/test_cash_balance_service.py`
for translated totals, account-level balance resolution, zero-balance account handling, and product
identity metadata.

OpenAPI proof exists in `tests/integration/services/query_service/test_main_app.py`, including the
route-purpose wording and endpoint-specific schema examples.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core #308` strategic `HoldingsAsOf` cash-account balance gap | Closed. lotus-core now publishes `GET /portfolios/{portfolio_id}/cash-balances` and the implementation evidence has been recorded. | Re-open only if a fresh downstream requirement exposes a real gap in the strategic route. |
| `lotus-core #310` retire deprecated `POST /reporting/cash-balances/query` compatibility route | Closed on 2026-04-16. The deprecated handler, request DTO, reporting-service bridge, route-catalog entries, and direct router/OpenAPI coverage were removed after internal downstream scans plus remote gateway closure evidence showed no active binding. | Keep closed unless fresh evidence shows a real consumer still depended on the retired compatibility route. |
| `lotus-gateway #119` deprecated `cash-balances/query` usage in holdings flows | Closed on 2026-04-16. Current gateway repo truth and remote issue closure both align to strategic `GET /portfolios/{portfolio_id}/cash-balances` adoption. | Keep closed unless fresh route-level evidence shows gateway reintroduced deprecated `cash-balances/query` usage. |
| `lotus-gateway #134` foundation workspace cash summary remains zero despite populated strategic cash balances | Still valid on 2026-04-18. Fresh live evidence shows gateway workspace `allocations[Cash].market_value_base = 123290.76` while `summary.total_cash_base = 0.0` and `cash_weight_pct = 0.0`, even though lotus-core now returns populated `GET /portfolios/{portfolio_id}/cash-balances` totals for the same as-of date. | Keep open in gateway until workspace summary mapping uses the strategic cash-balance payload consistently with the already-correct cash allocation block. |
| `lotus-advise #92` downstream adoption of enrichment/state route hardening | Closed on current repo truth. Advise stateful context now uses `GET /portfolios/{portfolio_id}/cash-balances`, and the remaining active advise bindings stay aligned with the hardened enrichment/state routes. | Re-open only if a later core contract change exposes advise-side drift. |

## Certified Endpoint Slice: Cash Account Master Operational Read

This certification pass covers:

1. `GET /portfolios/{portfolio_id}/cash-accounts`

### Route Contract Decision

This is the correct strategic route for cash-account master data.

The contract boundary is explicit:

1. use this route for canonical cash-account identity, currency, role, and lifecycle metadata;
2. use `as_of_date` when the caller needs the account set filtered by open/close window on a
   specific business date;
3. do not use this route as a liquidity or balance view, because it intentionally does not publish
   native balances or translated cash totals;
4. when a downstream workflow genuinely needs per-account balances, use
   `GET /portfolios/{portfolio_id}/cash-balances`.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `GET /portfolios/{portfolio_id}/cash-accounts` | No active direct downstream caller evidenced in this pass | Correct strategic contract with no overstated live adoption. Gateway, manage, and support remain the intended operational consumers for account-master workflows, but this pass did not find product code that should be described as a current direct binding. |

This matters because downstreams should not be pushed onto the cash-account master route where
they actually need balances. The absence of a live direct consumer here is not a route defect; it
is consistent with current product behavior, where gateway and advise mostly need cash-account
balances rather than master-data-only publication.

### Upstream Integration Assessment

The route is tight and production-grade for its intended purpose:

1. it checks portfolio existence before returning account-master rows, so missing scope fails
   truthfully as `404`;
2. it publishes source-owned identifiers, linked cash security, account currency, optional role,
   lifecycle status, open date, close date, and source system without mixing in balance semantics;
3. it supports as-of filtering through account open/close windows, which is the right operational
   read behavior for historical support and evidence workflows;
4. it keeps cash-account identity publication separate from cash-balance publication, which avoids
   ambiguous mixed-purpose payloads.

The adjacent strategic balance-publication gap is now closed by
`GET /portfolios/{portfolio_id}/cash-balances`. That remains adjacent to this endpoint rather than
a flaw in this endpoint.

### Swagger / OpenAPI Assessment

For this endpoint, Swagger now makes the following explicit:

1. this route publishes canonical cash-account master records, not balances;
2. `portfolio_id` and `as_of_date` parameter purpose is explicit;
3. response attributes now carry endpoint-specific descriptions and a concrete account example;
4. the description explains when to use this route and when to use the balance route instead.

Focused HTTP-level dependency proof exists in
`tests/integration/services/query_service/test_cash_accounts_router.py` for success, explicit
`as_of_date` forwarding, omitted-`as_of_date` behavior, shared `500` envelope behavior, and `404`
mapping.

Repository-level query proof exists in
`tests/unit/services/query_service/repositories/test_cash_account_repository.py` for
portfolio-existence checks, open/close-window filtering, and deterministic ordering.

Service-level proof exists in
`tests/unit/services/query_service/services/test_cash_account_service.py` for master-record
serialization and truthful not-found handling.

OpenAPI proof exists in `tests/integration/services/query_service/test_main_app.py`, including the
route-purpose wording, parameter descriptions, and cash-account response examples.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core #308` strategic `HoldingsAsOf` cash-account balance gap | Closed. It was never a defect in `GET /portfolios/{portfolio_id}/cash-accounts` itself. This route remains intentionally metadata-only. | Keep closed against the strategic cash-balance route unless a fresh gap appears. |
| `lotus-gateway #119` deprecated `cash-balances/query` usage in holdings flows | Closed on 2026-04-16. Adjacent only. Current gateway truth is aligned to `GET /portfolios/{portfolio_id}/cash-balances`, not `GET /portfolios/{portfolio_id}/cash-accounts`. | Keep closed unless fresh route-level evidence shows deprecated cash-balance-route reintroduction. |
| `lotus-manage #32` review latest lotus-core support and source-data contract hardening for operator adoption | Closed on April 17, 2026. It was broader future-adoption guidance rather than a cash-account-master defect, and current manage repo truth still has no active outbound lotus-core client for this family. | Keep closed unless a future manage workflow directly adopts lotus-core support/source-data routes and needs repo-local implementation work. |

## Certified Endpoint Slice: Income And Activity Compatibility Route Retirement

This certification pass closes the remaining retirement work for:

1. `POST /reporting/income-summary/query`
2. `POST /reporting/activity-summary/query`

### Route Contract Decision

Both deprecated compatibility routes are now retired from the active lotus-core contract surface.
The strategic source-data route for downstream summary derivation is
`GET /portfolios/{portfolio_id}/transactions`.

The decision is now explicit:

1. gateway migration is complete via issue `#122`;
2. local `lotus-report` migration exists in commit `bd866ef`, deriving both summaries from the
   strategic transaction ledger, and follow-on commit `0254c71` removed the stale report
   `core-snapshot` client seam;
3. no active direct internal consumer was evidenced in current local repo truth;
4. the last internal lotus-core dependency, `tools/front_office_portfolio_seed.py`, now derives
   readiness summary signals from the strategic transaction ledger instead of calling the retired
   routes.

### Downstream Consumer Reality

| Former route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /reporting/income-summary/query` | None evidenced as still active | Retired. Strategic replacement is `GET /portfolios/{portfolio_id}/transactions`. |
| `POST /reporting/activity-summary/query` | None evidenced as still active | Retired. Strategic replacement is `GET /portfolios/{portfolio_id}/transactions`. |

No active direct `lotus-advise`, `lotus-risk`, or `lotus-manage` consumer was evidenced against
these shapes in this pass.

### Upstream Integration Assessment

The upstream contract posture is stronger after retirement:

1. lotus-core now exposes one strategic transaction-ledger route instead of parallel ledger and
   compatibility summary shapes;
2. internal front-office seed verification keeps the readiness signal by deriving canonical income
   and flow-bucket presence from transaction-ledger rows;
3. dead summary-specific repository and service aggregation paths are removed, reducing maintenance
   surface and eliminating stale OpenAPI surface area.

### Swagger / OpenAPI Assessment

The retired routes are removed from active Swagger and contract-family inventory. The strategic
transaction-ledger route remains the documented `TransactionLedgerWindow` contract for downstream
reporting, audit, and UI summary derivation.

### Validation Evidence

Focused retirement proof:

1. `python -m pytest tests\\unit\\tools\\test_front_office_portfolio_seed.py -q`
2. `python -m pytest tests\\integration\\services\\query_service\\test_reporting_router.py tests\\integration\\services\\query_service\\test_main_app.py tests\\unit\\services\\query_service\\services\\test_reporting_service.py tests\\unit\\services\\query_service\\dtos\\test_reporting_dto.py tests\\unit\\services\\query_service\\dtos\\test_source_data_product_identity.py tests\\unit\\services\\query_service\\repositories\\test_reporting_repository.py tests\\unit\\tools\\test_front_office_portfolio_seed.py tests\\unit\\libs\\portfolio-common\\test_source_data_products.py -q`
3. `python scripts\\openapi_quality_gate.py`
4. `python scripts\\api_vocabulary_inventory.py --validate-only`
5. `python scripts\\route_contract_family_guard.py`

### Issue Disposition For These Endpoints

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core #309` | Closed on April 16, 2026. The strategic transaction-ledger contract now supports optional `reporting_currency` restatement and publishes explicit reporting-currency transaction amount fields required for downstream income/activity summary derivation. | Keep closed unless fresh evidence shows the strategic ledger still cannot replace the deprecated summary compatibility routes for valid downstream reporting use cases. |
| `lotus-gateway #122` | Closed on 2026-04-16. Current gateway repo truth derives both UI-facing summaries from strategic `GET /portfolios/{portfolio_id}/transactions`. | Keep closed unless fresh route-level evidence shows gateway reintroduced deprecated summary-route calls. |
| `lotus-report #39` | Closed on April 17, 2026 after merged PR `lotus-report #41`. Report now derives both summary sections from strategic `GET /portfolios/{portfolio_id}/transactions`, removed the stale `core-snapshot` client seam, refreshed the report monetary-float baseline for the refactored output paths, and passed remote PR Merge Gate run `24554406140`, including lint/type/security, unit, integration, e2e, 99% combined coverage, workflow lint, and Docker build. | Keep closed unless fresh report code reintroduces deprecated summary-route calls or stale `core-snapshot` report composition. |
| `lotus-core #311` retire deprecated income/activity summary compatibility routes | Closed on April 17, 2026. The deprecated handlers, dead DTOs/service/repository paths, source-data catalog/registry/vocabulary references, and stale tests/docs were removed after downstream retirement checks. | Keep closed unless fresh evidence shows a real external dependency still needs the retired compatibility routes. |

## Certified Endpoint Slice: Assets Under Management Operational Read

This certification pass covers:

1. `POST /reporting/assets-under-management/query`

### Route Contract Decision

This is the strategic lotus-core AUM route for governed source-owned assets-under-management
figures.

The boundary is explicit:

1. use it for one-portfolio, portfolio-list, or booking-center AUM totals and per-portfolio AUM
   breakdowns;
2. prefer it over reconstructing AUM downstream from holdings rows when the downstream need is a
   governed AUM figure;
3. keep holdings publication, summary composition, and narrative reporting outside this route;
4. treat it as an AUM operational read, not as a replacement for detailed holdings state.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /reporting/assets-under-management/query` | `lotus-gateway` | Correct. Gateway uses the dedicated route as the source-owned AUM input for portfolio workspace, liquidity, allocation, and position-book summary framing. |

No active direct `lotus-report`, `lotus-advise`, `lotus-risk`, or `lotus-manage` consumer was
evidenced against this route in this pass.

### Upstream Integration Assessment

The route is strong and domain-correct for PB/WM AUM needs:

1. AUM is computed upstream from the governed snapshot scope rather than reconstructed by each
   downstream consumer;
2. reporting-currency restatement is source-owned and available where the scope requires it;
3. one-portfolio and aggregated scope behavior are explicit rather than hidden in consumer-specific
   heuristics;
4. the route stays narrowly focused on AUM figures and per-portfolio AUM breakdowns.

### Swagger / OpenAPI Assessment

For this endpoint, Swagger now makes the following explicit:

1. this is the source-owned AUM route for a resolved reporting scope;
2. consumers should prefer it over reconstructing AUM from holdings rows when the need is a
   governed AUM figure;
3. the route is distinct from broad holdings publication and summary composition;
4. response fields now carry clearer examples for resolved as-of date, reporting currency, AUM
   totals, and position counts.

Focused HTTP-level dependency proof exists in
`tests/integration/services/query_service/test_reporting_router.py` for successful AUM routing.

Service-level proof exists in `tests/unit/services/query_service/services/test_reporting_service.py`
for single-portfolio defaults, portfolio-list reporting-currency handling, and multi-position AUM
aggregation.

OpenAPI proof exists in `tests/integration/services/query_service/test_main_app.py`, including the
route-purpose wording and endpoint-specific schema examples.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core` | No open issue | No open lotus-core behavior or documentation defect remains evidenced against `POST /reporting/assets-under-management/query` in this pass. |
| `lotus-gateway` | No open route-specific issue needed | Gateway is already using the dedicated AUM route directly and propagates reporting currency where supported. |

## Certified Endpoint Slice: Cashflow Projection Operational Read

This certification pass covers:

1. `GET /portfolios/{portfolio_id}/cashflow-projection`

### Route Contract Decision

This is the strategic lotus-core operational-read route for portfolio cashflow outlook.

The boundary is explicit:

1. use it when a downstream consumer needs a dedicated portfolio-level daily cashflow outlook for a
   chosen horizon;
2. use booked-only versus projected mode honestly rather than inferring one from the other;
3. do not use it as a substitute for broad portfolio state, performance forecasting, or advisory
   recommendation logic;
4. keep the route anchored to core-derived cashflow state rather than consumer-specific narrative
   interpretation.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `GET /portfolios/{portfolio_id}/cashflow-projection` | `lotus-gateway` | Correct. Gateway uses the route for the dedicated projected cashflow view and propagates `as_of_date`, `horizon_days`, and `include_projected` directly to lotus-core. |

No active direct `lotus-report`, `lotus-advise`, `lotus-risk`, or `lotus-manage` consumer was
evidenced against this route in this pass.

### Upstream Integration Assessment

The route is strong and domain-correct for operational liquidity planning:

1. it publishes an explicit portfolio-level daily net cashflow path instead of forcing downstream
   consumers to infer one from transaction rows;
2. booked-only mode and projected mode are explicit request choices;
3. the contract stays focused on liquidity outlook rather than drifting into performance
   forecasting;
4. the dependency lane already proves success, parameter forwarding, and 404 behavior through the
   ASGI surface.

Fresh live evidence on April 18, 2026 for `PB_SG_GLOBAL_BAL_001` confirms projected settlement
cashflow handling is now truthful for future-dated withdrawals:

1. `points[2026-04-20].net_cashflow = -18000.0000000000`;
2. `total_net_cashflow = -18000.0000000000`;
3. booked-only days around that settlement remain zero rather than double-counted.

### Swagger / OpenAPI Assessment

For this endpoint, Swagger now makes the following explicit:

1. this route serves portfolio-level daily cashflow outlook for operational liquidity planning;
2. booked-only versus projected mode semantics are explicit;
3. forecasting, performance analytics, and advisory recommendation logic stay outside this
   contract;
4. parameter descriptions and 404 example remain clear and specific.

Focused HTTP-level dependency proof exists in
`tests/integration/services/query_service/test_cashflow_projection_router_dependency.py` for
success, parameter forwarding, truthful `404` mapping, and shared `500` envelope behavior on
unexpected failures.

OpenAPI proof exists in `tests/integration/services/query_service/test_main_app.py`, including the
route-purpose wording and request-parameter descriptions.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core` | No open issue | No open lotus-core behavior or documentation defect remains evidenced against `GET /portfolios/{portfolio_id}/cashflow-projection` in this pass. |
| `lotus-gateway` | No open route-specific issue needed | Gateway is already using the dedicated projected cashflow route correctly. |

## Certified Endpoint Slice: Transaction Ledger Operational Read

This certification pass covers:

1. `GET /portfolios/{portfolio_id}/transactions`

### Route Contract Decision

This is the strategic lotus-core operational-read route for governed transaction-ledger rows.

The boundary is explicit:

1. use it when a downstream consumer needs canonical transaction-ledger rows rather than summary
   aggregates;
2. use holdings drill-down, instrument-specific filters, and FX/event filters intentionally instead
   of reconstructing economic-event views client-side;
3. keep summary income/activity reporting and performance interpretation outside this route;
4. preserve paging and explicit sorting as part of the governed ledger contract.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `GET /portfolios/{portfolio_id}/transactions` | `lotus-gateway`, `lotus-report` | Correct. Gateway exposes the strategic ledger route with the advanced instrument, FX/event, paging, and explicit sorting controls documented and regression-covered. Merged report PR `#41` derives income/activity sections from this strategic ledger route instead of the deprecated summary compatibility routes, removes the old `core-snapshot` read path from report review composition, and passed the remote PR Merge Gate (`24554406140`). |

No active direct `lotus-advise`, `lotus-risk`, or `lotus-manage` consumer was evidenced against
this route in this pass.

### Upstream Integration Assessment

The route is strong and domain-correct for operational ledger inspection:

1. it publishes canonical ledger rows with date-window, holdings drill-down, FX, and linked-event
   filter support;
2. explicit sort and pagination controls make the ledger stable for UI and operational use;
3. it now supports optional `reporting_currency` restatement on summary-relevant monetary fields so
   downstream reporting surfaces can migrate off deprecated income/activity summary routes without
   reimplementing upstream FX logic;
4. the route stays row-oriented and does not collapse into summary reporting or performance logic;
5. invalid reporting-currency restatement now fails as a truthful `400` instead of being miscast as
   a missing-portfolio `404`;
6. OpenAPI descriptions now make the advanced filter surface and reporting-currency behavior more
   explicit for downstream consumers.

### Swagger / OpenAPI Assessment

For this endpoint, Swagger now makes the following explicit:

1. this is the strategic `TransactionLedgerWindow` operational read for one portfolio;
2. holdings, instrument, and FX/event filters are part of the governed contract;
3. optional `reporting_currency` restatement is available for downstream reporting or aggregation
   workflows that still need row-level truth;
4. explicit sorting remains part of the route semantics;
5. `400` and `404` examples and transaction field descriptions remain clear and specific.

OpenAPI proof exists in `tests/integration/services/query_service/test_main_app.py`, including the
advanced filter descriptions and strategic route wording.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core #309` | Closed on April 16, 2026. The route now exposes optional reporting-currency-restated monetary fields plus truthful `400` handling for unsupported FX conversion requests. | Keep closed unless a fresh parity gap is evidenced after downstream migration work starts consuming the new contract surface. |
| `lotus-gateway #120` advanced transaction-ledger filter posture | Closed on 2026-04-16. Current gateway repo truth exposes the strategic ledger's instrument, FX/event, and explicit sorting controls on `/api/v1/portfolio/portfolios/{portfolio_id}/transactions`, and gateway contract/integration tests now pin that surface. | Keep closed unless fresh gateway code or OpenAPI evidence shows the advanced ledger controls were narrowed again. |
| `lotus-gateway #122` deprecated income/activity summary migration | Closed on 2026-04-16. Current gateway repo truth derives both UI-facing summaries from strategic `GET /portfolios/{portfolio_id}/transactions`. | Keep closed unless fresh gateway evidence shows deprecated summary-route calls were reintroduced. |
| `lotus-report #39` deprecated income/activity summary migration | Closed on April 17, 2026 after merged PR `lotus-report #41`. Current report mainline truth derives both summary sections from strategic `GET /portfolios/{portfolio_id}/transactions`, has no `src` or `tests` references to the retired income/activity summary routes, adds edge-case coverage for transaction pagination/error mapping and income/activity amount fallbacks, and passed remote PR Merge Gate run `24554406140`. | Keep closed unless fresh report code reintroduces deprecated summary-route calls. |

## Certified Endpoint Slice: BUY / SELL Investigative State Reads

This certification pass covers:

1. `GET /portfolios/{portfolio_id}/positions/{security_id}/lots`
2. `GET /portfolios/{portfolio_id}/positions/{security_id}/accrued-offsets`
3. `GET /portfolios/{portfolio_id}/transactions/{transaction_id}/cash-linkage`
4. `GET /portfolios/{portfolio_id}/positions/{security_id}/sell-disposals`
5. `GET /portfolios/{portfolio_id}/transactions/{transaction_id}/sell-cash-linkage`

### Route Contract Decision

These routes are correct and intentionally narrow investigative reads.

The contract boundary is explicit:

1. use them for transaction-state audit, reconciliation, support investigation, disposal tracing,
   and settlement-linkage proof;
2. do not use them as general holdings, cash-balance, portfolio cashflow, performance, or
   reporting-summary routes;
3. treat them as support-plane operational evidence for BUY/SELL lifecycle state, not as the
   default downstream portfolio workspace read model.

### Downstream Consumer Reality

| Route family | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| BUY / SELL investigative state reads | No active direct downstream caller evidenced in `lotus-gateway`, `lotus-manage`, or `lotus-report` during this pass | Correct investigative support contract with no overstated live front-office adoption. The family remains catalog-correct for gateway and support troubleshooting use cases, but this pass did not find product code that should be described as an active direct dependency. |

That is a healthy result rather than a defect. These routes exist to answer narrow operational
questions about lots, accrual offsets, and security-to-cash linkage. They should not be forced into
front-office product flows when broader portfolio or reporting routes already satisfy the use case.

### Upstream Integration Assessment

The family is strong for its intended purpose:

1. BUY lot state publishes acquisition-date, quantity, basis, and policy/linkage metadata needed
   for private-banking auditability;
2. BUY accrued-offset state keeps fixed-income accrued-interest offsets explicit instead of forcing
   downstream inference from transaction rows;
3. BUY and SELL cash-linkage routes publish the persisted transaction-to-cash relationship needed
   for deterministic reconciliation;
4. SELL disposal state exposes disposed quantity, disposed basis, realized gain/loss, and policy
   metadata in a way that remains readable for audit and support workflows;
5. the service layer now preserves truthful `404` behavior for missing portfolios, missing
   transaction linkage, and missing persisted BUY/SELL security-key state rather than collapsing
   investigative misses into empty generic payloads.

Fresh live evidence on April 18, 2026 for `PB_SG_GLOBAL_BAL_001` confirms the strategic
investigative reads are behaving consistently with the seeded ledger:

1. `GET /portfolios/PB_SG_GLOBAL_BAL_001/positions/FO_EQ_AAPL_US/lots` returns the original BUY
   lot with `original_quantity = 420.0` and corrected `open_quantity = 310.0`;
2. `GET /portfolios/PB_SG_GLOBAL_BAL_001/positions/FO_EQ_AAPL_US/sell-disposals` returns the SELL
   disposal with `quantity_disposed = 110.0000000000`,
   `disposal_cost_basis_base = 20295.0000000000`, and
   `realized_gain_loss_base = 2519.0000000000`.

No upstream defect was found in this pass. The family is narrow by design, and that narrowness is
appropriate.

### Swagger / OpenAPI Assessment

For this family, Swagger now makes the following explicit:

1. each route is framed as an investigative BUY/SELL state endpoint, not a broad portfolio read;
2. when-to-use and when-not-to-use guidance is explicit in the route descriptions;
3. security and transaction path parameters are documented with endpoint-specific descriptions;
4. concrete `404` examples exist for BUY state, SELL state, and both cash-linkage routes.

Focused HTTP-level dependency proof exists in
`tests/integration/services/query_service/test_buy_state_router.py` and
`tests/integration/services/query_service/test_sell_state_router.py` for success and `404`
behavior across the family, including missing persisted portfolio-security investigative state.

Service-level proof exists in `tests/unit/services/query_service/services/test_buy_state_service.py`
and `tests/unit/services/query_service/services/test_sell_state_service.py` for mapping of lot,
offset, disposal, proceeds, cash-linkage semantics, and missing-state investigative `404` mapping.

Repository-level proof exists in
`tests/unit/services/query_service/repositories/test_buy_state_repository.py` and
`tests/unit/services/query_service/repositories/test_sell_state_repository.py` for the underlying
BUY/SELL query joins and filters.

OpenAPI proof exists in `tests/integration/services/query_service/test_main_app.py`, including the
route-purpose wording, parameter descriptions, and concrete investigative not-found examples.

### Issue Disposition For This Endpoint Family

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core #314` FIFO lot open-quantity drift on BUY / SELL investigative state | Fixed in current local worktree and freshly revalidated on 2026-04-18. Live lot evidence for `PB_SG_GLOBAL_BAL_001` now shows `open_quantity = 310.0` for `TXN-BUY-AAPL-001` after the 110-share SELL, matching the disposal route and seeded transaction history. | Keep open until the implementing change is merged, then close with the recorded lot/disposal evidence and focused unit/integration regression tests. |
| Downstream repos | No open issue found in this pass | No downstream misuse or stale-contract binding was evidenced for these endpoints, so no new issue was opened. |

## Certified Endpoint Slice: Portfolio Discovery And Detail Reads

This certification pass covers:

1. `GET /portfolios/`
2. `GET /portfolios/{portfolio_id}`

### Route Contract Decision

These routes are the correct strategic portfolio identity reads.

The boundary is explicit:

1. use `GET /portfolios/` for discovery, selector population, navigation scope lookup, and
   operator filtering by portfolio, client grouping, or booking center;
2. use `GET /portfolios/{portfolio_id}` for the canonical portfolio identity and standing record
   for one portfolio;
3. do not treat either route as a substitute for workspace composition, positions, transactions,
   cashflow outlook, or reporting contracts.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `GET /portfolios/` | `lotus-gateway` | Correct. Gateway actively calls the canonical discovery route through its portfolio catalog service for `/api/v1/portfolio/portfolios`, while its foundation selector surface uses the dedicated lookup contract instead of overloading this broader discovery read. |
| `GET /portfolios/{portfolio_id}` | `lotus-gateway` | Correct. Gateway actively calls the canonical single-portfolio detail route before composing downstream workspace and related portfolio views. |

The split still matters. Gateway uses the broader discovery route for portfolio catalog views and
the single-portfolio identity route for workspace composition, while foundation selector flows use
the narrower `/lookups/portfolios` contract instead of treating discovery as a generic lookup API.

### Upstream Integration Assessment

The route pair is strong and appropriately narrow:

1. list discovery supports exact portfolio ID, multi-portfolio ID, client grouping, and booking
   center filters with deterministic ordering;
2. single-portfolio detail publishes canonical identity, lifecycle, advisory, booking-center, and
   cost-basis metadata without bleeding into holdings or reporting concerns;
3. single-portfolio detail now aligns to the newer route pattern by raising explicit lookup misses
   rather than generic value errors inside the service layer;
4. unexpected failures on discovery now fall through to the shared global error envelope instead of
   emitting one-off router-local `500` strings;
5. not-found behavior for single-portfolio detail is truthful and explicit;
6. the pair keeps identity/discovery separate from broader portfolio-state composition, which is
   the right operational-read boundary for downstream systems.

No upstream defect was found in this pass.

### Swagger / OpenAPI Assessment

For these endpoints, Swagger now makes the following explicit:

1. `GET /portfolios/` is for discovery and navigation scope, not detailed portfolio state;
2. `GET /portfolios/{portfolio_id}` is for canonical single-portfolio identity and standing
   metadata;
3. when-not-to-use guidance fences both routes away from positions, transactions, and reporting;
4. filter parameter descriptions, schema field descriptions, and single-portfolio `404` examples
   are explicit.

Focused HTTP-level dependency proof exists in
`tests/integration/services/query_service/test_portfolios_router_dependency.py` for success,
single-portfolio lookup, `404`, and filter forwarding behavior.

Service-level proof exists in
`tests/unit/services/query_service/services/test_portfolio_service.py` for DTO mapping, empty-list
behavior, single-portfolio lookup, DTO normalization, and not-found handling.

Repository-level proof exists in
`tests/unit/services/query_service/repositories/test_query_portfolio_repository.py` for no-filter
reads, exact-ID filters, multi-ID filters, client/booking-center filters, ordering, and single-ID
lookup.

OpenAPI proof exists in `tests/integration/services/query_service/test_main_app.py`, including the
route-purpose wording, field descriptions, and single-portfolio not-found example.

### Issue Disposition For This Endpoint Family

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core` | No open issue found in this pass | No lotus-core defect was found against the portfolio discovery/detail routes. |
| Downstream repos | No open issue found in this pass | No stale or incorrect downstream contract usage was evidenced for these endpoints, so no new issue was opened. |

## Certified Endpoint Slice: Position History Operational Read

This certification pass covers:

1. `GET /portfolios/{portfolio_id}/position-history`

### Route Contract Decision

This is the correct strategic lotus-core route for historical security-level position-state
inspection.

The boundary is explicit:

1. use it when a downstream consumer needs dated position-history rows for one security inside one
   portfolio;
2. use optional `start_date` and `end_date` filters to narrow the investigative window honestly;
3. do not use it as a substitute for the strategic latest-holdings read, transaction-ledger rows,
   or reporting summary contracts.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `GET /portfolios/{portfolio_id}/position-history` | No active direct downstream caller evidenced in `lotus-gateway`, `lotus-manage`, or `lotus-report` during this pass | Correct investigative holdings-history contract with no overstated live adoption. The route remains catalog-correct for gateway and support drill-down use cases, but this pass did not find product code that should be described as a current direct binding. |

That is acceptable. This route is narrower than the strategic latest-holdings read and should stay
that way.

### Upstream Integration Assessment

The route is strong for its intended purpose:

1. it publishes dated position-history rows for one portfolio-security key;
2. it now aligns to the shared query-service error posture: lookup misses map to truthful `404`
   while unexpected failures fall through to the global `500` envelope rather than bespoke
   router-local error strings;
3. it keeps historical security-state inspection separate from latest holdings and transaction
   ledger publication;
4. service-level tests already cover not-found handling and history-row mapping.

No upstream defect was found in this pass.

### Swagger / OpenAPI Assessment

For this endpoint, Swagger now makes the following explicit:

1. the route is for holdings-history drill-down and troubleshooting, not broad portfolio state;
2. when-not-to-use guidance fences the route away from latest holdings, ledger, and reporting
   reads;
3. `security_id`, `start_date`, and `end_date` semantics remain explicit;
4. the `404` example and position-history response-field descriptions are explicit.

Focused HTTP-level dependency proof exists in
`tests/integration/services/query_service/test_positions_router_dependency.py` for success, `404`,
and `500` behavior.

Service-level proof exists in `tests/unit/services/query_service/services/test_position_service.py`
for history-row mapping and truthful not-found handling.

Repository-level proof exists in
`tests/unit/services/query_service/repositories/test_unit_query_position_repo.py`.

OpenAPI proof exists in `tests/integration/services/query_service/test_main_app.py`, including the
route-purpose wording, parameter descriptions, and `404` example.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core #56` OpenAPI 404 contract gap | Already closed. Current route truth still matches the closure rationale: `GET /portfolios/{portfolio_id}/position-history` documents `404` in OpenAPI and the contract remains covered by current integration tests. | Keep closed. No new lotus-core issue is needed for this route in this pass. |
| Downstream repos | No open issue found in this pass | No downstream misuse or stale-contract binding was evidenced for this route, so no new issue was opened. |

## Certified Endpoint Slice: Reference Market Data Reads

This certification pass covers:

1. `GET /instruments/`
2. `GET /prices/`
3. `GET /fx-rates/`

### Route Contract Decision

These routes are the correct strategic raw reference-data reads.

The boundary is explicit:

1. use `GET /instruments/` for canonical security-master lookup and reference-data diagnostics;
2. use `GET /prices/` for source-owned security price history;
3. use `GET /fx-rates/` for source-owned FX conversion history;
4. do not use these routes as substitutes for holdings state, portfolio valuation outputs,
   performance analytics, risk analytics, or reporting aggregates.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `GET /instruments/` | `lotus-advise` | Correct. Advise uses the raw instrument read as part of stateful context resolution for proposal construction support, while still preferring strategic enrichment for classification-heavy analytics semantics. |
| `GET /prices/` | `lotus-advise` | Correct. Advise uses the raw price-history read as part of stateful context valuation support for proposal construction and simulation inputs. |
| `GET /fx-rates/` | `lotus-advise`, `lotus-performance` | Correct. Advise uses the raw FX-history read for stateful context currency support, and performance directly uses it for multi-currency benchmark/performance workflows. |

That posture is acceptable. These are foundational raw reads and the active downstream uses remain
supporting seams inside broader stateful workflows rather than user-facing portfolio or reporting
contracts in their own right.

### Upstream Integration Assessment

The family is strong for its intended purpose:

1. instrument lookup stays limited to canonical reference master fields with pagination and product
   filtering;
2. price history stays scoped to one security plus an optional date window;
3. FX history stays scoped to one currency pair plus an optional date window, with router-level
   currency canonicalization to uppercase;
4. unexpected failures now have focused HTTP-level coverage proving the family falls through to the
   shared global `500` envelope instead of bespoke router-local error strings;
5. the family keeps raw market/reference publication separate from derived portfolio analytics and
   report composition.

No upstream defect was found in this pass.

### Swagger / OpenAPI Assessment

For this family, Swagger now makes the following explicit:

1. each route publishes raw reference or market-data history rather than derived portfolio output;
2. when-to-use and when-not-to-use guidance is explicit on all three routes;
3. request parameter descriptions remain specific for security ID, product type, currencies, and
   date-window filters;
4. response schema field descriptions are explicit for instrument pages, price records, and FX
   rate records.

Focused HTTP-level dependency proof exists in
`tests/integration/services/query_service/test_reference_data_routers.py` for instrument, price,
and FX success behavior plus shared-envelope unexpected failure behavior.

Service-level proof exists in
`tests/unit/services/query_service/services/test_instrument_service.py`,
`tests/unit/services/query_service/services/test_price_service.py`, and
`tests/unit/services/query_service/services/test_fx_rate_service.py`.

Repository-level proof exists in
`tests/unit/services/query_service/repositories/test_instrument_repository.py`,
`tests/unit/services/query_service/repositories/test_price_repository.py`, and
`tests/unit/services/query_service/repositories/test_fx_rate_repository.py`.

OpenAPI proof exists in `tests/integration/services/query_service/test_main_app.py`, including the
route-purpose wording, parameter descriptions, and response-schema field descriptions.

### Issue Disposition For This Endpoint Family

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core` | No open issue found in this pass | No lotus-core defect was found against the raw reference market-data routes. |
| Downstream repos | No open issue found in this pass | Active direct bindings in `lotus-advise` and `lotus-performance` are strategically acceptable for this raw-data family, so no new issue was opened. |

## Certified Endpoint Slice: Lookup Catalog Reads

This certification pass covers:

1. `GET /lookups/portfolios`
2. `GET /lookups/instruments`
3. `GET /lookups/currencies`

### Route Contract Decision

These routes are the correct strategic selector-catalog reads.

The boundary is explicit:

1. use them for thin UI and gateway selector catalogs only;
2. do not use them as substitutes for canonical portfolio detail, canonical instrument reference,
   FX-rate history, or broader portfolio/reporting reads;
3. keep them limited to stable `id` / `label` selector payloads rather than expanding them into
   generic data APIs.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `GET /lookups/portfolios` | `lotus-gateway` | Correct. Gateway has an explicit lotus-core client binding and contract/integration tests for the portfolio lookup catalog through intake and foundation-facing selector surfaces. |
| `GET /lookups/instruments` | `lotus-gateway` | Correct. Gateway has an explicit lotus-core client binding and contract/integration tests for the instrument lookup catalog in intake workflows. |
| `GET /lookups/currencies` | `lotus-gateway` | Correct. Gateway has an explicit lotus-core client binding and contract/integration tests for the currency lookup catalog. |

This is real downstream adoption, but the route family remains intentionally thin. Gateway is using
them correctly as selector catalogs rather than trying to stretch them into rich portfolio or
market-data contracts.

### Upstream Integration Assessment

The family is strong for its intended purpose:

1. portfolio lookups are derived from canonical portfolio records with optional CIF and
   booking-center scoping;
2. instrument lookups are derived from canonical instrument records with optional product-type
   filtering, and `q` search now scans the full filtered instrument catalog across pages before
   applying selector ordering and truncation;
3. currency lookups are derived deterministically from portfolio base currencies and instrument
   currencies, with source scoping and full pagination over instrument pages;
4. the routes intentionally reduce the payload to selector-safe `id` / `label` records.

One upstream defect was found and fixed in this pass: instrument lookup search could miss valid
matches beyond the first fetched page when `q` was supplied. The route now pages through the full
filtered instrument catalog before applying search and limit semantics, which restores truthful
selector behavior for larger inventories.

### Swagger / OpenAPI Assessment

For this family, Swagger now makes the following explicit:

1. the routes are selector catalogs, not generic data APIs;
2. when-to-use and when-not-to-use guidance is explicit for all three catalogs;
3. filter and scope parameters remain clearly documented;
4. response schema field descriptions are explicit for lookup items and lookup collections.

Focused HTTP-level dependency proof exists in
`tests/integration/services/query_service/test_lookup_contract_router.py` and
`tests/integration/services/query_service/test_reference_data_routers.py` for portfolio,
instrument, and currency lookup success, filtering, source scoping, pagination-driven currency
derivation, output ordering, full-catalog instrument search, and shared `500` envelope behavior on
unexpected failures.

Gateway-side direct-consumer proof exists in
`lotus-gateway/src/app/clients/lotus_core_query_client.py`,
`lotus-gateway/tests/contract/test_lookup_contract.py`, and
`lotus-gateway/tests/integration/test_intake_router.py`.

OpenAPI proof exists in `tests/integration/services/query_service/test_main_app.py`, including the
route-purpose wording, parameter descriptions, and lookup schema field descriptions.

### Issue Disposition For This Endpoint Family

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core` | No open issue found in this pass | No open lotus-core issue existed for this family. The one core defect found in certification was fixed directly in this slice, so no new issue was opened. |
| Downstream repos | No open issue found in this pass | Gateway appears to be using the lookup contracts correctly, so no downstream issue was opened. |

## Certified Endpoint Slice: Asset Allocation Operational Read

This certification pass covers:

1. `POST /reporting/asset-allocation/query`

### Route Contract Decision

This is the strategic lotus-core allocation route for report-ready and UI-ready bucketed allocation
analysis.

The boundary is now explicit:

1. use this route when a downstream consumer needs allocation buckets across supported dimensions
   such as asset class, currency, sector, country, region, product type, rating, or issuer;
2. use it when explicit look-through request versus applied-mode posture matters;
3. prefer it over pulling allocation views out of `core-snapshot` when the consumer does not need
   broader source-state sections;
4. keep downstream composition focused on presentation, not on rebuilding allocation analytics from
   broad state payloads.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /reporting/asset-allocation/query` | `lotus-gateway`, `lotus-report` | Correct. Gateway already uses the dedicated allocation route for modular allocation APIs. Report now uses this route for summary allocation sections and honors requested allocation dimensions instead of mining allocation from `core-snapshot`. |

No active direct `lotus-advise`, `lotus-risk`, or `lotus-manage` client was evidenced against this
route in this pass.

### Upstream Integration Assessment

The route is strong and domain-correct for quant and private-banking allocation expectations:

1. allocation buckets are computed centrally in lotus-core rather than reconstructed downstream from
   holdings rows;
2. reporting-currency restatement is upstream-owned and consistent across dimensions;
3. look-through capability is explicit, so consumers can distinguish requested mode from applied
   mode honestly;
4. the route stays focused on allocation analysis rather than collapsing broader source-state
   publication into one consumer-specific payload.

### Swagger / OpenAPI Assessment

For this endpoint, Swagger now makes the following explicit:

1. this is the strategic allocation seam for downstream allocation analysis;
2. consumers should prefer it over mining allocation from `core-snapshot` when only allocation
   buckets are needed;
3. look-through request versus applied behavior is part of the governed contract;
4. bucket, view, response, and look-through metadata fields now carry clearer examples.

Focused HTTP-level dependency proof exists in
`tests/integration/services/query_service/test_reporting_router.py` for successful asset-allocation
routing and request validation behavior.

Service-level proof exists in
`tests/unit/services/query_service/services/test_reporting_service.py` for multi-dimension
allocation output and look-through behavior.

OpenAPI proof exists in `tests/integration/services/query_service/test_main_app.py`, including the
route-purpose wording and endpoint-specific schema examples.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core` | No open issue | The source route is contract-tight in this pass. No open lotus-core defect remains against `POST /reporting/asset-allocation/query`. |
| `lotus-gateway #72` region and look-through allocation support | Closed before this pass. Current gateway code and tests already support region allocation views, look-through request propagation, capability metadata, and OpenAPI coverage. | Keep closed unless new contrary runtime evidence appears. |
| `lotus-report` | No open issue after direct downstream fix in this pass | Report now uses the dedicated allocation route for summary allocation sections and honors requested allocation dimensions. No tracking issue is needed for this route today. |

## Certified Endpoint Slice: Portfolio Summary Operational Read

This certification pass covers:

1. `POST /reporting/portfolio-summary/query`

### Route Contract Decision

This is the strategic lotus-core summary route for one-portfolio historical wealth totals.

The boundary is now explicit:

1. use this route when a downstream consumer needs snapshot-backed total market value, cash versus
   invested split, and summary coverage metadata for one portfolio and as-of date;
2. prefer this route over reconstructing summary figures from `HoldingsAsOf` rows or
   `core-snapshot` section payloads;
3. keep performance, risk, and narrative reporting ownership outside this route;
4. treat it as a report-ready operational read, not as a replacement for sectioned state or
   analytics-serving contracts.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /reporting/portfolio-summary/query` | `lotus-report` | Correct after direct downstream fix in this pass. Report now uses the dedicated summary contract for wealth totals instead of reconstructing those figures from `core-snapshot`. |

`lotus-gateway` remains an intended consumer through report-owned or gateway-owned summary surfaces,
but this pass did not evidence a direct gateway call into lotus-core for this route itself.

### Upstream Integration Assessment

The route is strong and domain-correct for quant and private-banking summary expectations:

1. totals are snapshot-backed and restated into reporting currency rather than left for downstream
   reconstruction;
2. cash versus invested split is explicit and removes downstream guesswork around whether cash was
   netted out or derived from holdings rows;
3. summary coverage metadata publishes valued versus unvalued position counts so consumers can
   reason about supportability instead of trusting a single headline figure blindly;
4. the route stays narrow and avoids absorbing analytics narrative that belongs in performance,
   risk, or report-owned composition layers.

### Swagger / OpenAPI Assessment

For this endpoint, Swagger now makes the following explicit:

1. this is the strategic lotus-core summary seam for report-ready wealth totals;
2. downstream consumers should prefer it over `core-snapshot` or holdings-row reconstruction when
   the need is summary figures;
3. it does not own performance, risk, or narrative reporting outputs;
4. endpoint-specific DTO fields now carry clearer examples for portfolio classification, risk
   posture, lifecycle status, totals, and snapshot metadata.
5. unknown-portfolio requests now fail as a truthful `404` instead of being flattened into `400`,
   while invalid reporting-currency restatement remains a `400` contract.

Focused HTTP-level dependency proof exists in
`tests/integration/services/query_service/test_reporting_router.py` for successful summary routing,
truthful `404` mapping, and request validation behavior.

Service-level proof exists in `tests/unit/services/query_service/services/test_reporting_service.py`
for historical restated totals, cash versus invested split, and summary coverage metadata.

OpenAPI proof exists in `tests/integration/services/query_service/test_main_app.py`, including the
route-purpose wording and endpoint-specific schema examples.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core` | No open issue | The source route is contract-tight in this pass. No open lotus-core defect remains against `POST /reporting/portfolio-summary/query`. |
| `lotus-report` | No open issue after direct downstream fix in this pass | `lotus-report` now binds wealth totals to the dedicated summary contract instead of reconstructing them from `core-snapshot`. Keep watching downstream test coverage, but no tracking issue is needed for this route today. |

## Certified Endpoint Slice: Effective Integration Policy

This certification pass covers:

1. `GET /integration/policy/effective`

### Route Contract Decision

This is the strategic control-plane route for inspecting lotus-core policy posture before a
downstream caller requests governed source-data sections.

The contract is intentionally advisory and policy-scoped:

1. it resolves consumer and tenant policy context;
2. it can evaluate requested snapshot sections through `include_sections`;
3. it reports policy provenance, strict-mode posture, allowed sections, and warnings;
4. it does not itself publish portfolio state or analytics inputs.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `GET /integration/policy/effective` | `lotus-gateway` | Active direct default-path use is consistent with gateway’s role as the main control-plane consumer of section policy before governed state reads. |

Operator tooling and future downstream clients are also valid consumers when they need policy
diagnostics ahead of snapshot orchestration or support investigations.

### Swagger / OpenAPI Assessment

Swagger now makes the following explicit:

1. when the route should be used;
2. that `include_sections` is an optional evaluation input rather than a state read;
3. that the response is policy provenance and section-allowance metadata;
4. that the active direct use in this pass is `lotus-gateway` platform/bootstrap policy
   inspection rather than portfolio-state retrieval;
5. that canonical query names are snake_case only and camelCase aliases such as
   `consumerSystem` / `tenantId` are unsupported.

The HTTP dependency lane now proves both:

1. explicit consumer or tenant policy lookup with repeated `include_sections` query values;
2. canonical default resolution to `consumer_system=lotus-gateway` and `tenant_id=default`.

### Issue Disposition For This Endpoint

| Repository issue | Status | Certification read |
| --- | --- | --- |
| `lotus-core` | No open issue | The source route is already contract-tight in this pass. No lotus-core behavior or documentation defect remains open against `GET /integration/policy/effective`. |
| `lotus-gateway #116` | Closed on April 16, 2026 | Gateway completed the broader adoption review for the latest lotus-core route hardening. Keep closed unless a fresh gateway-facing policy-route regression appears. |

## Certified Endpoint Slice: Integration Capabilities

This certification pass covers:

1. `GET /integration/capabilities`

### Route Contract Decision

This is the control-plane discovery contract for policy-resolved lotus-core capability posture.

The contract is intentionally narrow:

1. it publishes source-owned feature and workflow availability for a consumer/tenant context;
2. it is not a substitute for endpoint-specific OpenAPI or source-data product contracts;
3. callers should use the canonical snake_case query parameters `consumer_system` and `tenant_id`.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `GET /integration/capabilities` | `lotus-gateway` | Active direct use exists via gateway platform capability aggregation and workbench composition context. |

This route is primarily a discovery/control-plane surface rather than a source-data product. The
active downstream need is real, but its job is capability publication, not domain calculation.

### Upstream Integration Assessment

The route is correctly placed and the contract is already strong. The main truth boundary worth
making explicit in this slice is canonical query naming. The route now states plainly that callers
should use snake_case `consumer_system` and `tenant_id`.

### Swagger / OpenAPI Assessment

For this endpoint, Swagger now makes the canonical query names explicit and recursive schema-family
tests protect the capabilities response surface from documentation drift.

Swagger now also states the active direct downstream use more plainly: `lotus-gateway` platform
capability aggregation is the current direct consumer in this pass, and the route remains a
control-plane discovery contract rather than a substitute for endpoint-specific source-data docs.
The route contract now also states explicitly that canonical query names are snake_case only and
camelCase aliases such as `consumerSystem` / `tenantId` are unsupported.

The HTTP dependency lane also proves both the explicit consumer or tenant request shape and the
default `consumer_system=lotus-gateway` plus `tenant_id=default` resolution path so downstream
discovery clients are covered whether they pass both query parameters or rely on the canonical
defaults.

### Issue Disposition For This Endpoint

| Repository issue | Status | Certification read |
| --- | --- | --- |
| `lotus-core` | No open issue | The source route is already contract-tight in this pass. No lotus-core behavior or documentation defect remains open against `GET /integration/capabilities`. |
| `lotus-gateway #117` | Closed on April 16, 2026 | Verified fixed in gateway commit `b45d3af`. `src/app/clients/lotus_core_query_client.py` now sends canonical snake_case `consumer_system` / `tenant_id`, and gateway unit coverage locks the non-default consumer and tenant path. |
| `lotus-gateway #73` | Closed | Gateway aggregation latency was a downstream performance issue rather than a lotus-core publication defect, and the remote issue is now closed. |
| `lotus-gateway #116` | Closed on April 16, 2026 | Gateway completed the broader adoption review for recently hardened lotus-core control-plane routes. |
| `lotus-gateway #109` | Closed on April 16, 2026 | Adjacent downstream parameter-conformance issue for lotus-performance capabilities, not a lotus-core route defect. Keep closed unless gateway reintroduces camelCase capabilities params for lotus-performance. |

The same certification lane now also protects the adjacent instrument-enrichment contract family
with recursive OpenAPI schema-family guards, so nested enrichment fields do not regress silently
while core-snapshot evolves.

The source-owned readiness, calculator-SLO, and control-stage support contracts are now also
covered by a recursive OpenAPI schema-family guard so nested readiness reasons, historical-FX
dependency summaries, SLO backlog fields, and control-stage lifecycle attributes remain
self-describing for gateway and operator consumers.

The adjacent support-operations contract family is now covered the same way, so support overview,
job-list, and analytics-export operational payloads cannot silently lose nested descriptions or
example signals while operator surfaces evolve.

## Certified Endpoint Slice: Instrument Enrichment

This certification pass covers:

1. `POST /integration/instruments/enrichment-bulk`

### Route Contract Decision

This is the strategic shared instrument-reference enrichment route for downstream consumers that
need governed issuer and liquidity metadata without taking a direct dependency on query-service
internals.

The contract boundary is now explicit:

1. request order is preserved in the response;
2. unknown securities remain present with null enrichment fields;
3. the route publishes source-owned reference context, not downstream suitability or analytics
   conclusions.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /integration/instruments/enrichment-bulk` | `lotus-advise`, `lotus-risk` | Correct. These repos contain direct integration usage for shared issuer/reference context. `lotus-performance` and `lotus-gateway` remain valid catalog-intended consumers for aligned source-reference enrichment. |

### Swagger / OpenAPI Assessment

Swagger now makes the following explicit:

1. when to use the route and which downstream apps it serves;
2. that unknown securities return null issuer fields instead of invented fallback identities;
3. that response order is deterministic and follows request order.

The HTTP dependency lane now also proves both the successful enrichment path and the trimmed-empty
identifier failure path, so this endpoint no longer relies only on router-function and schema
coverage.

### Issue Disposition For This Endpoint

| Repository issue | Status | Certification read |
| --- | --- | --- |
| `lotus-core` | No open issue | The source route is contract-tight in this pass. No lotus-core behavior or documentation defect remains open against `POST /integration/instruments/enrichment-bulk`. |
| `lotus-risk #93` | Closed on April 16, 2026 | Current risk repo truth on `main` includes merge commit `823524d` plus sync commits `177d722`, `fd94d45`, and `2fc86c6`. Active client/docs/tests remain aligned to `core-snapshot`, `position-timeseries`, `enrichment-bulk`, `risk-free-series`, and `risk-free-series/coverage`, including deterministic enrichment order and null unknown-security handling. |
| `lotus-advise #92` | Closed | Closed on current repo truth. Advise remains an active direct enrichment consumer and its stateful-context tests/mocks are aligned to current enrichment semantics and null unknown-security handling. |

## Certified Endpoint Slice: Core Snapshot

This certification pass covers:

1. `POST /integration/portfolios/{portfolio_id}/core-snapshot`

### Route Contract Decision

This remains the strategic state snapshot contract for downstream consumers that need governed
portfolio-state sections.

The contract boundary is now explicit in Swagger and tests:

1. use it for policy-aware baseline or simulation state;
2. use it for positions, deltas, totals, valuation context, and enrichment;
3. do not use it as a substitute for downstream performance, risk, or advisory output contracts;
4. treat it as source data publication, not analytics ownership transfer.

The certification lane now also includes HTTP-level dependency tests for the gateway-facing
`core-snapshot` and benchmark-assignment routes, so policy gating, source-data runtime metadata,
and not-found behavior are proven through the ASGI surface rather than only through direct router
function tests.

That dependency lane now also covers `409` simulation conflict and `422` unavailable-section
semantics, so downstream consumers can distinguish missing state, conflicting simulation version
state, policy block, and unfulfillable section requests without collapsing them into one generic
error path.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `POST /integration/portfolios/{portfolio_id}/core-snapshot` | `lotus-gateway`, `lotus-risk` | Gateway and risk are correct direct consumers and remain aligned to the governed top-level `PortfolioStateSnapshot` envelope. Merged report PR `#41` removed the remaining report-side `core-snapshot` dependency, migrated review composition onto strategic summary/allocation/positions/transactions routes, and passed the remote PR Merge Gate, so report is no longer a live direct consumer of this route. No active direct `lotus-manage` or `lotus-advise` client was found in this pass. |

`lotus-manage` remains an intended consumer in the source-data catalog, but direct active code use
was not found in this pass and should not be overstated as live validated. The same is true for
`lotus-advise` on this specific route family: advisory work is currently anchored more strongly to
simulation and stateful-context seams than to direct `core-snapshot` reads.

The earlier downstream mismatch found in this pass is now closed. On April 16, 2026, gateway commit
`6ec3977` moved foundation workspace parsing onto the governed top-level
`PortfolioStateSnapshot` envelope, using the dedicated portfolio identity route only for identity
fields that are not owned by `core-snapshot`. Current gateway unit and integration fixtures now
model top-level `portfolio_id`, `as_of_date`, `valuation_context`, and `sections`, and an explicit
regression test proves the parser ignores legacy nested `portfolio` / `metadata` blocks.

### Swagger / OpenAPI Assessment

For this endpoint, Swagger now makes the following explicit:

1. this route publishes portfolio-state source sections, not analytics conclusions;
2. simulation request block semantics are explicit and exampled;
3. request options and section payload semantics are explicit and exampled;
4. the governed response shape is top-level source-data runtime metadata plus `valuation_context`
   and `sections`, not a legacy nested `portfolio` or `metadata` envelope;
5. the full core-snapshot schema family is now protected by a recursive OpenAPI completeness guard.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core #57` portfolio-scoped POST endpoint 404 gap | Closed. The route documents 404 behavior and integration tests assert the not-found response example. | Re-open only if fresh contrary runtime evidence appears. |
| `lotus-gateway #118` legacy `core-snapshot` envelope assumption in foundation workspace | Closed on April 16, 2026. Verified fixed in gateway commit `6ec3977`. Foundation workspace parsing now consumes the canonical top-level `PortfolioStateSnapshot` envelope, fetches separate identity data only where required, and regression tests fail if legacy nested `portfolio` / `metadata` assumptions return. | Keep closed unless fresh gateway code reintroduces legacy envelope dependence. |
| `lotus-report #40` legacy core-snapshot section assumptions in reporting read flows | Closed on April 17, 2026. Local report commit `0254c71` removed the dead `get_core_snapshot(...)` client seam, moved report read/review composition onto strategic summary/allocation/positions/transactions routes, and deleted legacy `snapshot.*` fixtures from report tests. | Keep closed unless a future report workflow reintroduces direct `core-snapshot` dependence or stale nested `snapshot.*` assumptions. |

Focused certification evidence on April 16, 2026:

1. `lotus-core`: `python -m pytest tests\unit\services\query_service\services\test_core_snapshot_service.py tests\integration\services\query_control_plane_service\test_integration_router_dependency.py tests\integration\services\query_control_plane_service\test_control_plane_app.py -q`
2. `lotus-gateway`: `python -m pytest tests\unit\test_foundation_service.py tests\unit\test_workbench_service.py tests\unit\test_upstream_clients.py tests\integration\test_foundation_router.py tests\integration\test_workbench_router.py -q`
3. `lotus-risk`: `python -m pytest tests\unit\test_lotus_core_client.py tests\unit\test_concentration_engine_characterization.py tests\unit\test_concentration_engine_modes.py tests\integration\test_concentration_lotus_core_characterization.py -q`

No open route-specific GitHub issue remains for `core-snapshot` in `lotus-core`, `lotus-gateway`,
`lotus-risk`, or `lotus-report`. Current open downstream work in adjacent repos is now outside the
`core-snapshot` route family itself.

## Downstream Consumer Matrix

| Product | Governed route(s) | Intended consumers | Direct integration evidence reviewed | Test-pyramid posture |
| --- | --- | --- | --- | --- |
| `PortfolioStateSnapshot` | `POST /integration/portfolios/{portfolio_id}/core-snapshot` | `lotus-gateway`, `lotus-risk`, catalog-intended `lotus-manage`, `lotus-advise`, `lotus-report` | Direct active client evidence exists in `lotus-gateway/src/app/clients/lotus_core_query_client.py` and `lotus-risk/src/app/integrations/lotus_core_client.py`. Merged report PR `#41` removed the remaining direct `core-snapshot` client seam and migrated report review composition onto strategic routes with a green remote PR Merge Gate, so report is now catalog-intended rather than a live direct consumer. `lotus-manage` currently documents intended adoption but does not yet have an active outbound client. `lotus-advise` currently uses other lotus-core seams more directly than `core-snapshot` itself. | Strong for gateway and risk. `lotus-report`, `lotus-manage`, and `lotus-advise` should not be described as live direct consumers of this route until their product workflows bind to it. |
| `PositionTimeseriesInput` | `POST /integration/portfolios/{portfolio_id}/analytics/position-timeseries` | `lotus-performance`, `lotus-risk` | `lotus-performance` core integration and stateful attribution/contribution services; `lotus-risk/src/app/services/attribution_mode_adapter.py`. | Strong. Core route and schema tests, performance client tests, performance API/e2e mocked journey tests, and risk attribution adapter tests. |
| `PortfolioTimeseriesInput` | `POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries` | `lotus-performance` plus catalog-intended portfolio-level analytics consumers such as `lotus-risk` | `lotus-performance` returns/TWR source services and canonical TWR inspection script. Risk remains catalog-intended for portfolio-level analytics input, with current direct evidence stronger for position attribution and risk-free sources than for this route itself. | Strong for performance. Core catalog/OpenAPI tests protect the contract; risk portfolio-timeseries runtime use should be rechecked when risk portfolio-level analytics expands. |
| `PortfolioAnalyticsReference` | `POST /integration/portfolios/{portfolio_id}/analytics/reference` | `lotus-performance`, `lotus-gateway` | `lotus-performance` core integration service; `lotus-gateway` uses this route as workspace source context. `lotus-risk` remains governed but is not evidenced as a live direct caller in this pass. | Strong for performance and gateway direct usage. Risk should use this only where it needs analytics lifecycle/reference context, not operational holdings. |
| `MarketDataWindow` | `POST /integration/benchmarks/{benchmark_id}/market-series` | `lotus-performance` plus catalog-intended downstream benchmark consumers | Direct active code evidence in this pass exists for `lotus-performance` benchmark exposure/context services. Current `lotus-risk` architecture notes indicate active-risk attribution has moved away from direct benchmark market-series orchestration toward lotus-performance-owned derived benchmark exposure context. | Strong for performance benchmark path. Core catalog/OpenAPI tests protect route shape. Downstream direct-adoption claims beyond performance should stay narrow unless active product code resumes using the raw benchmark market-series contract. |
| `InstrumentReferenceBundle` | `POST /integration/instruments/enrichment-bulk`; `POST /integration/reference/classification-taxonomy` | `lotus-advise`, `lotus-risk` plus catalog-intended source-reference consumers | Direct active code evidence is strong for `enrichment-bulk` via `lotus-advise` and `lotus-risk`. Advise now also calls the classification-taxonomy route during stateful context resolution to prevent local advisory label drift. Gateway and performance remain catalog-intended consumers for source-reference alignment. | Strong for enrichment direct client paths and adequate for advise taxonomy adoption. Core taxonomy publication remains well documented and tested; additional direct-adoption evidence should be captured before gateway, performance, or risk are described as live taxonomy callers. |
| `BenchmarkAssignment` | `POST /integration/portfolios/{portfolio_id}/benchmark-assignment` | `lotus-performance`, `lotus-gateway` | `lotus-performance` returns and benchmark services; `lotus-gateway/src/app/clients/lotus_core_query_client.py` for workspace composition context. `lotus-risk` and `lotus-report` remain catalog-intended rather than live direct consumers in this pass. | Strong for performance and gateway. `lotus-risk` and `lotus-report` should not be described as live direct consumers until product workflows bind to the route. |
| `DpmModelPortfolioTarget` | `POST /integration/model-portfolios/{model_portfolio_id}/targets` | `lotus-manage` | RFC-087 Slice 4 introduced the dedicated model-target source product for discretionary portfolio management stateful source assembly. Direct downstream code evidence now exists in `lotus-manage/src/infrastructure/core_sourcing/client.py`, where `DpmCoreResolverClient.resolve_model_portfolio_targets` calls this route, and in `lotus-manage/src/core/dpm_source_context.py`, where the returned target rows transform into the DPM engine `ModelPortfolio`. | Strong for first-wave manage integration prep through core route/OpenAPI/catalog tests plus manage client and transformation unit tests. Production stateful execution remains intentionally blocked until the remaining RFC-087 source products are implemented and live-proven. |
| `DiscretionaryMandateBinding` | `POST /integration/portfolios/{portfolio_id}/mandate-binding` | `lotus-manage` | RFC-087 Slice 5 introduced the dedicated mandate binding source product so `lotus-manage` can resolve discretionary authority, model id, policy pack, booking center, jurisdiction, risk profile, tax-awareness, settlement-awareness, and rebalance bands from core source data instead of local assumptions. Direct downstream code evidence now exists in `lotus-manage/src/infrastructure/core_sourcing/client.py`, where `DpmCoreResolverClient.resolve_mandate_binding` calls this route, and in `lotus-manage/src/core/dpm_source_context.py`, where the binding response transforms into the DPM policy context. | Strong for core producer certification and first-wave manage integration prep. Production stateful execution remains intentionally blocked until eligibility, tax-lot, and market-data source products are implemented and live-proven. |
| `InstrumentEligibilityProfile` | `POST /integration/instruments/eligibility-bulk` | `lotus-manage` | RFC-087 Slice 6 introduced the dedicated instrument eligibility source product so `lotus-manage` can resolve product shelf status, buy/sell eligibility, restriction reason codes, settlement profile, liquidity tier, issuer hierarchy, asset class, and country of risk from core source data instead of advisory-era or local assumptions. Direct downstream code evidence now exists in `lotus-manage/src/infrastructure/core_sourcing/client.py`, where `DpmCoreResolverClient.resolve_instrument_eligibility` calls this route, and in `lotus-manage/src/core/dpm_source_context.py`, where eligibility rows transform into the DPM source context. | Strong for core producer certification and first-wave manage integration prep. Production stateful execution remains intentionally blocked until tax-lot and market-data source products are implemented and live-proven. |
| `PortfolioTaxLotWindow` | `POST /integration/portfolios/{portfolio_id}/tax-lots` | `lotus-manage` | RFC-087 Slice 7 introduced the dedicated portfolio tax-lot source product so `lotus-manage` can resolve cost basis and lot lineage for tax-aware sell decisions without per-security fan-out or local cost-basis assumptions. Current core evidence covers route/OpenAPI/catalog/service tests and the endpoint sources authoritative lot state from `position_lot_state`. Direct downstream code evidence must be added in `lotus-manage` before stateful tax-aware execution is enabled. | Strong for core producer certification. Downstream `lotus-manage` integration proof is required before RFC-0036 tax-aware stateful execution is enabled. Production stateful execution remains intentionally blocked until market-data source products and live canonical proof are complete. |
| `TransactionCostCurve` | `POST /integration/portfolios/{portfolio_id}/transaction-cost-curve` | `lotus-manage` | RFC40-WTBD-007 source-owner foundation introduced the observed transaction-cost curve source product so `lotus-manage` proof packs can distinguish source-backed booked fee evidence from local construction estimates. Current core evidence covers route/OpenAPI/catalog/security/service/repository/domain-product tests and the endpoint sources from `transactions` plus `transaction_costs`, grouped by security, transaction type, and currency. Direct downstream code evidence must be added in `lotus-manage` before proof packs may advertise source-backed transaction-cost curves. | Strong for core producer certification. This is observed booked fee evidence, not a predictive market-impact, spread, liquidity, or execution-price guarantee. Downstream `lotus-manage` integration and live canonical proof are required before RFC40-WTBD-007 can be closed. |
| `ClientRestrictionProfile` | `POST /integration/portfolios/{portfolio_id}/client-restriction-profile` | `lotus-manage` | RFC40-WTBD-008 source-owner foundation introduced the client restriction profile source product so `lotus-manage` can resolve client, mandate, instrument, issuer, country, and asset-class restriction records from core source data instead of local fallback fixtures. Current core evidence covers persistence, ingestion, route/OpenAPI/catalog/security/service/repository/domain-product tests, canonical seed records, and live DPM validator probes. Direct downstream code evidence must be added in `lotus-manage` before proof packs may advertise source-backed restriction enforcement. | Strong for core producer certification. This is source-owned restriction truth, not suitability adjudication, entitlement evaluation, or rebalance decisioning. Downstream `lotus-manage` integration and live canonical proof are required before RFC40-WTBD-008 can be closed. |
| `SustainabilityPreferenceProfile` | `POST /integration/portfolios/{portfolio_id}/sustainability-preference-profile` | `lotus-manage` | RFC40-WTBD-008 source-owner foundation introduced the sustainability preference profile source product so `lotus-manage` can resolve allocation bounds, exclusions, positive tilts, framework, source, and lineage from core source data instead of local fallback fixtures. Current core evidence covers persistence, ingestion, route/OpenAPI/catalog/security/service/repository/domain-product tests, canonical seed records, and live DPM validator probes. Direct downstream code evidence must be added in `lotus-manage` before proof packs may advertise source-backed sustainability preference enforcement. | Strong for core producer certification. This is source-owned preference truth, not greenwashing scoring, suitability adjudication, or rebalance decisioning. Downstream `lotus-manage` integration and live canonical proof are required before RFC40-WTBD-008 can be closed. |
| `ClientTaxProfile` | `POST /integration/portfolios/{portfolio_id}/client-tax-profile` | `lotus-manage` | RFC42-WTBD-006 source-owner foundation introduced the client tax profile source product so `lotus-manage` can resolve bounded client tax-reference profile facts from core source data instead of local fallback fixtures. Current core evidence covers persistence, migration, ingestion DTO/router/service validation, route/OpenAPI/catalog/security/service/domain-product tests, source methodology, and wiki/context updates. Direct downstream code evidence must be added in `lotus-manage` before proof packs may advertise source-backed tax-reference evidence. | Strong for core producer certification. This is source-owned tax-reference evidence only, not tax advice, after-tax optimization, tax-loss harvesting suitability, client-tax approval, jurisdiction-specific recommendations, tax-reporting certification, or OMS acknowledgement. Downstream `lotus-manage` integration and live canonical proof are required before RFC42-WTBD-006 can be closed. |
| `ClientTaxRuleSet` | `POST /integration/portfolios/{portfolio_id}/client-tax-rule-set` | `lotus-manage` | RFC42-WTBD-006 source-owner foundation introduced the client tax rule-set source product so `lotus-manage` can resolve bounded client tax-rule references from core source data instead of local fallback fixtures. Current core evidence covers persistence, migration, ingestion DTO/router/service validation, route/OpenAPI/catalog/security/service/domain-product tests, source methodology, and wiki/context updates. Direct downstream code evidence must be added in `lotus-manage` before proof packs may advertise source-backed tax-rule reference evidence. | Strong for core producer certification. This is source-owned tax-rule reference evidence only, not tax advice, tax-loss harvesting suitability, after-tax optimization, client-tax approval, jurisdiction-specific recommendations, tax-reporting certification, best execution, or OMS acknowledgement. Downstream `lotus-manage` integration and live canonical proof are required before RFC42-WTBD-006 can be closed. |
| `ClientIncomeNeedsSchedule` | `POST /integration/portfolios/{portfolio_id}/client-income-needs-schedule` | `lotus-manage` | RFC42-WTBD-006 source-owner foundation introduced the client income-needs schedule source product so `lotus-manage` can resolve bounded client cash-needs evidence from core source data instead of local fallback fixtures. Current core evidence covers persistence, migration, ingestion DTO/router/service validation, route/OpenAPI/catalog/security/service/domain-product tests, source methodology, and wiki/context updates. Direct downstream code evidence must be added in `lotus-manage` before proof packs may advertise source-backed income-needs evidence. | Strong for core producer certification. This is source-owned income-needs evidence only, not financial-planning advice, client liability planning, suitability approval, cashflow forecasting, funding recommendation, or OMS acknowledgement. Downstream `lotus-manage` integration and live canonical proof are required before RFC42-WTBD-006 can be closed. |
| `LiquidityReserveRequirement` | `POST /integration/portfolios/{portfolio_id}/liquidity-reserve-requirement` | `lotus-manage` | RFC42-WTBD-006 source-owner foundation introduced the liquidity reserve requirement source product so `lotus-manage` can resolve bounded reserve evidence from core source data instead of local fallback fixtures. Current core evidence covers persistence, migration, ingestion DTO/router/service validation, route/OpenAPI/catalog/security/service/domain-product tests, source methodology, and wiki/context updates. Direct downstream code evidence must be added in `lotus-manage` before proof packs may advertise source-backed reserve evidence. | Strong for core producer certification. This is source-owned reserve evidence only, not cash-reserve recommendation, financial-planning advice, suitability approval, treasury instruction, or OMS acknowledgement. Downstream `lotus-manage` integration and live canonical proof are required before RFC42-WTBD-006 can be closed. |
| `PlannedWithdrawalSchedule` | `POST /integration/portfolios/{portfolio_id}/planned-withdrawal-schedule` | `lotus-manage` | RFC42-WTBD-006 source-owner foundation introduced the planned withdrawal schedule source product so `lotus-manage` can resolve bounded withdrawal evidence from core source data instead of local fallback fixtures. Current core evidence covers persistence, migration, ingestion DTO/router/service validation, route/OpenAPI/catalog/security/service/domain-product tests, source methodology, and wiki/context updates. Direct downstream code evidence must be added in `lotus-manage` before proof packs may advertise source-backed withdrawal evidence. | Strong for core producer certification. This is source-owned withdrawal evidence only, not cashflow forecast, financial-planning advice, suitability approval, funding recommendation, treasury instruction, or OMS acknowledgement. Downstream `lotus-manage` integration and live canonical proof are required before RFC42-WTBD-006 can be closed. |
| `ExternalHedgeExecutionReadiness` | `POST /integration/portfolios/{portfolio_id}/external-hedge-execution-readiness` | `lotus-manage` | RFC39-WTBD-008 source-owner runtime posture introduces a fail-closed external treasury readiness product so `lotus-manage` can block currency-overlay realization when bank-owned treasury ingestion is not certified. Current core evidence covers route/OpenAPI/catalog/security/service/domain-product tests and explicit `UNAVAILABLE` supportability with missing external treasury data families and blocked capabilities. Direct downstream code evidence must be added in `lotus-manage` before any manage proof pack may advertise source-backed currency-overlay execution readiness. | Strong for core producer certification. This is source-owner supportability only, not hedge advice, forward pricing, counterparty selection, best execution, OMS acknowledgement, fills, settlement, or autonomous treasury action. Downstream `lotus-manage` integration and live canonical proof are required before RFC39-WTBD-008 can move beyond partial. |
| `MarketDataCoverageWindow` | `POST /integration/market-data/coverage` | `lotus-manage` | RFC-087 Slice 8 introduced the dedicated market-data coverage source product so `lotus-manage` can resolve held and target universe price/FX coverage, stale observations, and missing observations without serial price or FX lookup loops. Current core evidence covers route/OpenAPI/catalog/service tests and the endpoint sources from `market_prices` and `fx_rates`. Direct downstream code evidence must be added in `lotus-manage` before stateful market-data execution is enabled. | Strong for core producer certification. Downstream `lotus-manage` integration proof is required before RFC-0036 stateful execution is enabled. Production stateful execution remains intentionally blocked until DPM readiness/source-family supportability and live canonical proof are complete. |
| `DpmSourceReadiness` | `POST /integration/portfolios/{portfolio_id}/dpm-source-readiness` | `lotus-manage`, catalog-intended `lotus-gateway` operator/readiness surfaces | RFC-087 Slice 9 introduced the control-plane readiness product so operators and `lotus-manage` can verify mandate binding, model target, eligibility, tax-lot, and market-data source families before stateful discretionary execution. Current core evidence covers route/OpenAPI/catalog/security/service tests and bounded `READY`, `DEGRADED`, `INCOMPLETE`, and `UNAVAILABLE` diagnostics. Direct downstream code evidence must be added in `lotus-manage` before RFC-0036 can claim source-readiness-driven execution gating, and gateway should wait for the strategic post-RFC-0036 integration rather than consuming older advisory-oriented readiness seams. | Strong for core producer certification and operator supportability. Downstream `lotus-manage` integration proof and live canonical proof are required before the readiness product is described as production-proven in manage execution workflows. |
| `PortfolioManagerBookMembership` | `POST /integration/portfolio-manager-books/{portfolio_manager_id}/memberships` | `lotus-manage` | RFC41-WTBD-001 source-owner foundation introduced the PM-book membership source product so `lotus-manage` can discover explicit wave cohorts from core portfolio master membership instead of fabricating PM books locally. Current core evidence covers route/OpenAPI/catalog/security/service/repository tests and the endpoint sources from `portfolios.advisor_id` with as-of lifecycle, active-status, booking-center, and portfolio-type filters. | Strong for core producer certification. Downstream `lotus-manage` integration and live canonical wave proof are required before automatic PM-book wave discovery is described as production-proven. This is not a full relationship-householding or entitlement hierarchy claim. |
| `CioModelChangeAffectedCohort` | `POST /integration/model-portfolios/{model_portfolio_id}/affected-mandates` | `lotus-manage` | RFC41-WTBD-002 introduces the CIO model-change affected-cohort source product so `lotus-manage` can discover affected discretionary mandates from approved model definitions and effective mandate bindings rather than accepting caller-supplied portfolios. Coordinated downstream evidence exists in the `lotus-manage` RFC41-WTBD-002 slice: `DpmCoreResolverClient.resolve_cio_model_change_affected_cohort` calls the route and `src/core/dpm_source_context.py` maps the cohort into governed `CIO_MODEL_CHANGE` wave preview/create inputs. | Strong for core producer certification and first-wave manage integration through route/OpenAPI/catalog/security/service/repository tests plus manage client and wave API tests. Live canonical wave proof is still required before this source product is described as production-proven for full model-change operations. |
| `BenchmarkConstituentWindow` | `POST /integration/benchmarks/{benchmark_id}/composition-window` | `lotus-performance` plus catalog-intended downstream benchmark consumers | `lotus-performance` benchmark engine and stateful benchmark input services provide the active direct code evidence in this pass. | Strong for performance, including benchmark path unit/integration/characterization coverage. Downstream consumers such as risk should avoid independently recreating performance benchmark orchestration unless a governed RFC requires raw benchmark inputs again. |
| `IndexSeriesWindow` | `POST /integration/indices/{index_id}/price-series`; `POST /integration/indices/{index_id}/return-series` | `lotus-performance` plus catalog-intended downstream benchmark consumers | `lotus-performance` execution and benchmark tests reference index price series and related sourcing paths. Current `lotus-risk` architecture notes in this pass do not evidence live direct raw index-series calls. | Strong for performance sourcing. Core OpenAPI/catalog tests protect both price and return routes. Downstream direct usage should be validated before risk or other apps are described as active consumers of the raw index-series contracts. |
| `RiskFreeSeriesWindow` | `POST /integration/reference/risk-free-series` | `lotus-performance`, `lotus-risk` | `lotus-performance` returns-series service; `lotus-risk` rolling mode adapter and live returns support. | Strong. Both performance and risk have direct tests around source retrieval/error handling, with core OpenAPI/catalog guards. |
| `ReconciliationEvidenceBundle` | `GET /support/portfolios/{portfolio_id}/reconciliation-runs`; `GET /support/portfolios/{portfolio_id}/reconciliation-runs/{run_id}/findings` | Catalog-intended operator consumers; no strong active direct caller evidenced in this pass | Governed support-plane evidence published correctly by lotus-core. April 18, 2026 live probes against `PB_SG_GLOBAL_BAL_001` returned completed `timeseries_integrity` evidence with truthful source-data product metadata, and a downstream repo scan still found no active direct product client binding in gateway, risk, manage, report, or advise. | Strong for core publication and dependency-lane behavior. `test_operations_router_dependency.py` covers success, 404, and 500 mappings for both routes, and the focused April 18, 2026 support-evidence test slice passed. Downstream workflow validation is still needed before specific product surfaces are described as direct consumers. |
| `DataQualityCoverageReport` | `POST /integration/benchmarks/{benchmark_id}/coverage`; `POST /integration/reference/risk-free-series/coverage` | `lotus-risk` plus catalog-intended readiness/support consumers | Direct code evidence in this pass exists for `lotus-risk` consuming `risk-free-series/coverage`. Current canonical live proof also confirms both benchmark coverage and risk-free coverage are published correctly by lotus-core for the governed window, but this pass did not verify direct gateway/manage/performance product code calling those routes. | Strong for core publication and live readiness evidence. Downstream direct-adoption claims should stay narrow until product code paths for benchmark coverage or operator support callers are evidenced. |
| `IngestionEvidenceBundle` | `GET /lineage/portfolios/{portfolio_id}/keys`; `GET /support/portfolios/{portfolio_id}/reprocessing-keys`; `GET /support/portfolios/{portfolio_id}/reprocessing-jobs` | Catalog-intended operator consumers; no strong active direct caller evidenced in this pass | Core lineage and replay-support routes are present in OpenAPI and intentionally published as operational evidence rather than calculation inputs. April 18, 2026 live probes against `PB_SG_GLOBAL_BAL_001` returned eleven healthy lineage keys, eleven current replay keys, and an explicit zero-job replay backlog, while the downstream repo scan still found no active direct product client binding in gateway, risk, manage, report, or advise. | Strong for core route publication and dependency-lane behavior. `test_operations_router_dependency.py` covers lineage keys, reprocessing keys, and reprocessing jobs success plus 404/500 handling, and the focused April 18, 2026 support-evidence test slice passed. Downstream operator-console/report workflows still need direct product validation before they can be called fully production-proven. |

## Swagger Documentation Assessment

The governed query-control-plane routes are expected to meet RFC-0067 documentation quality:

1. Endpoint summary and description explain the route's purpose, when to use it, and the primary downstream consumers.
2. Every request parameter and request-body attribute has an explicit description, type, and example through the FastAPI/Pydantic OpenAPI schema.
3. Every response attribute has an explicit description and example where the schema carries example metadata.
4. 404 and validation examples are present for important operator and integration failure modes.
5. OpenAPI operations expose `x-lotus-source-data-product` so consumers can discover product name, version, owner, route family, paging/export mode, and intended consumers.
6. OpenAPI operations expose `x-lotus-source-data-security` so consumers can discover tenant, entitlement, required capability, sensitivity, and audit expectations.

Current automated evidence:

```powershell
python scripts\openapi_quality_gate.py
python scripts\source_data_product_contract_guard.py
python scripts\analytics_input_consumer_contract_guard.py
```

These gates are necessary but not sufficient for feature sign-off. They prove contract publication quality, not live end-to-end economic correctness.

## Test Pyramid Assessment

The current test posture is intentionally layered:

| Pyramid layer | Evidence | Assessment |
| --- | --- | --- |
| Catalog/static guards | `tests/unit/scripts/test_source_data_product_contract_guard.py`, `tests/unit/scripts/test_analytics_input_consumer_contract_guard.py`, source-data catalog tests | Strong. Prevents missing extensions, incorrect route-family publication, and stale consumer metadata. |
| OpenAPI integration tests | `tests/integration/services/query_control_plane_service/test_control_plane_app.py` | Strong. Verifies route existence, excluded legacy paths, parameter descriptions, response descriptions, error examples, source-data extensions, and consumer-facing descriptions. |
| Router/service integration tests | Query-control-plane integration tests and route dependency tests | Adequate to strong for contract shape and dependency wiring. Domain-specific payload economics still require service and canonical data validation. |
| Downstream client unit tests | `lotus-performance`, `lotus-risk`, `lotus-gateway`, and `lotus-advise` client/service tests found during review | Strong for currently active consumers. Some catalog-intended consumers are intentionally future/feature dependent and should not be overstated as live validated. |
| Platform E2E | Canonical front-office runtime and live `PB_SG_GLOBAL_BAL_001` probes | Passed on 2026-04-15 for the canonical front-office flow. This does not replace PR Merge Gates or authorization/entitlement hardening proof. |

## Production-Grade Expectations

For a route to be considered production-grade, all of the following must hold:

1. The source-data product is present in `SOURCE_DATA_PRODUCT_CATALOG`.
2. OpenAPI publishes source-data and security extensions for the route.
3. Swagger descriptions explain purpose, usage, consumers, attributes, examples, and failure behavior.
4. lotus-core has targeted tests for route publication and payload shape.
5. At least one active downstream consumer has client tests for the exact path and payload contract.
6. Canonical `PB_SG_GLOBAL_BAL_001` live validation passes when the route participates in front-office calculation or UI behavior.
7. Any route used for performance, risk, or private-banking decisions has domain-level checks for economic consistency, not only JSON shape.

## Remaining Follow-Ups

1. Add downstream workflow tests as `lotus-manage` and `lotus-report` begin direct use of support/evidence products.
2. Keep `SOURCE_DATA_PRODUCT_CATALOG`, OpenAPI operation descriptions, and this audit synchronized whenever route consumers change.
3. Avoid adding downstream UI features that imply backend capability until the relevant source-data product has live validation evidence.
4. Keep the portfolio workspace `Performance Snapshot` on the correct side of the boundary: its calculated return, benchmark, excess-return, and sparkline payload belong in `lotus-performance`, not `lotus-core`.
5. Complete PR Merge Gates and production authorization/entitlement proof before claiming full production runtime closure.

