# Portfolio Liquidity Ladder

## Metric

`PortfolioLiquidityLadder:v1` is the lotus-core source-data product for portfolio cash-availability
ladder evidence. It combines source holdings, source cash positions, instrument liquidity tiers, and
booked/projected cashflow rows into deterministic liquidity buckets.

This product is evidence for downstream monitoring, reporting, and DPM supportability. It is not a
client advice recommendation, funding recommendation, income plan, OMS execution forecast,
best-execution assessment, tax methodology, or market-impact model.

## Endpoint and Mode Coverage

| Mode | Endpoint | Status |
| --- | --- | --- |
| Portfolio liquidity ladder | `GET /portfolios/{portfolio_id}/liquidity-ladder` | Implemented |

The endpoint supports an optional `as_of_date`, `horizon_days`, and `include_projected` flag.
`horizon_days` is bounded from 0 to 366 calendar days.

## Inputs

| Input | Meaning |
| --- | --- |
| `portfolio_id` | Source portfolio identifier. |
| `as_of_date` | Optional business date. Defaults to latest lotus-core business date. |
| `horizon_days` | Calendar-day ladder horizon from `as_of_date`. |
| `include_projected` | Includes settlement-dated future external deposits and withdrawals when true. |

## Upstream Data Sources

| Source | Fields Used |
| --- | --- |
| `portfolio` | Portfolio identity and base currency. |
| `position_history` | Current-epoch open position quantity used by snapshot row selection. |
| `daily_position_snapshot` | Current cash and non-cash market value. |
| `instrument` | Asset class and source-owned `liquidity_tier`. |
| `cashflow` | Latest booked net cashflow by date. |
| `transaction` | Projected settlement-dated external `DEPOSIT` and `WITHDRAWAL` movements. |

## Unit Conventions

All returned monetary values are in portfolio base currency. The product does not perform reporting
currency conversion and does not infer liquidation proceeds or market impact.

## Variable Dictionary

| Symbol | Definition |
| --- | --- |
| `A` | Resolved as-of date. |
| `H` | Requested horizon days. |
| `C0` | Opening source cash balance at `A`. |
| `B_k` | Booked net cashflow in bucket `k`. |
| `P_k` | Projected settlement cashflow in bucket `k`. |
| `N_k` | Net bucket cashflow, `B_k + P_k`. |
| `CA_k` | Cumulative cash available through bucket `k`. |
| `S_k` | Cash shortfall through bucket `k`, `abs(min(CA_k, 0))`. |
| `MV_t` | Non-cash market value for liquidity tier `t`. |

## Methodology and Formulas

The ladder uses fixed deterministic buckets:

1. `T0`: `A`.
2. `T_PLUS_1`: `A + 1`.
3. `T_PLUS_2_TO_7`: `A + 2` through `A + 7`.
4. `T_PLUS_8_TO_30`: `A + 8` through `A + 30`.
5. `T_PLUS_31_TO_HORIZON`: `A + 31` through `A + H`.

Buckets beyond the requested horizon are omitted.

For each bucket:

```text
N_k = B_k + P_k
CA_k = C0 + sum(N_i for i <= k)
S_k = abs(min(CA_k, 0))
```

Asset liquidity-tier exposure is grouped from non-cash holdings:

```text
MV_t = sum(snapshot.market_value for non-cash positions where instrument.liquidity_tier = t)
```

Missing tier values are grouped under `UNCLASSIFIED`.

## Step-by-Step Computation

1. Resolve the portfolio; fail with 404-equivalent service error when missing.
2. Resolve `A` from the request or latest business date.
3. Select current snapshot-backed holdings using the same current-epoch reconciliation path as
   `HoldingsAsOf`.
4. Split cash and non-cash rows by `instrument.asset_class == CASH`.
5. Compute `C0` from cash row market values.
6. Group non-cash market value by instrument liquidity tier.
7. Load booked cashflow rows between `A` and `A + H`.
8. Load projected settlement-dated external cashflows for the same range when requested.
9. Build deterministic buckets and cumulative cash availability.
10. Return source-data runtime metadata, evidence timestamp, and deterministic source fingerprint.

## Validation and Failure Behavior

| Condition | Behavior |
| --- | --- |
| Missing portfolio | Raises `Portfolio with id <id> not found`; router maps to HTTP 404. |
| Missing business date | Raises `No business date is available for liquidity ladder queries.`; router maps to HTTP 400. |
| Invalid horizon | Raises `horizon_days must be between 0 and 366.`; router and FastAPI validation reject the request. |
| No source holding rows | Returns `data_quality_status=UNKNOWN`. |
| Source rows and buckets present | Returns `data_quality_status=COMPLETE`. |

## Configuration Options

| Option | Default | Meaning |
| --- | --- | --- |
| `horizon_days` | `30` | Calendar days from `A`. |
| `include_projected` | `true` | Include settlement-dated projected external deposits and withdrawals. |

## Outputs

| Field | Meaning |
| --- | --- |
| `totals.opening_cash_balance_portfolio_currency` | `C0`. |
| `buckets[].booked_net_cashflow_portfolio_currency` | `B_k`. |
| `buckets[].projected_settlement_cashflow_portfolio_currency` | `P_k`. |
| `buckets[].cumulative_cash_available_portfolio_currency` | `CA_k`. |
| `buckets[].cash_shortfall_portfolio_currency` | `S_k`. |
| `asset_liquidity_tiers[]` | Non-cash exposure by source-owned liquidity tier. |

## Worked Example

| Item | Value |
| --- | --- |
| `C0` | 100000 |
| `T0 booked cashflow` | -25000 |
| `T+1 projected cashflow` | -90000 |
| `T+2 to T+7 booked cashflow` | 5000 |
| `T+8 to T+30 projected cashflow` | -25000 |
| `projected_cash_available_end_portfolio_currency` | -35000 |
| `maximum_cash_shortfall_portfolio_currency` | 35000 |
| `asset_liquidity_tiers[T1].market_value_portfolio_currency` | 400000 |
| `asset_liquidity_tiers[T2].market_value_portfolio_currency` | 250000 |
