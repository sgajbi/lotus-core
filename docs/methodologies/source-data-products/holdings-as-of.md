# Holdings As Of Methodology

## Metric

`HoldingsAsOf:v1` is the core-owned operational holdings and cash-balance product exposed by:

1. `GET /portfolios/{portfolio_id}/positions`,
2. `GET /portfolios/{portfolio_id}/cash-balances`.

It returns governed position rows and cash-account balances for one portfolio with source-data
product identity, runtime metadata, as-of semantics, instrument descriptors, position-state
supportability, evidence timestamps, and cash reporting-currency restatement where requested.

The product is source evidence for recorded holdings and cash state. It is not a liquidity-ladder
methodology, income-needs plan, performance return, risk exposure methodology, tax advice,
execution-quality assessment, or OMS acknowledgement.

## Endpoint and Mode Coverage

| Mode | Request shape | Implemented behavior |
| --- | --- | --- |
| Default booked holdings | `/positions` without `as_of_date`, `include_projected=false` | Resolves the effective `as_of_date` to the latest business date when available, otherwise the current application date. Returns latest non-zero current-epoch holdings on or before that date. |
| Explicit as-of holdings | `/positions?as_of_date=<date>` | Returns latest non-zero current-epoch holdings on or before the requested date. |
| Projected-inclusive holdings | `/positions?include_projected=true` without `as_of_date` | Skips the default latest-business-date cap and returns latest non-zero current-epoch holdings, including future-dated projected state when the underlying position state has advanced. |
| Cash-balance read | `/cash-balances` without `as_of_date` | Resolves the effective `as_of_date` to the latest business date. Returns cash-account balances from snapshot rows and cash-account master data. |
| Explicit as-of cash balances | `/cash-balances?as_of_date=<date>` | Returns cash-account balances for the requested date. |
| Reporting-currency cash balances | `/cash-balances?reporting_currency=<ccy>` | Converts portfolio-currency cash balances to the requested reporting currency using the latest FX rate on or before the resolved `as_of_date`. |

## Inputs

| Input | Source | Required | Meaning |
| --- | --- | --- | --- |
| `portfolio_id` | Path parameter | Yes | Portfolio whose holdings or cash balances are queried. |
| `as_of_date` | Query parameter | No | Booked-state cap for holdings and cash balances. |
| `include_projected` | Positions query parameter | No, default `false` | Controls whether the default latest-business-date cap is skipped for positions when no explicit `as_of_date` is supplied. |
| `reporting_currency` | Cash-balances query parameter | No | Currency used to populate reporting-currency cash totals and account balances. Defaults to portfolio base currency. |

## Upstream Data Sources

| Source | Used fields | Inclusion rule |
| --- | --- | --- |
| `portfolios` | `portfolio_id`, `base_currency` | Portfolio must exist. Base currency is used for cash reporting defaults. |
| `business_dates` | `date`, `calendar_code` | Supplies default effective `as_of_date` for booked holdings and cash reads. |
| `position_state` | `portfolio_id`, `security_id`, `epoch`, `status`, `created_at`, `updated_at` | Constrains holdings to the active epoch for each portfolio-security key and supplies reprocessing supportability. |
| `position_history` | `security_id`, `position_date`, `quantity`, `cost_basis`, `cost_basis_local`, `epoch` | Authoritative booked quantity and cost-basis stream. Also supplements missing snapshot rows when snapshot materialization lags. |
| `daily_position_snapshots` | `security_id`, `date`, `quantity`, valuation fields, `market_value`, local valuation fields, `epoch`, timestamps | Supplies current or as-of snapshot-backed holdings, valuation fields, cash rows, and evidence timestamps. Snapshot rows must reconcile to latest current-epoch history quantity for positions. |
| `instruments` | name, asset class, currency, ISIN, sector, country of risk, product type, rating, liquidity tier | Adds instrument descriptors and classifies cash rows. |
| `cash_account_masters` | cash account identity, display name, currency, effective dates | Supplies stable account identity for cash-balance rows where available. |
| `fx_rates` | `from_currency`, `to_currency`, `rate_date`, `rate` | Used only for optional cash reporting-currency restatement. |
| `market_prices` | `security_id`, `price_date` | Used to classify non-cash holdings as stale when latest price coverage does not reach the response `as_of_date`. |

## Unit Conventions

Position `quantity` remains in instrument units. `cost_basis`, `market_value`, and
`unrealized_gain_loss` are portfolio-currency values. Local valuation and cost-basis fields remain
in the instrument or account local currency represented by the source row.

Position `weight` is computed as each position value divided by total returned position value. The
position value is `valuation.market_value` when available, otherwise `cost_basis`. When total
returned value is zero, every weight is `0`.

Cash balances preserve three levels:

1. native account currency balance,
2. portfolio-currency balance,
3. reporting-currency balance.

Same-currency cash restatement uses a rate of `1`. Cross-currency cash restatement uses the latest
available FX rate on or before the resolved `as_of_date`.

No performance return, risk exposure, liquidity ladder, income need, tax calculation, market-impact
adjustment, execution-quality assessment, or OMS status inference is performed by this product.

## Variable Dictionary

| Symbol | Response or source field | Definition |
| --- | --- | --- |
| `P` | `portfolio_id` | Requested portfolio. |
| `A` | `as_of_date` | Effective booked-state cap for the response. |
| `I` | `include_projected` | Flag controlling default as-of capping for positions. |
| `H` | `position_history` | Current-epoch booked position history rows. |
| `S` | `daily_position_snapshots` | Snapshot-backed position and cash rows. |
| `E` | `position_state.epoch` | Active epoch for a portfolio-security key. |
| `Q_s` | `position_state.status` | Reprocessing status for a portfolio-security key. |
| `V_i` | `positions[i].valuation.market_value` or `positions[i].cost_basis` | Value used for position weight. |
| `W_i` | `positions[i].weight` | Position weight versus total returned value. |
| `C_n` | `balance_account_currency` | Cash account native-currency balance. |
| `C_p` | `balance_portfolio_currency` | Cash account portfolio-currency balance. |
| `C_r` | `balance_reporting_currency` | Cash account reporting-currency balance. |
| `X_c` | reporting FX rate | Latest FX rate from portfolio currency to reporting currency on or before `A`. |
| `Q` | `data_quality_status` | `COMPLETE`, `PARTIAL`, `STALE`, or `UNKNOWN` source-data quality posture. |

## Methodology and Formulas

For positions, the current-epoch latest history row for each security is:

`H_latest = max(position_history where portfolio_id = P and epoch = E and position_date <= A)`

when `A` exists. Without `A`, the same expression is evaluated without the date cap.

Snapshot-backed holdings are included when a latest snapshot row exists for the same
portfolio-security key, the same epoch, and the same quantity as `H_latest`:

`S_latest.quantity = H_latest.quantity and S_latest.epoch = H_latest.epoch`

History-backed supplement rows are included only when no snapshot-backed row exists for that
security. If a history-backed row has no matching snapshot valuation, the valuation continuity
fallback sets:

`market_value = cost_basis`

`unrealized_gain_loss = 0`

Position weights are:

`W_i = V_i / sum(V_i for all returned positions)`

when the denominator is greater than zero. Otherwise:

`W_i = 0`

For cash balances:

`C_n = snapshot.market_value_local or snapshot.market_value or 0`

`C_p = snapshot.market_value or 0`

`C_r = C_p * X_c`

where `X_c = 1` when portfolio currency equals reporting currency.

## Step-by-Step Computation

1. Verify the portfolio exists.
2. Resolve the effective `A`:
   - use request `as_of_date` when supplied,
   - otherwise, for positions with `include_projected=false`, use the latest business date or the current application date when no business date exists,
   - otherwise, for positions with `include_projected=true`, leave `A` unset,
   - for cash balances, use the latest business date when no `as_of_date` is supplied.
3. For positions, fetch snapshot-backed current-epoch holdings. Snapshot rows must match latest current-epoch history quantity and have non-zero quantity.
4. Fetch current-epoch history-backed holdings for the same effective scope and add only securities missing from the snapshot-backed set.
5. For history-backed supplement rows, fetch latest available snapshot valuation fields and use them when present; otherwise use cost basis as valuation continuity fallback.
6. Attach instrument descriptors and position-state status to each position.
7. Compute position weights from returned position values.
8. Resolve `held_since_date` as the earliest position-history date in the current continuous non-zero holding period after the last zero-quantity break in the active epoch. If no epoch exists, use the row position date.
9. Fetch latest market-price dates for non-cash positions that have market prices and compare them with response `A` to derive stale posture.
10. Return positions with `HoldingsAsOf:v1` metadata, evidence timestamp, and data-quality status.
11. For cash balances, filter snapshot rows to cash instruments, join cash-account master rows and fallback account identifiers, build one row per known cash account, sort by account currency and account id, convert portfolio-currency balances to reporting currency, and return totals with `HoldingsAsOf:v1` metadata.

## Validation and Failure Behavior

| Condition | Behavior |
| --- | --- |
| Portfolio id does not exist for positions | Service raises `LookupError`; the API maps it to HTTP `404`. |
| Portfolio id does not exist for cash balances | Service raises `ValueError`; the API maps it to HTTP `404` or `400` depending on route handling. |
| No business date exists for default cash balances | Service raises `ValueError`; the route does not invent an as-of date. |
| Cash `reporting_currency` has no FX rate as of `A` | Service raises `ValueError`; the route does not return restated balances with missing FX evidence. |
| No positions are returned | Returns `data_quality_status=UNKNOWN`. |
| Any returned position lacks reprocessing status | Returns `data_quality_status=UNKNOWN`. |
| Any returned position has non-`CURRENT` reprocessing status | Returns `data_quality_status=STALE`. |
| Any non-cash priced position lacks market-price freshness through `A` | Returns `data_quality_status=STALE`. |
| Positions include history-backed supplement rows | Returns `data_quality_status=PARTIAL` unless a stronger `STALE` condition applies. |
| All positions are current, priced through `A` where required, and snapshot-backed | Returns `data_quality_status=COMPLETE`. |
| Cash balance response has no account records | Returns `data_quality_status=UNKNOWN`. |
| Cash account records exist but no cash snapshot rows back them | Returns `data_quality_status=UNKNOWN`. |
| Cash account records are backed by cash snapshot rows | Returns `data_quality_status=COMPLETE`. |

## Configuration Options

| Option | Current value |
| --- | --- |
| Holdings product identity | `HoldingsAsOf:v1` |
| Holdings default business calendar | `DEFAULT_BUSINESS_CALENDAR_CODE` through the latest business date repository path |
| Cash default reporting currency | Portfolio base currency |
| Cash account output ordering | `account_currency`, then `cash_account_id` |
| Cash classification | Instrument `asset_class == CASH` |

## Outputs

| Field | Methodology mapping |
| --- | --- |
| `product_name`, `product_version` | Governed source-data product identity. |
| `portfolio_id` | Requested portfolio. |
| `positions[]` | Snapshot-backed and history-supplemented holdings rows for the resolved scope. |
| `positions[].valuation` | Snapshot valuation when available; fallback valuation from latest snapshot or cost basis for history-backed supplement rows. |
| `positions[].weight` | Position value divided by total returned position value, or zero when total value is zero. |
| `positions[].held_since_date` | Earliest continuous non-zero holding date in the active epoch. |
| `cash_accounts[]` | Cash-account balance records for the resolved scope. |
| `totals.total_balance_portfolio_currency` | Sum of account portfolio-currency balances. |
| `totals.total_balance_reporting_currency` | Sum of account reporting-currency balances. |
| `as_of_date` | Effective booked-state cap or resolved response date. |
| `data_quality_status` | Completeness and freshness posture for returned holdings or cash balances. |
| `latest_evidence_timestamp` | Latest durable position, position-state, or cash snapshot timestamp used by the response. |

## Worked Example

Request:

`GET /portfolios/P1/positions?as_of_date=2026-03-10`

Source facts:

| Security | Snapshot quantity | Current-epoch history quantity | Snapshot market value | Position state | Latest price date |
| --- | ---: | ---: | ---: | --- | --- |
| `AAPL.OQ` | 100 | 100 | 18500.00 | `CURRENT` | 2026-03-10 |
| `BND.US` | none | 50 | 5050.00 fallback snapshot value | `CURRENT` | 2026-03-10 |

Final output mapping:

| Response field | Value |
| --- | ---: |
| `positions[0].security_id` | `AAPL.OQ` |
| `positions[0].weight` | 0.7856 |
| `positions[1].security_id` | `BND.US` |
| `positions[1].weight` | 0.2144 |
| `data_quality_status` | `PARTIAL` |

Cash request:

`GET /portfolios/P1/cash-balances?as_of_date=2026-03-10&reporting_currency=SGD`

Cash source facts:

| Account | Portfolio balance | Portfolio currency | FX rate to SGD | Reporting balance |
| --- | ---: | --- | ---: | ---: |
| `USD-CASH` | 12000.00 | USD | 1.36 | 16320.00 |

Final output mapping:

| Response field | Value |
| --- | ---: |
| `totals.cash_account_count` | 1 |
| `totals.total_balance_portfolio_currency` | 12000.00 |
| `totals.total_balance_reporting_currency` | 16320.00 |
| `data_quality_status` | `COMPLETE` |
