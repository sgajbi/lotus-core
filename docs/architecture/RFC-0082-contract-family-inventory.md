# RFC-0082 Contract Family Inventory

## Purpose

This document is the Slice 1 inventory for platform RFC-0082:

- `C:/Users/Sandeep/projects/lotus-platform/rfcs/RFC-0082-lotus-core-domain-authority-and-analytics-serving-boundary-hardening.md`

It classifies active downstream-facing `lotus-core` API surfaces into the RFC-0082 contract families:

1. operational reads,
2. snapshot and simulation,
3. analytics inputs,
4. control-plane and policy,
5. write ingress,
6. control execution.

RFC-0082 defines the first four families as downstream-serving `lotus-core` contract families. This inventory also records write-ingress and control-execution surfaces because they are active APIs and affect downstream platform behavior, even though they are not analytics-serving read contracts.

## Inventory Date

2026-04-14

## Scope

Included active router roots:

1. `src/services/query_service/app/routers/`
2. `src/services/query_control_plane_service/app/routers/`
3. `src/services/ingestion_service/app/routers/`
4. `src/services/event_replay_service/app/routers/`
5. `src/services/financial_reconciliation_service/app/routers/`

Excluded:

1. service health endpoints,
2. metrics endpoints,
3. internal Kafka event contracts,
4. internal service methods without HTTP exposure.

## Contract Family Definitions

| Family | Definition | Owning runtime |
| --- | --- | --- |
| Operational Read | Canonical portfolio, position, transaction, market, lookup, and reporting-oriented read models. | `query_service` |
| Snapshot And Simulation | Governed state bundles, simulation session state, and projected state views. | `query_control_plane_service` |
| Analytics Input | Deterministic input products for downstream analytics engines, including timeseries, benchmark, index, taxonomy, risk-free, and export lifecycle contracts. | `query_control_plane_service` |
| Control-Plane And Policy | Capability, policy, support, lineage, replay, health, and operator diagnostics contracts. | `query_control_plane_service`, `event_replay_service` |
| Write Ingress | Canonical write-ingress and adapter upload contracts that mutate or enqueue source data. | `ingestion_service` |
| Control Execution | Reconciliation and control execution APIs that create or inspect financial control runs. | `financial_reconciliation_service` |

## Executive Assessment

Current placement is mostly aligned with RFC-0082.

Strengths:

1. operational reads are concentrated in `query_service`,
2. analytics input, snapshot, simulation, and support contracts are concentrated in `query_control_plane_service`,
3. replay and ingestion operations are split out into `event_replay_service`,
4. financial reconciliation execution has an independent service boundary,
5. analytics behavior remains de-owned from `lotus-core`; current analytics contracts provide inputs, not performance or risk conclusions.

Main risks:

1. several `/integration/benchmarks`, `/integration/indices`, and `/integration/reference` contracts are close to raw reference-data reads and require continued discipline to avoid turning the control plane into a generic read surface,
2. `/reporting/*` endpoints are operational reads today, but could drift into report-composition ownership if they start returning product-facing narratives or analytics conclusions,
3. `/integration/instruments/enrichment-bulk` is acceptable as a downstream enrichment contract but remains a borderline placement if it stays a plain reference read,
4. ingestion adapter paths are useful but must remain clearly marked as write-ingress or adapter workflows, not canonical downstream read contracts.

## Inventory Summary

| Runtime | Route group | Family | Assessment | Primary consumers |
| --- | --- | --- | --- | --- |
| `query_service` | `/portfolios/*` | Operational Read | Correct | `lotus-gateway`, `lotus-manage`, support tooling |
| `query_service` | `/instruments`, `/prices`, `/fx-rates`, `/lookups/*` | Operational Read | Correct | gateway, analytics services, support tooling |
| `query_service` | `/reporting/*/query` | Operational Read | Correct, watch for reporting-composition drift | `lotus-report`, gateway, support tooling |
| `query_control_plane_service` | `/integration/portfolios/*/analytics/*` | Analytics Input | Correct | `lotus-performance`, `lotus-risk`, reporting consumers |
| `query_control_plane_service` | `/integration/exports/analytics-timeseries/*` | Analytics Input | Correct | `lotus-performance`, batch/reporting consumers |
| `query_control_plane_service` | `/integration/portfolios/*/core-snapshot` | Snapshot And Simulation | Correct | `lotus-manage`, gateway, support tooling |
| `query_control_plane_service` | `/simulation-sessions/*` | Snapshot And Simulation | Correct | `lotus-advise`, `lotus-manage`, gateway |
| `query_control_plane_service` | `/integration/benchmarks/*`, `/integration/indices/*`, `/integration/reference/*` | Analytics Input | Correct but high-discipline boundary | `lotus-performance`, `lotus-risk` |
| `query_control_plane_service` | `/integration/policy/effective`, `/integration/capabilities` | Control-Plane And Policy | Correct | all downstream services |
| `query_control_plane_service` | `/support/*`, `/lineage/*` | Control-Plane And Policy | Correct | support tooling, operators, gateway diagnostics |
| `ingestion_service` | `/ingest/*`, `/reprocess/transactions` | Write Ingress | Correct | onboarding, seed, platform automation |
| `event_replay_service` | `/ingestion/jobs/*`, `/ingestion/health/*`, `/ingestion/dlq/*`, `/ingestion/audit/*`, `/ingestion/ops/*` | Control-Plane And Policy | Correct | operators, automation, QA |
| `financial_reconciliation_service` | `/reconciliation/*` | Control Execution | Correct | orchestrator, operators, QA |

Local ingress names follow the same split: `core-query.dev.lotus` reaches
`query_service` on port `8201`, while `core-control.dev.lotus` reaches
`query_control_plane_service` on port `8202`. Downstream analytics consumers
must use the control-plane base URL for `/integration/portfolios/*/analytics/*`
contracts.

## Detailed Route Inventory

### `query_service`: Operational Read Contracts

These endpoints expose canonical read models and domain drill-downs. They are correctly placed in `query_service` because they do not require consumer-specific policy, export lifecycle, or analytics-serving semantics.

| Route | Family | Consumers | Assessment | Notes |
| --- | --- | --- | --- | --- |
| `GET /portfolios/` | Operational Read | gateway, manage, support | Correct | Portfolio discovery and listing. |
| `GET /portfolios/{portfolio_id}` | Operational Read | gateway, manage, support | Correct | Canonical portfolio detail. |
| `GET /portfolios/{portfolio_id}/positions` | Operational Read | gateway, manage, support | Correct | Latest position read model. |
| `GET /portfolios/{portfolio_id}/position-history` | Operational Read | gateway, manage, support | Correct | Historical position read model. |
| `GET /portfolios/{portfolio_id}/transactions` | Operational Read | gateway, manage, support | Correct | Transaction ledger read model. |
| `GET /portfolios/{portfolio_id}/cash-accounts` | Operational Read | gateway, manage, support | Correct | Cash account state. |
| `GET /portfolios/{portfolio_id}/cashflow-projection` | Operational Read | gateway, manage, support | Correct, monitor semantics | Acceptable while it remains core-derived cashflow state; do not expand into performance forecasting. |
| `GET /portfolios/{portfolio_id}/positions/{security_id}/lots` | Operational Read | gateway, support | Correct | BUY state drill-down. |
| `GET /portfolios/{portfolio_id}/positions/{security_id}/accrued-offsets` | Operational Read | gateway, support | Correct | BUY/accrual state drill-down. |
| `GET /portfolios/{portfolio_id}/transactions/{transaction_id}/cash-linkage` | Operational Read | gateway, support | Correct | BUY cash linkage. |
| `GET /portfolios/{portfolio_id}/positions/{security_id}/sell-disposals` | Operational Read | gateway, support | Correct | SELL state drill-down. |
| `GET /portfolios/{portfolio_id}/transactions/{transaction_id}/sell-cash-linkage` | Operational Read | gateway, support | Correct | SELL cash linkage. |
| `GET /instruments/` | Operational Read | gateway, analytics services, support | Correct | Canonical instrument reference read. |
| `GET /prices/` | Operational Read | gateway, analytics services, support | Correct | Raw market price read. |
| `GET /fx-rates/` | Operational Read | gateway, analytics services, support | Correct | FX rate read. |
| `GET /lookups/portfolios` | Operational Read | UI, gateway, support | Correct | Lookup catalog. |
| `GET /lookups/instruments` | Operational Read | UI, gateway, support | Correct | Lookup catalog. |
| `GET /lookups/currencies` | Operational Read | UI, gateway, support | Correct | Lookup catalog. |

### `query_service`: Reporting-Oriented Reads

These endpoints are currently classified as operational read contracts because they expose source-data summaries and ledger/query views. They must not drift into `lotus-report` document-generation ownership or downstream analytics ownership.

| Route | Family | Consumers | Assessment | Notes |
| --- | --- | --- | --- | --- |
| `POST /reporting/assets-under-management/query` | Operational Read | `lotus-report`, gateway | Correct, watch | Source-data query, not report composition. |
| `POST /reporting/asset-allocation/query` | Operational Read | `lotus-report`, gateway | Correct, watch | Must remain core-held allocation source truth. |
| `POST /reporting/cash-balances/query` | Operational Read | `lotus-report`, gateway | Deprecated convenience shape | Cash source-data summary; target product is `HoldingsAsOf`. |
| `POST /reporting/portfolio-summary/query` | Operational Read | `lotus-report`, gateway | Correct, watch | Avoid absorbing analytics narrative. |
| `POST /reporting/holdings-snapshot/query` | Operational Read | `lotus-report`, gateway | Deprecated convenience shape | Holdings snapshot query; target product is `HoldingsAsOf`. |
| `POST /reporting/income-summary/query` | Operational Read | `lotus-report`, gateway | Deprecated convenience shape | Income source-data summary; target product is `TransactionLedgerWindow`. |
| `POST /reporting/activity-summary/query` | Operational Read | `lotus-report`, gateway | Deprecated convenience shape | Transaction/activity source-data summary; target product is `TransactionLedgerWindow`. |

### `query_control_plane_service`: Analytics Input Contracts

These are first-class downstream input products under RFC-0082. They are correctly placed in `query_control_plane_service` because they include deterministic request scope, downstream contract semantics, paging/export behavior, or analytics-safe reference shaping.

| Route | Family | Consumers | Assessment | Notes |
| --- | --- | --- | --- | --- |
| `POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries` | Analytics Input | `lotus-performance`, `lotus-risk` | Correct | Canonical portfolio valuation/cashflow input product. |
| `POST /integration/portfolios/{portfolio_id}/analytics/position-timeseries` | Analytics Input | `lotus-performance`, `lotus-risk` | Correct | Canonical position-level analytics input product. |
| `POST /integration/portfolios/{portfolio_id}/analytics/reference` | Analytics Input | `lotus-performance`, `lotus-risk` | Correct | Portfolio reference metadata for analytics context. |
| `POST /integration/exports/analytics-timeseries/jobs` | Analytics Input | `lotus-performance`, batch/reporting | Correct | Large retrieval lifecycle contract. |
| `GET /integration/exports/analytics-timeseries/jobs/{job_id}` | Analytics Input | `lotus-performance`, batch/reporting | Correct | Export job status. |
| `GET /integration/exports/analytics-timeseries/jobs/{job_id}/result` | Analytics Input | `lotus-performance`, batch/reporting | Correct | Export result retrieval. |

### `query_control_plane_service`: Benchmark, Index, And Reference Input Contracts

These are valid analytics-input contracts, but they are closest to the query/control-plane boundary. Future additions in this area require explicit review against RFC-0082.

| Route | Family | Consumers | Assessment | Notes |
| --- | --- | --- | --- | --- |
| `POST /integration/portfolios/{portfolio_id}/benchmark-assignment` | Analytics Input | `lotus-performance`, `lotus-risk` | Correct | Effective portfolio-to-benchmark assignment. |
| `POST /integration/benchmarks/{benchmark_id}/composition-window` | Analytics Input | `lotus-performance`, `lotus-risk` | Correct | Windowed benchmark composition contract. |
| `POST /integration/benchmarks/{benchmark_id}/definition` | Analytics Input | `lotus-performance`, `lotus-risk` | Borderline but acceptable | Reference-data query shape; acceptable because it is a governed downstream contract. |
| `POST /integration/benchmarks/catalog` | Analytics Input | `lotus-performance`, `lotus-risk`, support | Borderline | Catalog discovery can resemble plain read-model access. Keep explicit downstream-contract framing. |
| `POST /integration/indices/catalog` | Analytics Input | `lotus-performance`, `lotus-risk`, support | Borderline | Same risk as benchmark catalog. |
| `POST /integration/benchmarks/{benchmark_id}/market-series` | Analytics Input | `lotus-performance`, `lotus-risk` | Correct, high-discipline | Strong downstream contract; keep paging/quality/lineage semantics explicit. |
| `POST /integration/indices/{index_id}/price-series` | Analytics Input | `lotus-performance`, `lotus-risk` | Borderline | Close to `/prices`; acceptable only as analytics-safe series contract. |
| `POST /integration/indices/{index_id}/return-series` | Analytics Input | `lotus-performance`, `lotus-risk` | Borderline | Keep downstream-contract semantics explicit. |
| `POST /integration/benchmarks/{benchmark_id}/return-series` | Analytics Input | `lotus-performance`, `lotus-risk` | Borderline | Raw benchmark return series, governed for analytics consumers. |
| `POST /integration/reference/risk-free-series` | Analytics Input | `lotus-performance`, `lotus-risk` | Borderline | Could resemble reference read; retain because it is analytics input. |
| `POST /integration/reference/classification-taxonomy` | Analytics Input | `lotus-performance`, `lotus-risk` | Borderline | Canonical taxonomy retrieval; must remain explicit about downstream analytics use. |
| `POST /integration/benchmarks/{benchmark_id}/coverage` | Control-Plane And Policy | operators, analytics services | Correct | Coverage/readiness diagnostic, not raw data retrieval. |
| `POST /integration/reference/risk-free-series/coverage` | Control-Plane And Policy | operators, analytics services | Correct | Coverage/readiness diagnostic. |

### `query_control_plane_service`: Snapshot And Simulation Contracts

| Route | Family | Consumers | Assessment | Notes |
| --- | --- | --- | --- | --- |
| `POST /integration/portfolios/{portfolio_id}/core-snapshot` | Snapshot And Simulation | `lotus-manage`, gateway, support | Correct | Governed sectioned snapshot. Must not regain analytics sections. |
| `POST /simulation-sessions` | Snapshot And Simulation | `lotus-advise`, `lotus-manage`, gateway | Correct | Simulation session lifecycle. |
| `GET /simulation-sessions/{session_id}` | Snapshot And Simulation | `lotus-advise`, `lotus-manage`, gateway | Correct | Simulation state read. |
| `DELETE /simulation-sessions/{session_id}` | Snapshot And Simulation | `lotus-advise`, `lotus-manage`, gateway | Correct | Simulation lifecycle. |
| `POST /simulation-sessions/{session_id}/changes` | Snapshot And Simulation | `lotus-advise`, `lotus-manage`, gateway | Correct | Simulation mutation. |
| `DELETE /simulation-sessions/{session_id}/changes/{change_id}` | Snapshot And Simulation | `lotus-advise`, `lotus-manage`, gateway | Correct | Simulation mutation rollback. |
| `GET /simulation-sessions/{session_id}/projected-positions` | Snapshot And Simulation | `lotus-advise`, `lotus-manage`, gateway | Correct | Projected state, not analytics conclusion. |
| `GET /simulation-sessions/{session_id}/projected-summary` | Snapshot And Simulation | `lotus-advise`, `lotus-manage`, gateway | Correct, monitor | Must not become proposal/advisory recommendation logic. |
| `POST /integration/advisory/proposals/simulate-execution` | Snapshot And Simulation | `lotus-advise` | Correct, monitor | Acceptable as core execution projection; advisory decision logic remains outside core. |

### `query_control_plane_service`: Policy, Support, And Lineage Contracts

| Route | Family | Consumers | Assessment | Notes |
| --- | --- | --- | --- | --- |
| `GET /integration/policy/effective` | Control-Plane And Policy | all downstream services | Correct | Policy diagnostics and provenance. |
| `GET /integration/capabilities` | Control-Plane And Policy | all downstream services | Correct | Capability discovery. |
| `POST /integration/instruments/enrichment-bulk` | Analytics Input | analytics services, gateway | Borderline but acceptable | Valid as governed enrichment contract; candidate for future placement review if it remains plain reference lookup. |
| `GET /support/portfolios/{portfolio_id}/overview` | Control-Plane And Policy | support, operations, QA | Correct | Support overview. |
| `GET /support/portfolios/{portfolio_id}/readiness` | Control-Plane And Policy | support, operations, QA | Correct | Readiness diagnostics. |
| `GET /support/portfolios/{portfolio_id}/calculator-slos` | Control-Plane And Policy | support, operations, QA | Correct | SLO diagnostics. |
| `GET /support/portfolios/{portfolio_id}/control-stages` | Control-Plane And Policy | support, operations, QA | Correct | Control stage diagnostics. |
| `GET /support/portfolios/{portfolio_id}/reprocessing-keys` | Control-Plane And Policy | support, operations, QA | Correct | Reprocessing support. |
| `GET /support/portfolios/{portfolio_id}/reprocessing-jobs` | Control-Plane And Policy | support, operations, QA | Correct | Reprocessing support. |
| `GET /support/portfolios/{portfolio_id}/valuation-jobs` | Control-Plane And Policy | support, operations, QA | Correct | Valuation support. |
| `GET /support/portfolios/{portfolio_id}/aggregation-jobs` | Control-Plane And Policy | support, operations, QA | Correct | Aggregation support. |
| `GET /support/portfolios/{portfolio_id}/analytics-export-jobs` | Control-Plane And Policy | support, operations, QA | Correct | Analytics export support visibility. |
| `GET /support/portfolios/{portfolio_id}/reconciliation-runs` | Control-Plane And Policy | support, operations, QA | Correct | Reconciliation visibility. |
| `GET /support/portfolios/{portfolio_id}/reconciliation-runs/{run_id}/findings` | Control-Plane And Policy | support, operations, QA | Correct | Reconciliation finding visibility. |
| `GET /lineage/portfolios/{portfolio_id}/securities/{security_id}` | Control-Plane And Policy | support, operations, QA | Correct | Lineage diagnostics. |
| `GET /lineage/portfolios/{portfolio_id}/keys` | Control-Plane And Policy | support, operations, QA | Correct | Lineage discovery. |

### `ingestion_service`: Write Ingress Contracts

These are not downstream read contracts. They are included so RFC-0082 implementers do not confuse write-ingress ownership with downstream analytics-serving ownership.

| Route | Family | Consumers | Assessment | Notes |
| --- | --- | --- | --- | --- |
| `POST /ingest/transaction` | Write Ingress | upstream feeds, automation | Correct | Canonical single transaction ingress. |
| `POST /ingest/transactions` | Write Ingress | upstream feeds, automation | Correct | Batch transaction ingress. |
| `POST /ingest/portfolios` | Write Ingress | upstream feeds, automation | Correct | Portfolio master ingress. |
| `POST /ingest/portfolio-bundle` | Write Ingress | onboarding, UI adapters, automation | Correct, adapter discipline required | Must remain governed adapter/onboarding path. |
| `POST /ingest/uploads/preview` | Write Ingress | onboarding, UI adapters | Correct, adapter discipline required | Preview-only adapter path. |
| `POST /ingest/uploads/commit` | Write Ingress | onboarding, UI adapters | Correct, adapter discipline required | Commit adapter path. |
| `POST /ingest/instruments` | Write Ingress | upstream feeds, automation | Correct | Instrument ingress. |
| `POST /ingest/market-prices` | Write Ingress | upstream feeds, automation | Correct | Market price ingress. |
| `POST /ingest/fx-rates` | Write Ingress | upstream feeds, automation | Correct | FX rate ingress. |
| `POST /ingest/business-dates` | Write Ingress | upstream feeds, automation | Correct | Calendar/business date ingress. |
| `POST /ingest/benchmark-assignments` | Write Ingress | upstream feeds, automation | Correct | Benchmark assignment ingress. |
| `POST /ingest/benchmark-definitions` | Write Ingress | upstream feeds, automation | Correct | Benchmark definition ingress. |
| `POST /ingest/benchmark-compositions` | Write Ingress | upstream feeds, automation | Correct | Benchmark composition ingress. |
| `POST /ingest/indices` | Write Ingress | upstream feeds, automation | Correct | Index reference ingress. |
| `POST /ingest/index-price-series` | Write Ingress | upstream feeds, automation | Correct | Index price series ingress. |
| `POST /ingest/index-return-series` | Write Ingress | upstream feeds, automation | Correct | Index return series ingress. |
| `POST /ingest/benchmark-return-series` | Write Ingress | upstream feeds, automation | Correct | Benchmark return series ingress. |
| `POST /ingest/risk-free-series` | Write Ingress | upstream feeds, automation | Correct | Risk-free source ingress. |
| `POST /ingest/reference/classification-taxonomy` | Write Ingress | upstream feeds, automation | Correct | Classification taxonomy ingress. |
| `POST /ingest/reference/cash-accounts` | Write Ingress | upstream feeds, automation | Correct | Cash account reference ingress. |
| `POST /ingest/reference/instrument-lookthrough-components` | Write Ingress | upstream feeds, automation | Correct | Lookthrough component ingress. |
| `POST /reprocess/transactions` | Write Ingress | operations, automation | Correct | Reprocessing request ingress; control visibility belongs in replay/support surfaces. |

### `event_replay_service`: Replay And Ingestion Operations Contracts

These are control-plane contracts. They should remain separate from ingestion write ingress and from downstream analytics input surfaces.

| Route group | Family | Consumers | Assessment | Notes |
| --- | --- | --- | --- | --- |
| `/ingestion/jobs/*` | Control-Plane And Policy | operators, automation, QA | Correct | Job inspection, failures, records, retry. |
| `/ingestion/health/*` | Control-Plane And Policy | operators, automation, QA | Correct | Health, lag, SLO, policy, capacity, backlog, stalled jobs. |
| `/ingestion/dlq/*` | Control-Plane And Policy | operators, automation, QA | Correct | DLQ listing and replay. |
| `/ingestion/audit/replays*` | Control-Plane And Policy | operators, automation, QA | Correct | Replay audit lineage. |
| `/ingestion/ops/control` | Control-Plane And Policy | operators, automation | Correct | Operations mode control. |
| `/ingestion/idempotency/diagnostics` | Control-Plane And Policy | operators, QA | Correct | Idempotency diagnostics. |

### `financial_reconciliation_service`: Control Execution Contracts

These contracts execute or inspect control runs. They are intentionally not `query_service` reads and not analytics product outputs.

| Route | Family | Consumers | Assessment | Notes |
| --- | --- | --- | --- | --- |
| `POST /reconciliation/runs/transaction-cashflow` | Control Execution | orchestrator, operators, QA | Correct | Transaction-cashflow control run. |
| `POST /reconciliation/runs/position-valuation` | Control Execution | orchestrator, operators, QA | Correct | Position-valuation control run. |
| `POST /reconciliation/runs/timeseries-integrity` | Control Execution | orchestrator, operators, QA | Correct | Timeseries-integrity control run. |
| `GET /reconciliation/runs` | Control Execution | operators, QA | Correct | Control run listing. |
| `GET /reconciliation/runs/{run_id}` | Control Execution | operators, QA | Correct | Control run detail. |
| `GET /reconciliation/runs/{run_id}/findings` | Control Execution | operators, QA | Correct | Control finding detail. |

## Overlap And Watchlist

The following surfaces are acceptable today but should receive explicit review before material expansion.

| Surface | Concern | Current decision | Required guardrail |
| --- | --- | --- | --- |
| `/integration/benchmarks/catalog` | Can look like plain reference read. | Keep in control plane as downstream analytics contract. | Preserve downstream-contract framing and avoid generic catalog sprawl. |
| `/integration/indices/catalog` | Can look like plain reference read. | Keep in control plane as downstream analytics contract. | Same as benchmark catalog. |
| `/integration/indices/{index_id}/price-series` | Overlaps conceptually with `/prices`. | Keep only if analytics-safe semantics stay explicit. | Document why direct `/prices` is insufficient for downstream analytics use. |
| `/integration/reference/risk-free-series` | Can become generic reference read. | Keep as analytics input. | Keep request semantics and consumer usage explicit. |
| `/integration/reference/classification-taxonomy` | Can become generic taxonomy lookup. | Keep as analytics input. | Maintain canonical analytics taxonomy framing. |
| `/integration/instruments/enrichment-bulk` | Could live in `query_service` if it is only plain reference lookup. | Keep as downstream enrichment contract for now. | Revisit if it does not carry governed downstream semantics. |
| `/reporting/*/query` | Can drift into report composition or analytics narrative. | Keep as operational read; selected convenience shapes are deprecated in OpenAPI pending source-data product migration. | Keep `lotus-report` and analytics services as owners of downstream composition. |
| `/portfolios/{portfolio_id}/cashflow-projection` | Can drift into forecasting or performance interpretation. | Keep as operational read. | Restrict to core-derived cashflow state. |
| `/simulation-sessions/{session_id}/projected-summary` | Can drift into advisory recommendations. | Keep as simulation state. | Keep recommendation/proposal logic outside `lotus-core`. |

## Consumer Map

| Consumer | Intended `lotus-core` families | Must not consume `lotus-core` for |
| --- | --- | --- |
| `lotus-performance` | analytics inputs, benchmark/reference inputs, operational reads only where source truth is needed | delegated performance calculations, attribution interpretation owned by performance |
| `lotus-risk` | analytics inputs, benchmark/reference inputs, selected operational reads, performance outputs through `lotus-performance` where governed | delegated risk calculations, active-risk narrative, issuer risk interpretation owned by risk |
| `lotus-gateway` | operational reads, snapshots, simulation state, downstream product outputs from authoritative analytics services | recomputing performance/risk analytics from raw core data |
| `lotus-manage` | operational reads, snapshots, simulation state, management workflow state requirements | parallel foundational state ownership |
| `lotus-report` | operational reporting reads, analytics outputs from authoritative analytics services where required | document composition inside `lotus-core` |
| operators and QA | control-plane, policy, replay, support, reconciliation, lineage | business workflow shortcuts that bypass domain services |

## Required Next Actions

### P0

1. Cross-link this inventory from `REPOSITORY-ENGINEERING-CONTEXT.md`.
2. Reference this inventory from platform RFC-0082 implementation evidence once the first slice is accepted.
3. Use this inventory in architecture review for any new downstream-facing `lotus-core` endpoint.

### P1

1. Add explicit route-description checks or documentation review for watchlist surfaces when they change.
2. Add consumer conformance tests for `lotus-performance` analytics-input usage. Completed through
   `scripts/analytics_input_consumer_contract_guard.py`, which verifies that declared
   `lotus-performance` source-data products stay on the query control plane and that the governed
   analytics cash-flow vocabulary remains canonical.
3. Add consumer conformance notes for `lotus-risk` upstream dependency usage. Completed through
   `scripts/analytics_input_consumer_contract_guard.py`, which verifies that declared `lotus-risk`
   source-data products cover operational holdings, transaction windows, snapshot state,
   analytics-input market/reference products, and evidence products on the governed serving planes.

### P2

1. Consider generating this inventory from OpenAPI plus curated family annotations.
2. Add a lightweight ownership annotation file if manual upkeep becomes unreliable.
3. Revisit borderline control-plane reference contracts after retrieval-performance profiling.

## Validation Guidance

This inventory now has an RFC-0083 Slice 2 machine-readable enforcement companion:

1. `docs/standards/route-contract-family-registry.json`
2. `scripts/route_contract_family_guard.py`
3. `make route-contract-family-guard`

Recommended validation for route-family changes:

1. update this prose inventory when ownership semantics change,
2. update `docs/standards/route-contract-family-registry.json` for any route add/remove/family change,
3. run `make route-contract-family-guard`,
4. run `python -m pytest tests/unit/scripts/test_route_contract_family_guard.py -q`.

If later slices modify route behavior or OpenAPI descriptions, use the RFC-0082 validation lane map in the platform RFC.
