# Query Service and Control-Plane Boundary

## Purpose

This note defines the intended ownership split between:

- `query_service`
- `query_control_plane_service`

The goal is to keep the boundary explicit as the API surface grows, especially for
downstream analytics, integration, support, and simulation contracts.

This document is normative for **new endpoint placement**.

Platform RFC-0082 is the broader authority for downstream-facing `lotus-core`
domain authority and analytics-serving boundaries:

- `C:/Users/Sandeep/projects/lotus-platform/rfcs/RFC-0082-lotus-core-domain-authority-and-analytics-serving-boundary-hardening.md`

The current route-family inventory and watchlist is maintained in:

- `docs/architecture/RFC-0082-contract-family-inventory.md`

## Short Model

- `query_service` is the **canonical read engine**
- `query_control_plane_service` is the **curated external contract and support façade**

That means:

- `query_service` owns direct domain read models and reusable query logic
- `query_control_plane_service` owns governed contracts for downstream systems,
  support workflows, simulation workflows, and policy-aware integration surfaces
- RFC-0082 classifies all downstream-facing surfaces as operational reads,
  snapshot/simulation, analytics inputs, control-plane/policy, write ingress,
  or control execution

## Why Both Services Exist

We keep both services because they solve different problems.

### `query_service`

Owns:

- direct portfolio, position, transaction, instrument, price, and FX reads
- query-layer repositories and data assembly
- canonical domain read semantics
- reusable read-model logic consumed by other surfaces

This service answers:

- "What is the current or historical read state?"

### `query_control_plane_service`

Owns:

- downstream integration contracts
- analytics input products
- support and operations APIs
- simulation session orchestration APIs
- policy-aware snapshot and contract surfaces
- lineage/diagnostics-governed read façades
- export lifecycle contracts for large downstream retrievals

This service answers:

- "What is the supported external contract for a specific consumer or operational workflow?"

## Endpoint Placement Rule

Use this rule for every new API.

### Put an endpoint in `query_service` when:

1. it is a canonical domain read
2. it maps closely to one read model or one bounded query concern
3. it does not need consumer-specific policy evaluation
4. it does not need contract-governed lineage or support diagnostics beyond normal API behavior
5. it is primarily "fetch/filter/page the data"

Examples:

- portfolio discovery
- latest positions
- transaction ledgers
- price and FX series
- instrument reference reads
- domain drill-downs like BUY/SELL state

### Put an endpoint in `query_control_plane_service` when:

1. it exists primarily for downstream systems rather than direct domain browsing
2. it is a contract surface, not just a read surface
3. it requires policy evaluation, governance, lineage, diagnostics, or deterministic export semantics
4. it spans multiple read domains or orchestrates multiple query components
5. it supports support/ops or simulation workflows

Examples:

- analytics input contracts
- benchmark integration contracts
- core snapshot
- support overview and support drill-through APIs
- simulation sessions and projected views
- analytics export jobs

## Smell Test

If a proposed endpoint:

- only reads canonical data
- has no policy behavior
- has no consumer-specific contract semantics
- has no support, simulation, or governance role

then it probably belongs in `query_service`, not `query_control_plane_service`.

If a proposed endpoint:

- exists because `lotus-performance`, support tooling, or another downstream app needs a stable governed contract
- carries lineage, diagnostics, paging guarantees, or policy-aware behavior
- intentionally shapes data for a consumer workflow rather than exposing a raw read model

then it belongs in `query_control_plane_service`.

## Current Placement Assessment

### Clearly Correct in `query_service`

- `/portfolios`
- `/portfolios/{portfolio_id}`
- `/portfolios/{portfolio_id}/positions`
- `/portfolios/{portfolio_id}/position-history`
- `/portfolios/{portfolio_id}/transactions`
- `/instruments`
- `/prices`
- `/fx-rates`
- `/lookups/*`
- `/portfolios/{portfolio_id}/cashflow-projection`
- BUY/SELL state drill-down endpoints

Why:

- these are canonical read models or domain drill-downs
- they do not need policy-governed downstream contract wrapping

### Clearly Correct in `query_control_plane_service`

- `/integration/policy/effective`
- `/integration/portfolios/{portfolio_id}/core-snapshot`
- `/support/*`
- `/simulation-sessions/*`
- `/integration/capabilities/*`

Why:

- these are policy-aware, operational, simulation, or governed contract APIs

### Correct but Requires Discipline in `query_control_plane_service`

- `/integration/portfolios/{portfolio_id}/analytics/*`
- `/integration/benchmarks/*`
- `/integration/indices/*`
- `/integration/reference/*`
- `/integration/instruments/enrichment-bulk`

Why:

- these are valid control-plane contracts today
- but they sit closest to the line where control-plane can become a catch-all public read API
- the current RFC-0082 inventory marks these as watchlist areas requiring explicit review before material expansion

For current route-by-route classification, use:

- `docs/architecture/RFC-0082-contract-family-inventory.md`

## `integration.py` Endpoint-by-Endpoint Review

This section classifies the current `integration.py` surface using the placement rule above.

### Clearly belongs in `query_control_plane_service`

#### `GET /integration/policy/effective`

Call: **Correct**

Reason:

- pure policy/control-plane concern
- not a canonical read-model endpoint

#### `POST /integration/portfolios/{portfolio_id}/core-snapshot`

Call: **Correct**

Reason:

- policy-aware
- consumer-aware
- multi-section governed contract
- exactly the kind of façade control-plane should own

#### `POST /integration/portfolios/{portfolio_id}/benchmark-assignment`

Call: **Correct**

Reason:

- downstream-facing contract, not raw reference lookup
- deterministic effective-date resolution for external consumers

#### `POST /integration/benchmarks/{benchmark_id}/composition-window`

Call: **Correct**

Reason:

- purpose-built downstream benchmark contract
- carries window semantics shaped for analytics consumers

#### `POST /integration/benchmarks/{benchmark_id}/market-series`

Call: **Correct but high-risk**

Reason:

- this is a strong downstream contract with paging, quality, and lineage semantics
- that makes control-plane ownership reasonable
- but it is close enough to raw reference/query behavior that future expansion should be watched carefully

#### `POST /integration/benchmarks/{benchmark_id}/coverage`

Call: **Correct**

Reason:

- support/ops and readiness contract, not raw data retrieval

#### `POST /integration/reference/risk-free-series/coverage`

Call: **Correct**

Reason:

- readiness/coverage diagnostic surface
- belongs with contract governance

### Acceptable in `query_control_plane_service`, but borderline

#### `POST /integration/instruments/enrichment-bulk`

Call: **Borderline but acceptable**

Reason:

- semantically this could live in `query_service` as an enriched reference read
- it stays acceptable in control-plane only if we treat it as a stable downstream contract
- if it stays simple and read-only forever, it may be a candidate to move later

#### `POST /integration/benchmarks/{benchmark_id}/definition`

Call: **Borderline but acceptable**

Reason:

- looks close to a canonical reference-data query
- still acceptable because it is framed as a deterministic downstream benchmark contract

#### `POST /integration/benchmarks/catalog`

Call: **Borderline**

Reason:

- catalog discovery is very close to a plain reference-data read
- acceptable in control-plane if the contract is intentionally downstream-facing
- otherwise this is the kind of API that could drift into control-plane without needing to

#### `POST /integration/indices/catalog`

Call: **Borderline**

Reason:

- same reasoning as benchmark catalog
- not wrong, but closest to plain read-model discovery

#### `POST /integration/indices/{index_id}/price-series`

Call: **Borderline**

Reason:

- functionally close to `/prices`
- acceptable if the contract intentionally guarantees analytics-safe semantics for external consumers
- if it is just raw canonical series retrieval, it should live in `query_service`

#### `POST /integration/indices/{index_id}/return-series`

Call: **Borderline**

Reason:

- same pattern as price-series
- downstream-contract intent justifies control-plane
- raw-read evolution would not

#### `POST /integration/benchmarks/{benchmark_id}/return-series`

Call: **Borderline**

Reason:

- still acceptable because benchmark inputs are mainly consumed as downstream integration contracts
- but semantically very close to direct reference series retrieval

#### `POST /integration/reference/risk-free-series`

Call: **Borderline**

Reason:

- acceptable for downstream analytics contracts
- but it is one of the nearest examples to "query-service read wearing control-plane clothes"

#### `POST /integration/reference/classification-taxonomy`

Call: **Borderline**

Reason:

- canonical taxonomy retrieval could plausibly live in `query_service`
- it remains acceptable in control-plane if the contract is intended as the official external analytics taxonomy surface

## Decision Guidance for Future APIs

When a new API proposal arrives, answer these questions in order:

1. Is this endpoint exposing a canonical read model?
2. Is it mainly for downstream systems, support, or simulation?
3. Does it need policy, lineage, diagnostics, or governed paging/export semantics?
4. Is it composing multiple read domains into one contract?
5. Would moving it into control-plane create a new external contract that should be intentionally owned there?
6. Is it an analytics input product, or is it trying to return a downstream analytics conclusion?

If the answer pattern is mostly `1`, use `query_service`.

If the answer pattern is mostly `2` through `5`, use `query_control_plane_service`.

If the endpoint returns performance, risk, attribution, active-risk, or advisory
interpretation owned by another Lotus service, do not add it to `lotus-core`.

## Practical Guardrail

`query_control_plane_service` should not become the default home for every important read API.

That would create architectural drift where:

- `query_service` remains the engine
- but `query_control_plane_service` quietly becomes the only public query surface

That model can work, but only if we explicitly choose it.

Until then, the safer rule is:

- `query_service` for canonical reads
- `query_control_plane_service` for curated contracts
- downstream analytics authorities for analytics conclusions

## Review Trigger

Revisit this boundary when either of these becomes true:

1. a new control-plane router is mostly plain read-model retrieval
2. a `query_service` endpoint starts carrying downstream-specific lineage, policy, or contract-governance rules
3. any watchlist surface in `RFC-0082-contract-family-inventory.md` receives material expansion
4. a proposed endpoint would let `lotus-core` return downstream performance, risk, reporting-composition, or advisory recommendation behavior

Either case is a signal that the boundary is drifting and should be reviewed before more APIs are added.
