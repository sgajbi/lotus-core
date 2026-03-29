# Manual Portfolio Performance Benchmark Seed Runbook

This runbook seeds the missing local `lotus-core` reference data required for the
manual portfolio performance workstation to return benchmark-linked data for:

- `MANUAL_PB_USD_001`
- gateway performance summary/details
- `lotus-performance` stateful portfolio analytics inputs

This runbook is intentionally local-stack scoped. It does not depend on `lotus-manage`.

## Problem This Fixes

The manual portfolio bootstrap created:

- portfolio, instrument, transaction, and current market-value state

but it did not create the historical reference inputs required by `lotus-performance`:

- business-date coverage for the manual performance window
- daily market prices for the manual securities
- daily EUR/USD FX coverage across the same window
- benchmark assignment, definitions, components, and return/reference series

Without those inputs, the live gateway performance endpoints returned empty or partial payloads with errors such as:

- `Missing FX rate for EUR/USD on 2026-03-03`
- `No effective benchmark assignment found for portfolio and as_of_date`
- `Benchmark composition window does not cover requested date 2026-01-05`
- `Benchmark market-series coverage is incomplete`

## Preconditions

The local stack must already be up:

- `lotus-core` ingestion/query/query-control-plane
- `lotus-performance`
- `lotus-gateway`

Expected local endpoints:

- ingestion: `http://127.0.0.1:8200`
- query control plane: `http://127.0.0.1:8202`
- gateway: `http://127.0.0.1:8100`

## Operator Command

Run from the `lotus-core` repo root:

```powershell
python tools/manual_performance_seed.py `
  --portfolio-id MANUAL_PB_USD_001 `
  --start-date 2026-03-03 `
  --end-date 2026-03-28 `
  --benchmark-start-date 2026-01-05 `
  --sleep-seconds 45
```

## What The Tool Does

The tool:

1. deletes any existing local benchmark seed rows for the target benchmark and its component indices
2. ingests business dates for the manual valuation window
3. ingests daily market prices for the 9 manual portfolio instruments
4. ingests calendar-daily EUR/USD and USD/EUR FX
5. ingests benchmark reference data:
   - index definitions
   - index price series
   - index return series
   - benchmark definition
   - benchmark compositions
   - benchmark return series
   - portfolio benchmark assignment
6. waits for downstream valuation and aggregation to catch up
7. verifies:
   - benchmark assignment resolution
   - portfolio analytics timeseries availability
   - gateway performance summary availability

## Why Cleanup Happens First

The benchmark reference seed is local-runbook data, not production-sourced data.

The tool deletes the prior rows for this local benchmark seed before re-ingesting them so the run remains deterministic. Without cleanup, duplicate local benchmark rows can produce:

- duplicate benchmark options
- duplicate component observations
- non-deterministic benchmark selection

## Seed Scope

Current seeded instrument universe:

- `CASH_EUR_MANUAL_PB_001`
- `CASH_USD_MANUAL_PB_001`
- `EQ_DE_SAP_MANUAL_001`
- `EQ_US_AAPL_MANUAL_001`
- `EQ_US_MSFT_MANUAL_001`
- `FD_EU_BLACKROCK_ALLOC_MANUAL_001`
- `FD_US_PIMCO_INC_MANUAL_001`
- `FI_EU_SIEMENS_2031_MANUAL_001`
- `FI_US_TSY_2030_MANUAL_001`

Current seeded benchmark:

- `BMK_GLOBAL_BALANCED_60_40`

Current seeded component indices:

- `IDX_GLOBAL_EQUITY_TR`
- `IDX_GLOBAL_BOND_TR`

## Live Validation Performed

After running the tool, the following live validations succeeded:

### 1. Benchmark assignment resolves

`POST http://127.0.0.1:8202/integration/portfolios/MANUAL_PB_USD_001/benchmark-assignment`

Observed result:

- `200`
- `benchmark_id = BMK_GLOBAL_BALANCED_60_40`
- `effective_from = 2026-01-05`

### 2. Portfolio analytics timeseries resolves

`POST http://127.0.0.1:8202/integration/portfolios/MANUAL_PB_USD_001/analytics/portfolio-timeseries`

Observed result:

- `200`
- resolved window `2026-03-03` to `2026-03-28`
- `returned_row_count = 26`
- `performance_end_date = 2026-03-28`

### 3. Gateway performance summary resolves with benchmark-linked data

`GET http://127.0.0.1:8100/api/v1/workbench/MANUAL_PB_USD_001/performance/summary?period=YTD&chart_frequency=monthly&contribution_dimension=asset_class&attribution_dimension=asset_class&detail_basis=NET`

Observed result:

- `200`
- `benchmark_code = BMK_GLOBAL_BALANCED_60_40`
- net performance block populated
- benchmark return populated
- money-weighted return populated

Observed example values at validation time:

- `portfolio_return_pct = 47475.898496`
- `benchmark_return_pct = 3.833325`
- `active_return_pct = 47472.065171`
- `money_weighted_return_pct = 6.625621`

### 4. Gateway performance details resolves with analytical content

`GET http://127.0.0.1:8100/api/v1/workbench/MANUAL_PB_USD_001/performance/details?period=YTD&chart_frequency=monthly&contribution_dimension=asset_class&attribution_dimension=asset_class&detail_basis=NET`

Observed result:

- `200`
- `benchmark_code = BMK_GLOBAL_BALANCED_60_40`
- `net_chart` populated
- `contribution` populated
- `attribution` populated

## Known Non-Blocking Warning

The gateway performance responses may still contain:

- `MANAGE_REBALANCE_UNAVAILABLE`

with a partial failure from `lotus-manage`.

That warning does not block the benchmark-linked performance data seeded by this runbook. This runbook is specifically for making the performance UI usable without depending on `lotus-manage`.

## Regression Check

If the performance endpoints regress back to empty state, check in this order:

1. benchmark assignment:
   - `POST /integration/portfolios/{portfolio_id}/benchmark-assignment`
2. stateful portfolio timeseries:
   - `POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries`
3. benchmark reference coverage:
   - benchmark definitions
   - benchmark composition rows
   - index/benchmark series coverage through the requested end date
4. local valuation/aggregation catch-up after ingestion

## Source Files

- tool: [tools/manual_performance_seed.py](/C:/Users/Sandeep/projects/lotus-core/tools/manual_performance_seed.py)
- tests: [test_manual_performance_seed.py](/C:/Users/Sandeep/projects/lotus-core/tests/unit/tools/test_manual_performance_seed.py)
