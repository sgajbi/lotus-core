# RFC-0083 Market And Reference Data Target Model

This document is the RFC-0083 Slice 7 target model for instrument master, market data, benchmark,
index, risk-free, and reference-series quality in `lotus-core`.

It does not change runtime behavior, persistence, DTOs, OpenAPI output, or downstream contracts. It
defines the target quality and lineage rules that later market/reference runtime slices must use.

The executable helper is:

1. `src/libs/portfolio-common/portfolio_common/market_reference_quality.py`
2. `tests/unit/libs/portfolio-common/test_market_reference_quality.py`

## Target Principle

Market and reference data are source-truth inputs, not enrichment decorations.

Every benchmark, index, risk-free, FX, price, instrument, and taxonomy product must make freshness,
completeness, and source-observation lineage explicit enough for `lotus-performance`, `lotus-risk`,
`lotus-gateway`, `lotus-advise`, and `lotus-report` to decide whether the source data is safe to use.

## Timestamp Decision

`observed_at` is the canonical timestamp for when an upstream source or vendor observed, emitted, or
published a data point.

Existing `source_timestamp` fields are legacy source-observed timestamps. Runtime migrations may keep
them until public contracts are changed, but new market/reference product DTOs must expose
`observed_at` or clearly map `source_timestamp` into `observed_at`.

`ingested_at` remains the timestamp when Lotus accepted the source record into the platform.

## Product Alignment

| Area | Target product | Required alignment |
| --- | --- | --- |
| Instrument master and taxonomy | `InstrumentReferenceBundle` | effective dating, source vendor, source record id, quality status, observed-at mapping |
| Market prices and FX rates | `MarketDataWindow` | price/rate business date, observed-at mapping, ingested-at lineage, freshness and completeness status |
| Benchmark assignment | `BenchmarkAssignment` | assignment version, policy pack, source system, effective date, product version |
| Benchmark composition | `BenchmarkConstituentWindow` | effective component window, rebalance event id, component source lineage, completeness status |
| Index series | `IndexSeriesWindow` | deterministic series ordering, observed-at mapping, quality status summary, export posture |
| Risk-free series | `RiskFreeSeriesWindow` | currency, series mode, convention metadata, observed-at mapping, coverage status |
| Data-quality diagnostics | `DataQualityCoverageReport` | required/observed/stale/blocking counts and target status vocabulary |

## Quality Status Mapping

| Source quality status | Target treatment |
| --- | --- |
| `accepted` | `COMPLETE` when a source-observed timestamp is available |
| `estimated`, `provisional`, `warning` | `PARTIAL` |
| `stale` | `STALE` |
| `rejected`, `quarantined`, `invalid`, `blocked` | `BLOCKED` |
| blank or unknown values | `UNKNOWN` |

Freshness flags override otherwise accepted quality and produce `STALE`. Blocking quality wins over
freshness.

## Coverage Classification

Coverage diagnostics use the same target status vocabulary as RFC-0083 Slice 5:

1. blocking source issues produce `BLOCKED`,
2. zero required points produce `UNKNOWN`,
3. zero observed points for a required scope produce `UNRECONCILED`,
4. stale points produce `STALE`,
5. estimated or partial observations produce `PARTIAL`,
6. fully observed accepted data produces `COMPLETE`.

## Runtime Follow-Up

Future market/reference runtime slices must:

1. add product identity and version metadata from the source-data product catalog,
2. expose `observed_at` or explicitly map legacy `source_timestamp`,
3. carry `ingested_at` where Lotus ingestion time affects supportability,
4. carry `quality_status` and aggregate quality summaries,
5. emit freshness/completeness diagnostics through `DataQualityCoverageReport`,
6. preserve deterministic paging/export behavior for large series windows,
7. update downstream consumer tests when response semantics change.

## Validation

Slice 7 validation is:

1. `python -m pytest tests/unit/libs/portfolio-common/test_market_reference_quality.py -q`,
2. `python -m ruff check src/libs/portfolio-common/portfolio_common/market_reference_quality.py tests/unit/libs/portfolio-common/test_market_reference_quality.py --ignore E501,I001`,
3. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/market_reference_quality.py tests/unit/libs/portfolio-common/test_market_reference_quality.py`,
4. `git diff --check`,
5. `make lint`.
