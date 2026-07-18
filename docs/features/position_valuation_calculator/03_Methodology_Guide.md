# Methodology Guide: Position Valuation & Scheduling

This guide details the methodologies used by the `position-valuation-calculator` for both its calculation and orchestration responsibilities.

## 1. Valuation Logic

The core calculation is performed by the stateless `ValuationLogic` class. It determines a position's market value and unrealized profit & loss (P&L) in both the instrument's local currency and the portfolio's base currency.

### Calculation Steps

1.  **Align Price Currency:** If the provided market price's currency is different from the instrument's currency, an FX rate is used to convert the price into the instrument's currency.
2.  **Calculate Local Values:**
    * `Market Value (Local) = Quantity * Price (in instrument's currency)`
    * `Unrealized P&L (Local) = Market Value (Local) - Cost Basis (Local)`
3.  **Convert to Base Currency:**
    * If the instrument's currency is different from the portfolio's base currency, the `instrument_to_portfolio_fx_rate` is applied to the local currency values.
    * `Market Value (Base) = Market Value (Local) * FX Rate`
4.  **Calculate Base P&L:**
    * `Unrealized P&L (Base) = Market Value (Base) - Cost Basis (Base)`

### Current Behavior for Missing Data

* If a required FX rate for a valuation is not found in the database, the valuation cannot be completed. The resulting `daily_position_snapshot` is marked with a status of `FAILED`, and the corresponding valuation job is marked `COMPLETE`. The system **does not** automatically retry this job; a manual reprocessing trigger is required if the missing data is later ingested.

### Governed policy migration status

Issue #788 is replacing the quantity-price and legacy bond-quote heuristic with explicit valuation
representations. The framework-independent policy, assignment, day-count, and segmented-accrual
domains are implemented locally, but the production worker and financial reconciliation path are
not wired to them yet. Until that wiring, persistence, API, and wiki support claims remain limited
to the current runtime described above.

The target policy never selects behavior from a broad product name or price magnitude. An exact,
effective-dated instrument assignment selects a versioned composition of:

- source representation: unit price, NAV, clean/dirty percent of principal, supplied per-unit,
  supplied per-contract, supplied whole-position value, or settlement variation;
- principal basis: position units, face amount, factor-adjusted current principal, or supplied
  current principal;
- scaling: quantity, principal, contract count and multiplier, or no scaling;
- accrued-income treatment: not applicable, included, calculated separately, or supplied separately;
- direct source-to-reporting FX policy and a separately named output measure.

Missing or conflicting assignments and ambiguous or incomplete inputs fail closed. Futures notional
and settlement variation cannot populate market value. Core consumes supplied derivative fair value
and supplied floating all-in rates; it does not price derivatives, forecast rates, construct curves,
or calculate fund NAV.

#### Segmented accrued-income formula

For contiguous segments over which principal, supplied annual rate, and day-count facts are
constant:

```text
gross_accrued_income = sum(
    signed_accrual_principal_segment
    * supplied_annual_effective_rate_segment
    * governed_year_fraction_segment
)
```

| Variable | Meaning | Required behavior |
|---|---|---|
| `signed_accrual_principal_segment` | Principal applicable to the segment, including long/short sign | Preserve original face separately; segment on paydown/amortization |
| `supplied_annual_effective_rate_segment` | Fixed contractual rate or upstream-supplied floating all-in rate in decimal form | Do not divide by frequency or derive index, spread, cap/floor, fallback, or rounding |
| `governed_year_fraction_segment` | Exact convention/version result for start-inclusive, end-exclusive dates | Reject unknown convention/version and incomplete calendars/reference periods |
| `gross_accrued_income` | Contractual accrual before separate tax, impairment, PIK, inflation, compounding, or boundary rounding policy | Keep separate from clean value and add exactly once only when policy requires |

The version-1 registry implements `ACT/365.FIXED`, `ACT/360`, `BUS/252`, `30/360.US`,
`30E/360`, `30E/360.ISDA`, `ACT/ACT.ISDA`, and `ACT/ACT.ICMA`. `BUS/252` requires a
versioned source calendar. `30E/360.ISDA` requires the contractual termination date.
`ACT/ACT.ICMA` requires authoritative regular or quasi-coupon reference periods that cover the
calculation interval exactly once; this is how regular, short-stub, and long-stub periods avoid an
inferred schedule.

Day-count and accrued-income intermediates use an internal precision of 50 decimal digits,
independent of ambient process Decimal precision. No implicit currency rounding occurs in the
domain kernel; the persisted/API boundary must apply a separately governed currency/product
rounding policy and retain the unrounded evidence required for reconciliation.

#### Calculation lineage contract

Every governed calculation result must bind three different evidence layers:

1. `input_content_hash` covers normalized financial inputs and source lineage. Decimal scale,
   effective dates, aware observation timestamps, enum values, ordered sequences, and unordered sets
   have canonical representations; binary floating-point values are prohibited.
2. `calculation_content_hash` binds the input hash to the algorithm identifier, algorithm version,
   and intermediate precision. A methodology version change therefore changes calculation lineage
   even when the source facts are unchanged.
3. `output_content_hash` binds the named output values to the calculation hash. It cannot be reused
   for another algorithm or input set that happens to produce the same monetary total.

The domain contract uses lowercase SHA-256 digests and rejects non-finite Decimal values, naive
timestamps, non-string mapping keys, unsupported values, and invalid algorithm metadata. Runtime
persistence, events, API/OpenAPI, diagnostics, and financial reconciliation must carry these hashes
with policy/assignment and source references; a request correlation ID is not calculation lineage.

#### Performance contract

The pure policies are I/O-free and bounded by the number of supplied segments/reference periods.
Production integration must bulk-resolve assignment, schedule, calendar, rate, principal/factor,
multiplier, price, and FX evidence; per-position N+1 reads are not acceptable. Kernel checks can
detect local regressions, but capacity claims require exact-SHA mixed-book runtime evidence with
throughput, p95/p99, database operations, lock/connection pressure, Kafka lag, cache invalidation,
resource use, queue closure, and exact reconciliation.

## 2. Valuation Scheduler Logic

The `ValuationScheduler` is a powerful background process that orchestrates all valuation and backfill activities. It runs in a continuous loop, performing a series of state management and job creation tasks.

### Scheduler's Main Loop

1.  **Process Instrument Triggers:** The scheduler first checks the `instrument_reprocessing_state` table. If it finds triggers from back-dated price events, it fans out by finding all affected portfolios and resetting their watermarks in the `position_state` table.
    * **Readiness-race closure:** If an in-horizon market price arrives before the affected portfolio-security key is visible as an open position, the price consumer still stages a durable instrument reprocessing trigger instead of dropping the event. This guarantees the scheduler revisits the security after transaction processing and prevents quiet-day carry-forward gaps in downstream position-timeseries and portfolio-timeseries outputs.
2.  **Reset Stale Jobs:** It runs a recovery query to find any jobs that have been in a `PROCESSING` state for too long (default > 15 minutes). These jobs are reset to `PENDING`, allowing them to be picked up again by a consumer. This makes the system resilient to worker crashes.
3.  **Create Backfill Jobs:** The scheduler queries the `position_state` table for all keys where the `watermark_date` is older than the latest system `business_date`. For each of these "lagging" keys, it creates the necessary `valuation.job.requested` jobs to fill the gap.
    * **Position-Aware Scheduling:** This process is intelligent; it will not create a job for a date that is before the position's first known transaction date, preventing unnecessary work.
4.  **Advance Watermarks:** After creating new jobs, the scheduler checks which lagging keys now have a complete, contiguous history of `daily_position_snapshots`. For these keys, it advances their `watermark_date` in the `position_state` table to the last contiguous date. If the new watermark matches the latest business date, the key's `status` is set back to `CURRENT`.
5.  **Dispatch Jobs:** Finally, the scheduler queries for all `PENDING` jobs in the `portfolio_valuation_jobs` table, atomically claims a batch of them by setting their status to `PROCESSING`, and publishes them as events to the `valuation.job.requested` Kafka topic.
