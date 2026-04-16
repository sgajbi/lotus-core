# RFC-0082 / RFC-0083 Downstream Endpoint Consumer And Test Coverage Audit

Status: Draft implementation audit  
Owner: lotus-core  
Last reviewed: 2026-04-16  
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
| `#259` need explicit flow provenance beyond plain external flow | Addressed in the live contract. `CashFlowObservation` now exposes `cash_flow_type`, `flow_scope`, and `source_classification`, with OpenAPI descriptions covering semantics. | Closure comment posted with implementation evidence; issue should now be closed. |
| `#250` acquisition-day position cash flows missing for newly opened positions | Current service-layer evidence shows funded acquisition-day stock positions emit `internal_trade_flow` cash flows rather than an empty list. | Closure comment posted with current unit/service evidence; re-open only if fresh live cross-app artifacts still show `cash_flows=[]` on the acquisition day. |
| `#253` portfolio-timeseries versus position-timeseries reconciliation mismatch | Current service-layer evidence shows day-boundary capital continuity repair and internal cash-book settlement neutralization in portfolio observation aggregation. | Closure comment posted with current unit/service evidence; re-open only if fresh live cross-app artifacts still show the reported begin/end mismatch. |
| `#254` fresh seeded analytics windows do not mature beyond day one | Query-service maturity reporting now derives `performance_end_date` from the latest available analytics horizon across portfolio-timeseries and position-timeseries publication, so synthesized portfolio windows no longer appear stalled behind lagging persisted portfolio aggregate rows. | Code-level fix landed with unit regression coverage; keep open only until fresh canonical/live validation is re-run and captured. |
| `#258` internal trade legs misclassified as `external_flow` | Unit/service evidence now shows distinct `internal_trade_flow` versus `external_flow` behavior for the funded buy scenario. | Closure comment posted with current implementation evidence; re-open only if fresh live cross-app artifacts contradict the service tests. |
| `#260` staged external cash flows doubled in cash-only windows | Unit/service evidence now shows portfolio and position staged external flows remain `10000`, `5000`, `-2000` rather than doubling. | Closure comment posted with current implementation evidence; re-open only if fresh live cross-app artifacts contradict the service tests. |

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

Reviewed open benchmark-assignment-related issues:

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `#237` grouped benchmark analytics contract | Valid strategic follow-on. This is broader than assignment resolution and remains open. | Keep open. |
| `#246` broader benchmark source-contract hardening | Valid broader benchmark-program issue. Not a duplicate of this assignment endpoint slice. | Keep open. |
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
| `#246` broader benchmark source hardening | Still valid as the umbrella benchmark-source program. This slice closes documentation/truth gaps but does not claim the entire benchmark-source roadmap is finished. | Keep open. |
| `#237` grouped benchmark analytics contract | Still valid, but narrowed. `indices/catalog` now supports optional targeted `index_ids`, so downstream consumers no longer need a full index-catalog scan just to resolve known benchmark component metadata. The remaining gap is the absence of a first-class grouped benchmark analytics input contract. | Keep open as the grouped-contract follow-on, not as a catalog-scan workaround issue. |

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
| `lotus-core #237` grouped benchmark analytics contract | Still valid. Targeted `index_ids` removes the old full-catalog-scan pain, but downstream consumers still compose grouped benchmark analytics from lower-level contracts client-side. | Keep open as the grouped benchmark follow-on, not as a defect in the current reference family. |
| `lotus-core #246` broader benchmark source hardening | Still valid. This slice confirms the supporting reference contracts are truthful today, but does not claim the full benchmark-source program is complete. | Keep open. |
| `lotus-performance #125` downstream adoption of latest lotus-core benchmark/reference hardening | Still valid as downstream conformance work. Performance is the primary active consumer for this family and should keep tests, mocks, and runtime assumptions aligned to the tightened route descriptions and payload semantics. | Keep open until downstream adoption review is complete. |

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

### Issue Disposition For This Endpoint Family

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core #294` risk-free data missing for USD live window | Closed. Current repo and recorded live evidence indicate the issue was stale rather than a standing publication defect: the canonical front-office seed bundle extends USD risk-free series through `2026-05-10`, and the 2026-04-15 production-readiness closure records live USD coverage of `90` points with zero missing dates for `2026-01-01` to `2026-03-31`. | Re-open only if fresh canonical/live probes again show empty USD series for the governed window. |
| `lotus-risk #77` rolling Sharpe follow-up after upstream fix | Stale. `lotus-risk` now records the canonical portfolio as live validated for stateful `ROLLING_SHARPE` in `docs/operations/live-risk-validation-matrix.md`, so the original follow-up condition has already been satisfied. | Close in `lotus-risk` unless fresh live validation again fails for the governed canonical scenario. |
| `lotus-gateway #112` stale zero-risk-free fallback wording | Still valid product-surface issue in gateway. Core route semantics are now documented truthfully, but gateway rolling-risk messaging still needs to align. | Keep open in gateway. |
| `lotus-gateway #114` stale zero-risk-free fallback wording in summary supportability | Still valid product-surface issue in gateway. The risk summary surface should not imply a zero-risk-free Sharpe fallback unless gateway explicitly governs that methodology. | Keep open in gateway. |

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
| `lotus-advise #93` canonical core advisory simulation execution contract review | Opened in this pass. `lotus-advise` is the active direct consumer and already has dedicated client/test coverage, but the downstream adoption trail should explicitly track the certified contract-version, request-hash, idempotency, and problem-details semantics for this route. | Keep open in `lotus-advise` until downstream docs/tests are rechecked against the latest certified core contract. |

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
| `POST /integration/reference/classification-taxonomy` | No active direct caller evidenced in this pass | Catalog-intended route. The contract remains valid for governed shared taxonomy sourcing, but current downstream code search did not show a live direct caller that should be described as production-bound here yet. |

`lotus-performance`, `lotus-risk`, `lotus-gateway`, and `lotus-advise` remain catalog-intended
consumers because they rely on the same governed vocabulary, but this pass did not verify a live
direct caller that should be overstated as endpoint-specific production adoption.

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
| `lotus-advise #94` adopt lotus-core classification taxonomy to reduce local advisory label drift | Opened in this pass. `lotus-advise` still contains local asset-class/product-type classification heuristics in stateful context assembly, so the taxonomy route should be reviewed as the governed source for shared labels before those heuristics drift further. | Keep open in `lotus-advise` until advisory docs/tests and classification fallback posture are rechecked against the certified taxonomy route. |

The active need here is downstream taxonomy adoption and classification-coverage quality, not route
replacement inside lotus-core.

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

### Issue Disposition For This Endpoint Family

| Issue | Status in this pass | Action |
| --- | --- | --- |
| `lotus-gateway #116` | Still valid downstream adoption issue. Gateway is the active direct consumer of `overview` and `readiness`, and it must keep tests/docs aligned with the current operator-evidence boundary and 400-vs-404 error behavior. | Keep open in gateway until downstream validation closes it. |
| `lotus-manage #32` | Still valid future-adoption issue. No active direct client was evidenced in this pass, so manage should treat the issue as adoption guidance rather than proof of live dependency. | Keep open in manage until direct operator workflow binding exists and is tested. |
| `lotus-report #38` | Opened in this pass as future-adoption guidance. Report remains a catalog-intended support/evidence consumer, but this pass did not find active direct client code. | Keep open in report until direct workflow binding and tests exist. |

## Certified Endpoint Slice: Holdings Operational Read Family

This certification pass covers:

1. `GET /portfolios/{portfolio_id}/positions`
2. `POST /reporting/holdings-snapshot/query`

### Route Contract Decision

The strategic route in this family is `GET /portfolios/{portfolio_id}/positions`.

The boundary is now explicit:

1. use `GET /portfolios/{portfolio_id}/positions` for governed HoldingsAsOf operational reads,
   including booked as-of state and optional projected holdings state;
2. use `as_of_date` when the consumer needs booked state on or before a specific business date;
3. use `include_projected=true` only when the consumer intentionally wants future-dated projected
   holdings beyond the latest booked business date;
4. do not treat this route as a substitute for performance, risk, or reporting-specific
   aggregations;
5. `POST /reporting/holdings-snapshot/query` remains a deprecated convenience shape in the same
   `HoldingsAsOf` product family and should not be the default choice for new downstream bindings.

### Downstream Consumer Reality

| Route | Active downstream consumers verified | Integration posture |
| --- | --- | --- |
| `GET /portfolios/{portfolio_id}/positions` | `lotus-gateway` | Correct. Gateway uses the strategic positions route for portfolio position-book workflows. |
| `POST /reporting/holdings-snapshot/query` | No active direct downstream caller evidenced in this pass | Deprecated convenience shape. Core coverage remains strong, but this pass did not find a live downstream product binding that should be described as the preferred route. |

Gateway still also uses the deprecated sibling convenience route
`POST /reporting/cash-balances/query` in related holdings flows. That is now tracked as downstream
migration issue `lotus-gateway #119`.

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
   a generic positions list;
5. `POST /reporting/holdings-snapshot/query` remains documented as a deprecated convenience shape.

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
| `lotus-core` | No open issue | The strategic positions route is contract-tight in this pass. No open lotus-core defect was found against `GET /portfolios/{portfolio_id}/positions`. |
| `lotus-gateway #119` deprecated `cash-balances/query` usage in holdings flows | Open. Still valid as downstream adoption work. Gateway remains correctly bound to the strategic positions route for position-book reads, but related holdings workflows still depend on a deprecated convenience shape in the same product family. | Keep open until gateway narrows or removes deprecated `HoldingsAsOf` convenience-route dependence in holdings-position workflows. |

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
| `lotus-gateway #116` | Open | Still valid as downstream adoption work. Gateway is the active direct consumer and should keep aligning to the canonical snake_case query contract, default `lotus-gateway/default` resolution semantics, and the route's policy-diagnostics-only purpose. |

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
| `lotus-gateway #117` | Open | Active downstream defect. Gateway still sends camelCase query params to lotus-core capabilities in its core query client and should align to canonical snake_case `consumer_system` / `tenant_id`. |
| `lotus-gateway #73` | Open | Still valid, but it is a gateway aggregation-latency issue rather than a lotus-core publication defect. |
| `lotus-gateway #116` | Open | Remains the broader gateway adoption umbrella for recently hardened lotus-core control-plane routes, including capability and policy semantics. |
| `lotus-gateway #109` | Open | Adjacent downstream parameter-conformance issue for lotus-performance capabilities, not a lotus-core route defect. |

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
| `lotus-risk #93` | Open | Still valid as downstream adoption work. Risk is an active direct consumer and should keep its concentration and attribution tests aligned to deterministic response order, null unknown-security handling, and upstream-owned enrichment semantics. |
| `lotus-advise #92` | Open | Still valid as downstream adoption work. Advise is an active direct consumer and should keep stateful-context tests and mocks aligned to current enrichment semantics and null unknown-security handling. |

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
| `POST /integration/portfolios/{portfolio_id}/core-snapshot` | `lotus-gateway`, `lotus-risk` | Correct. Gateway uses the route for workspace state sourcing, and risk uses it for concentration and rolling-Sharpe currency/valuation context. No active direct `lotus-manage` or `lotus-advise` client was found in this pass. |

`lotus-manage` remains an intended consumer in the source-data catalog, but direct active code use
was not found in this pass and should not be overstated as live validated. The same is true for
`lotus-advise` on this specific route family: advisory work is currently anchored more strongly to
simulation and stateful-context seams than to direct `core-snapshot` reads.

One downstream mismatch was found in this pass: `lotus-gateway` foundation workspace tests and
parser helpers still model an older upstream payload shape with nested `portfolio` and `metadata`
blocks. That is not the governed `PortfolioStateSnapshot` contract. Gateway should read the
current top-level source-data runtime metadata, `portfolio_id`, `valuation_context`, and requested
`sections`, and only fetch separate portfolio identity context from dedicated routes when the UI
needs it. That concrete downstream defect is now tracked in `lotus-gateway #118`.

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
| `lotus-gateway #118` legacy `core-snapshot` envelope assumption in foundation workspace | Open. Still valid as downstream adoption work. Gateway foundation parsing and fixtures still rely on nested `portfolio` and `metadata` blocks that are not part of the governed `PortfolioStateSnapshot` contract. | Keep open until gateway foundation parsing and tests consume the top-level source-data runtime metadata plus `valuation_context` and `sections`. |

## Downstream Consumer Matrix

| Product | Governed route(s) | Intended consumers | Direct integration evidence reviewed | Test-pyramid posture |
| --- | --- | --- | --- | --- |
| `PortfolioStateSnapshot` | `POST /integration/portfolios/{portfolio_id}/core-snapshot` | `lotus-gateway`, `lotus-risk` | Direct active client evidence exists in `lotus-gateway/src/app/clients/lotus_core_query_client.py` and `lotus-risk/src/app/integrations/lotus_core_client.py`. `lotus-manage` currently documents intended adoption but does not yet have an active outbound client. `lotus-advise` currently uses other lotus-core seams more directly than `core-snapshot` itself. | Strong for gateway and risk. `lotus-manage` and `lotus-advise` remain catalog-intended and should not be described as live direct consumers of this route until their product flows bind to it. |
| `PositionTimeseriesInput` | `POST /integration/portfolios/{portfolio_id}/analytics/position-timeseries` | `lotus-performance`, `lotus-risk` | `lotus-performance` core integration and stateful attribution/contribution services; `lotus-risk/src/app/services/attribution_mode_adapter.py`. | Strong. Core route and schema tests, performance client tests, performance API/e2e mocked journey tests, and risk attribution adapter tests. |
| `PortfolioTimeseriesInput` | `POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries` | `lotus-performance` plus catalog-intended portfolio-level analytics consumers such as `lotus-risk` | `lotus-performance` returns/TWR source services and canonical TWR inspection script. Risk remains catalog-intended for portfolio-level analytics input, with current direct evidence stronger for position attribution and risk-free sources than for this route itself. | Strong for performance. Core catalog/OpenAPI tests protect the contract; risk portfolio-timeseries runtime use should be rechecked when risk portfolio-level analytics expands. |
| `PortfolioAnalyticsReference` | `POST /integration/portfolios/{portfolio_id}/analytics/reference` | `lotus-performance`, `lotus-gateway` | `lotus-performance` core integration service; `lotus-gateway` uses this route as workspace source context. `lotus-risk` remains governed but is not evidenced as a live direct caller in this pass. | Strong for performance and gateway direct usage. Risk should use this only where it needs analytics lifecycle/reference context, not operational holdings. |
| `MarketDataWindow` | `POST /integration/benchmarks/{benchmark_id}/market-series` | `lotus-performance` plus catalog-intended downstream benchmark consumers | Direct active code evidence in this pass exists for `lotus-performance` benchmark exposure/context services. Current `lotus-risk` architecture notes indicate active-risk attribution has moved away from direct benchmark market-series orchestration toward lotus-performance-owned derived benchmark exposure context. | Strong for performance benchmark path. Core catalog/OpenAPI tests protect route shape. Downstream direct-adoption claims beyond performance should stay narrow unless active product code resumes using the raw benchmark market-series contract. |
| `InstrumentReferenceBundle` | `POST /integration/instruments/enrichment-bulk`; `POST /integration/reference/classification-taxonomy` | `lotus-advise`, `lotus-risk` plus catalog-intended source-reference consumers | Direct active code evidence in this pass is strong for `enrichment-bulk` via `lotus-advise` and `lotus-risk`. Gateway and performance remain catalog-intended consumers for source-reference alignment, and taxonomy is currently documented as a governed shared-vocabulary route rather than an actively evidenced endpoint-specific integration. | Strong for enrichment direct client paths. Taxonomy publication is well documented and tested in core, but downstream direct-adoption evidence should be captured before it is described as a live endpoint-specific dependency. |
| `BenchmarkAssignment` | `POST /integration/portfolios/{portfolio_id}/benchmark-assignment` | `lotus-performance`, `lotus-gateway` | `lotus-performance` returns and benchmark services; `lotus-gateway/src/app/clients/lotus_core_query_client.py` for workspace composition context. `lotus-risk` and `lotus-report` remain catalog-intended rather than live direct consumers in this pass. | Strong for performance and gateway. `lotus-risk` and `lotus-report` should not be described as live direct consumers until product workflows bind to the route. |
| `BenchmarkConstituentWindow` | `POST /integration/benchmarks/{benchmark_id}/composition-window` | `lotus-performance` plus catalog-intended downstream benchmark consumers | `lotus-performance` benchmark engine and stateful benchmark input services provide the active direct code evidence in this pass. | Strong for performance, including benchmark path unit/integration/characterization coverage. Downstream consumers such as risk should avoid independently recreating performance benchmark orchestration unless a governed RFC requires raw benchmark inputs again. |
| `IndexSeriesWindow` | `POST /integration/indices/{index_id}/price-series`; `POST /integration/indices/{index_id}/return-series` | `lotus-performance` plus catalog-intended downstream benchmark consumers | `lotus-performance` execution and benchmark tests reference index price series and related sourcing paths. Current `lotus-risk` architecture notes in this pass do not evidence live direct raw index-series calls. | Strong for performance sourcing. Core OpenAPI/catalog tests protect both price and return routes. Downstream direct usage should be validated before risk or other apps are described as active consumers of the raw index-series contracts. |
| `RiskFreeSeriesWindow` | `POST /integration/reference/risk-free-series` | `lotus-performance`, `lotus-risk` | `lotus-performance` returns-series service; `lotus-risk` rolling mode adapter and live returns support. | Strong. Both performance and risk have direct tests around source retrieval/error handling, with core OpenAPI/catalog guards. |
| `ReconciliationEvidenceBundle` | `GET /support/portfolios/{portfolio_id}/reconciliation-runs`; `GET /support/portfolios/{portfolio_id}/reconciliation-runs/{run_id}/findings` | Catalog-intended operator consumers; no strong active direct caller evidenced in this pass | Governed support-plane evidence published correctly by lotus-core. The current detailed review supports the contract and dependency-lane behavior, but not a broad claim of live direct downstream product adoption yet. | Strong for core publication and dependency-lane behavior. `test_operations_router_dependency.py` covers success, 404, and 500 mappings for both routes. Downstream workflow validation is still needed before specific product surfaces are described as direct consumers. |
| `DataQualityCoverageReport` | `POST /integration/benchmarks/{benchmark_id}/coverage`; `POST /integration/reference/risk-free-series/coverage` | `lotus-risk` plus catalog-intended readiness/support consumers | Direct code evidence in this pass exists for `lotus-risk` consuming `risk-free-series/coverage`. Current canonical live proof also confirms both benchmark coverage and risk-free coverage are published correctly by lotus-core for the governed window, but this pass did not verify direct gateway/manage/performance product code calling those routes. | Strong for core publication and live readiness evidence. Downstream direct-adoption claims should stay narrow until product code paths for benchmark coverage or operator support callers are evidenced. |
| `IngestionEvidenceBundle` | `GET /lineage/portfolios/{portfolio_id}/keys`; `GET /support/portfolios/{portfolio_id}/reprocessing-keys`; `GET /support/portfolios/{portfolio_id}/reprocessing-jobs` | Catalog-intended operator consumers; no strong active direct caller evidenced in this pass | Core lineage and replay-support routes are present in OpenAPI and intentionally published as operational evidence rather than calculation inputs. The detailed review found support-plane readiness, but not enough downstream product-code evidence to call gateway/manage/report live direct consumers yet. | Strong for core route publication and dependency-lane behavior. `test_operations_router_dependency.py` covers lineage keys, reprocessing keys, and reprocessing jobs success plus 404/500 handling. Downstream operator-console/report workflows still need direct product validation before they can be called fully production-proven. |

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

