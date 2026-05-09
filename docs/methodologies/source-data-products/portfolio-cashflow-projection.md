# Portfolio Cashflow Projection Methodology

## Metric

`PortfolioCashflowProjection:v1` is the core-owned operational cashflow projection product exposed
by `GET /portfolios/{portfolio_id}/cashflow-projection`.

It returns daily net portfolio cashflow points, a running cumulative cashflow, and the total net
cashflow over the returned window in the portfolio base currency. The product is source evidence for
operational cash movement, not a liquidity ladder, funding recommendation, income plan, performance
return, market-impact estimate, or OMS execution forecast.

## Endpoint and Mode Coverage

| Mode | Request shape | Implemented behavior |
| --- | --- | --- |
| Projected | `include_projected=true` | Returns booked portfolio cashflow rows from `as_of_date` through `as_of_date + horizon_days` and adds settlement-dated future external cash movements from `DEPOSIT` and `WITHDRAWAL` transactions booked before the projection start date. |
| Booked only | `include_projected=false` | Returns booked portfolio cashflow rows only for `as_of_date`. The response is capped to one point and carries the note `Booked-only view capped at as_of_date.` |

If `as_of_date` is omitted, the service uses the latest configured business date for the default
business calendar. If no business date is available, it falls back to the current application date.

## Inputs

| Input | Source | Required | Meaning |
| --- | --- | --- | --- |
| `portfolio_id` | Path parameter | Yes | Portfolio whose base currency and cashflow evidence are returned. |
| `horizon_days` | Query parameter | No, default `10` | Calendar-day projection horizon from `as_of_date`; constrained by the API to `1..3650`. |
| `as_of_date` | Query parameter | No | Business-date anchor for the projection baseline. |
| `include_projected` | Query parameter | No, default `true` | Whether to include settlement-dated future external cash movements in addition to booked cashflow rows. |

## Upstream Data Sources

| Source | Used fields | Inclusion rule |
| --- | --- | --- |
| `portfolios` | `portfolio_id`, `base_currency` | Portfolio must exist and provide the currency used for all monetary output fields. |
| latest `cashflows` per transaction | `portfolio_id`, `cashflow_date`, `amount`, `is_portfolio_flow`, `epoch`, `updated_at` | Latest cashflow row per transaction is selected by highest `epoch`, then highest row id; rows must match the portfolio, be marked `is_portfolio_flow`, and fall inside the query window. |
| `transactions` | `portfolio_id`, `transaction_type`, `transaction_date`, `settlement_date`, `gross_transaction_amount`, `updated_at` | Projected mode includes only `DEPOSIT` and `WITHDRAWAL` transactions with non-null settlement dates in the query window and transaction dates before the projection start date. |
| `business_dates` | `date`, `calendar_code` | Supplies the default `as_of_date` when the caller omits it. |

## Unit Conventions

All monetary outputs use the portfolio base currency returned as `portfolio_currency`.

Inflows to the portfolio are positive. Outflows from the portfolio are negative. Projected
`DEPOSIT` amounts are `abs(gross_transaction_amount)`. Projected `WITHDRAWAL` amounts are
`-abs(gross_transaction_amount)`.

No FX conversion, tax methodology, liquidity bucketing, or performance return calculation is
performed by this product.

## Variable Dictionary

| Symbol | Response or source field | Definition |
| --- | --- | --- |
| `P` | `portfolio_id` | Requested portfolio. |
| `A` | `as_of_date` | Effective projection start date. |
| `H` | `horizon_days` | Requested horizon in calendar days. |
| `I` | `include_projected` | Projected-mode flag. |
| `E` | `range_end_date` | `A + H` when `I=true`; `A` when `I=false`. |
| `B_d` | booked cashflows | Sum of latest booked portfolio cashflow amounts on date `d`. |
| `S_d` | projected settlement movements | Sum of projected `DEPOSIT`/`WITHDRAWAL` settlement movements on date `d`; zero when `I=false`. |
| `N_d` | `points[].net_cashflow` | Daily net cashflow for date `d`: `B_d + S_d`. |
| `C_d` | `points[].projected_cumulative_cashflow` | Running cumulative cashflow through date `d`. |
| `T` | `total_net_cashflow` | Final cumulative cashflow for the returned range. |

## Methodology and Formulas

For every calendar date `d` in the returned range `[A, E]`:

`N_d = B_d + S_d`

`C_d = sum(N_i for each returned date i where A <= i <= d)`

`T = C_E`

Booked cashflows and projected settlement movements on the same date are additive. Dates with no
booked or projected movement return `net_cashflow = 0` and carry the prior cumulative value forward.

## Step-by-Step Computation

1. Resolve the portfolio base currency from `portfolios`.
2. Resolve `A` from the request `as_of_date`, or from the latest business date, or from the current
   application date if no business date exists.
3. Compute `E = A + H` for projected mode, otherwise `E = A`.
4. Query latest booked portfolio cashflow rows where `cashflow_date` falls between `A` and `E` and
   `is_portfolio_flow` is true.
5. In projected mode only, query settlement-dated future external cash movements where:
   `transaction_type in ("DEPOSIT", "WITHDRAWAL")`, `settlement_date` falls between `A` and `E`,
   and `transaction_date < A`.
6. Add booked and projected amounts by date.
7. Walk every calendar date from `A` through `E` in ascending order, emitting one
   `CashflowProjectionPoint` per date.
8. Maintain the running cumulative amount and assign it to
   `points[].projected_cumulative_cashflow`.
9. Return `total_net_cashflow` as the final running cumulative value.
10. Return source-data runtime metadata with `product_name`, `product_version`,
    `data_quality_status`, `latest_evidence_timestamp`, and `source_batch_fingerprint`.

## Validation and Failure Behavior

| Condition | Behavior |
| --- | --- |
| Portfolio id does not exist or has no base currency | Service raises `ValueError`; the API maps it to HTTP `404`. |
| `horizon_days` outside `1..3650` | FastAPI validation rejects the request before service execution. |
| No booked or projected cashflows in range | The service returns daily points with zero net cashflow and zero cumulative cashflow. |
| No source evidence timestamp exists | `latest_evidence_timestamp` is returned as `null`; the product still returns deterministic points. |
| Multiple cashflow epochs exist for a transaction | Only the latest cashflow row per transaction contributes to `B_d`. |
| Same-day booked and projected movements exist | Amounts are added into a single `net_cashflow` point for that date. |

`data_quality_status` is currently `COMPLETE` when the service can resolve the portfolio and build
the projection. This status indicates a service-owned projection response, not a broader liquidity,
tax, execution, or performance certification.

## Configuration Options

| Option | Current value |
| --- | --- |
| Default horizon | `10` calendar days |
| Maximum horizon | `3650` calendar days |
| Default projected mode | `include_projected=true` |
| Default business calendar | `DEFAULT_BUSINESS_CALENDAR_CODE` |
| Product identity | `PortfolioCashflowProjection:v1` |

## Outputs

| Field | Methodology mapping |
| --- | --- |
| `portfolio_currency` | Portfolio base currency used for all monetary outputs. |
| `points[].projection_date` | Each calendar date from `range_start_date` through `range_end_date`. |
| `points[].net_cashflow` | `N_d`. |
| `points[].projected_cumulative_cashflow` | `C_d`. |
| `total_net_cashflow` | `T`. |
| `notes` | Projected mode or booked-only mode explanation. |
| `source_batch_fingerprint` | Deterministic fingerprint containing portfolio, start date, end date, and projected-mode flag. |

## Worked Example

Request:

`GET /portfolios/P1/cashflow-projection?as_of_date=2026-03-01&horizon_days=4&include_projected=true`

Source facts:

| Date | Booked latest portfolio cashflow `B_d` | Projected settlement movement `S_d` | Daily net `N_d` | Cumulative `C_d` |
| --- | ---: | ---: | ---: | ---: |
| 2026-03-01 | -1000 | 0 | -1000 | -1000 |
| 2026-03-02 | 0 | 0 | 0 | -1000 |
| 2026-03-03 | 250 | 0 | 250 | -750 |
| 2026-03-04 | 0 | -18000 | -18000 | -18750 |
| 2026-03-05 | 0 | 0 | 0 | -18750 |

Final output mapping:

| Response field | Value |
| --- | ---: |
| `points[2026-03-04].net_cashflow` | -18000 |
| `points[2026-03-04].projected_cumulative_cashflow` | -18750 |
| `total_net_cashflow` | -18750 |
