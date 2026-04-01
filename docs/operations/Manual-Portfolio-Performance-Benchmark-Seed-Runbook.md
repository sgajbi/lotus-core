# Manual Portfolio Performance Benchmark Seed Runbook

This runbook seeds the missing local `lotus-core` reference data required for the
manual portfolio performance workstation to return benchmark-linked data for:

- `MANUAL_PB_USD_001`
- gateway performance summary/details
- `lotus-performance` stateful portfolio analytics inputs

This runbook is intentionally app-local scoped. It does not depend on
`lotus-manage`.

This is a narrow repair runbook for benchmark-linked performance enablement. It
is not the full front-office seed target. For the broader realistic seed
contract that should support gateway and UI development across the portfolio and
performance workspaces, see:

- [Front-Office-Portfolio-Seed-Contract.md](/C:/Users/Sandeep/projects/lotus-core/docs/operations/Front-Office-Portfolio-Seed-Contract.md)

## Safety Scope

This runbook is for local development and local validation only.

It is not approved for shared environments, QA environments, or production-like
data stores because the seed tool performs direct cleanup of previously seeded
benchmark rows before re-ingesting them.

Do not run this tool against any database you are not prepared to modify
destructively for the seeded benchmark ids.

## Purpose

The manual portfolio bootstrap creates:

- portfolio
- instruments
- transactions
- current market-value state

but it does not create the historical reference inputs required by
`lotus-performance`:

- business-date coverage for the manual performance window
- daily market prices for the seeded manual securities
- daily EUR/USD FX coverage across the same window
- benchmark assignment, definitions, compositions, and return/reference series

Without those inputs, the live gateway performance endpoints return empty or
partial payloads with errors such as:

- `Missing FX rate for EUR/USD on 2026-03-03`
- `No effective benchmark assignment found for portfolio and as_of_date`
- `Benchmark composition window does not cover requested date 2026-01-05`
- `Benchmark market-series coverage is incomplete`

## Preconditions

The following services must already be running:

- `lotus-core` ingestion service
- `lotus-core` query service
- `lotus-core` query control plane
- `lotus-performance`
- `lotus-gateway`

Expected local endpoints:

- ingestion: `http://core-ingestion.dev.lotus`
- query control plane: `http://core-query.dev.lotus`
- gateway: `http://gateway.dev.lotus`

The following portfolio must already exist from the manual portfolio bootstrap:

- `MANUAL_PB_USD_001`

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

1. deletes any existing local benchmark seed rows for the target benchmark and
   its component indices
2. ingests business dates for the manual valuation window
3. ingests daily market prices for the seeded manual instruments
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

The tool deletes the prior rows for this local benchmark seed before
re-ingesting them so the run remains deterministic. Without cleanup, duplicate
local benchmark rows can produce:

- duplicate benchmark options
- duplicate component observations
- non-deterministic benchmark selection

Use `--skip-cleanup` only if you are debugging ingestion behavior and explicitly
want to preserve the currently seeded benchmark rows. Do not use
`--skip-cleanup` for the normal rerun path.

## Seed Contract

This runbook asserts the following seeded scope.

### Portfolio

- `MANUAL_PB_USD_001`

### Instrument universe

- `CASH_EUR_MANUAL_PB_001`
- `CASH_USD_MANUAL_PB_001`
- `EQ_DE_SAP_MANUAL_001`
- `EQ_US_AAPL_MANUAL_001`
- `EQ_US_MSFT_MANUAL_001`
- `FD_EU_BLACKROCK_ALLOC_MANUAL_001`
- `FD_US_PIMCO_INC_MANUAL_001`
- `FI_EU_SIEMENS_2031_MANUAL_001`
- `FI_US_TSY_2030_MANUAL_001`

### Benchmark scope

- benchmark: `BMK_GLOBAL_BALANCED_60_40`
- component indices:
  - `IDX_GLOBAL_EQUITY_TR`
  - `IDX_GLOBAL_BOND_TR`
- benchmark effective start date:
  - `2026-01-05`

### Time window

- valuation window:
  - `2026-03-03` to `2026-03-28`
- benchmark coverage must extend through the requested as-of date

### Downstream APIs that must become usable

- `POST /integration/portfolios/{portfolio_id}/benchmark-assignment`
- `POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries`
- `GET /api/v1/workbench/{portfolio_id}/performance/summary`
- `GET /api/v1/workbench/{portfolio_id}/performance/details`

## Happy Path Validation

Run these checks after the seed completes.

### 1. Benchmark assignment resolves

`POST http://core-query.dev.lotus/integration/portfolios/MANUAL_PB_USD_001/benchmark-assignment`

Pass criteria:

- HTTP `200`
- `benchmark_id = BMK_GLOBAL_BALANCED_60_40`
- `effective_from = 2026-01-05`

Fail criteria:

- any `4xx` or `5xx`
- null or empty benchmark assignment
- assignment start date later than the requested as-of date

### 2. Portfolio analytics timeseries resolves

`POST http://core-query.dev.lotus/integration/portfolios/MANUAL_PB_USD_001/analytics/portfolio-timeseries`

Pass criteria:

- HTTP `200`
- resolved window `2026-03-03` to `2026-03-28`
- non-zero `returned_row_count`
- `performance_end_date = 2026-03-28`

Fail criteria:

- empty timeseries payload
- timeseries stops before the requested end date
- FX-related failure

### 3. Gateway performance summary resolves with benchmark-linked data

`GET http://gateway.dev.lotus/api/v1/workbench/MANUAL_PB_USD_001/performance/summary?period=YTD&chart_frequency=monthly&contribution_dimension=asset_class&attribution_dimension=asset_class&detail_basis=NET`

Pass criteria:

- HTTP `200`
- `benchmark_code = BMK_GLOBAL_BALANCED_60_40`
- net performance block populated
- benchmark return populated
- money-weighted return populated

Important interpretation rule:

This runbook does not assert specific portfolio return magnitudes as the
success criterion. A numerically implausible performance value is a warning that
the performance calculation path may still need review, but it does not mean the
benchmark seed itself failed.

Treat values like `47475.898496%` as suspicious and escalate them separately as
a calculation-quality issue, not as proof that the seed run failed.

### 4. Gateway performance details resolves with analytical content

`GET http://gateway.dev.lotus/api/v1/workbench/MANUAL_PB_USD_001/performance/details?period=YTD&chart_frequency=monthly&contribution_dimension=asset_class&attribution_dimension=asset_class&detail_basis=NET`

Pass criteria:

- HTTP `200`
- `benchmark_code = BMK_GLOBAL_BALANCED_60_40`
- `net_chart` populated
- `contribution` populated
- `attribution` populated

Fail criteria:

- benchmark code missing
- chart block empty
- contribution or attribution blocks empty

## Known Non-Blocking Warning

The gateway performance responses may still contain:

- `MANAGE_REBALANCE_UNAVAILABLE`

with a partial failure from `lotus-manage`.

That warning does not block the benchmark-linked performance data seeded by this
runbook. This runbook is specifically for making the performance UI usable
without depending on `lotus-manage`.

## Troubleshooting Matrix

| Symptom | Likely cause | Corrective action |
| --- | --- | --- |
| `Missing FX rate for EUR/USD ...` | FX series not ingested or window too short | rerun the seed without `--skip-cleanup`; verify `/ingest/fx-rates` completed and the start/end dates cover the requested window |
| `No effective benchmark assignment found ...` | benchmark assignment missing or effective date too late | verify benchmark assignment response; rerun with the correct `--benchmark-start-date` |
| `Benchmark composition window does not cover requested date ...` | benchmark composition/reference series do not extend far enough back or forward | rerun with the correct benchmark start date and ensure the requested end date is still inside seeded coverage |
| `Benchmark market-series coverage is incomplete` | index price/return series were not fully ingested | rerun the seed and confirm the benchmark/index ingestion steps completed |
| performance summary/details return `200` but benchmark fields are empty | gateway is reachable but seed contract is incomplete | check benchmark assignment first, then timeseries, then benchmark series coverage |
| performance summary returns implausible return magnitudes | benchmark seed succeeded but the calculation path may still be wrong | treat as a separate performance-methodology defect; do not rewrite the seed runbook to normalize implausible outputs |

## Regression Check Order

If the performance endpoints regress back to empty or partial state, check in
this order:

1. benchmark assignment:
   - `POST /integration/portfolios/{portfolio_id}/benchmark-assignment`
2. stateful portfolio timeseries:
   - `POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries`
3. benchmark reference coverage:
   - benchmark definitions
   - benchmark composition rows
   - index/benchmark series coverage through the requested end date
4. local valuation and aggregation catch-up after ingestion
5. gateway performance summary/details payload shape

## Source Files

- tool: [tools/manual_performance_seed.py](/C:/Users/Sandeep/projects/lotus-core/tools/manual_performance_seed.py)
- tests: [test_manual_performance_seed.py](/C:/Users/Sandeep/projects/lotus-core/tests/unit/tools/test_manual_performance_seed.py)
