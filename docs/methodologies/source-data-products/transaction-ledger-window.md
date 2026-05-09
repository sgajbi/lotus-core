# Transaction Ledger Window Methodology

## Metric

`TransactionLedgerWindow:v1` is the core-owned operational transaction-ledger product exposed by
`GET /portfolios/{portfolio_id}/transactions`.

It returns governed booked transaction rows for one portfolio with source-data product identity,
runtime metadata, optional filters, offset pagination, linked cost/cashflow evidence, and
optional reporting-currency restatement fields. The product is source evidence for row-level
portfolio activity. It is not a tax methodology, FX attribution methodology, cash-movement
aggregation methodology, transaction-cost curve methodology, execution-quality assessment, OMS
acknowledgement, or client advice output.

## Endpoint and Mode Coverage

| Mode | Request shape | Implemented behavior |
| --- | --- | --- |
| Default booked ledger | No `as_of_date`, `include_projected=false` | Resolves `as_of_date` to the latest business date when available, otherwise the current application date. Returns rows with `transaction_date <= as_of_date`. |
| Explicit as-of ledger | `as_of_date=<date>` | Returns rows with `transaction_date <= as_of_date`. |
| Projected-inclusive ledger | `include_projected=true` | Does not apply the default business-date cap when `as_of_date` is omitted, allowing future-dated projected rows that match the other filters. |
| Reporting-currency restated ledger | `reporting_currency=<ccy>` with an effective `as_of_date` | Adds reporting-currency monetary fields by applying the latest available FX rate on or before the effective `as_of_date`. Raw ledger monetary fields remain unchanged. |

## Inputs

| Input | Source | Required | Meaning |
| --- | --- | --- | --- |
| `portfolio_id` | Path parameter | Yes | Portfolio whose transaction ledger is queried. |
| `instrument_id` | Query parameter | No | Restricts rows to one instrument. |
| `security_id` | Query parameter | No | Restricts rows to one security for holdings drill-down. |
| `transaction_type` | Query parameter | No | Restricts rows to one canonical transaction type. |
| `component_type` | Query parameter | No | Restricts rows to one FX component type. |
| `linked_transaction_group_id` | Query parameter | No | Restricts rows to one linked economic-event group. |
| `fx_contract_id` | Query parameter | No | Restricts rows to one FX contract. |
| `swap_event_id` | Query parameter | No | Restricts rows to one FX swap event. |
| `near_leg_group_id` | Query parameter | No | Restricts rows to one FX swap near-leg group. |
| `far_leg_group_id` | Query parameter | No | Restricts rows to one FX swap far-leg group. |
| `start_date` | Query parameter | No | Inclusive lower bound on `transaction_date`. |
| `end_date` | Query parameter | No | Inclusive upper bound on `transaction_date`. |
| `as_of_date` | Query parameter | No | Booked-state cap on `transaction_date`. |
| `include_projected` | Query parameter | No, default `false` | Controls whether the default latest-business-date cap is skipped when no explicit `as_of_date` is supplied. |
| `reporting_currency` | Query parameter | No | Currency used to populate restated reporting-currency monetary fields. |
| `skip`, `limit` | Pagination parameters | No | Offset pagination controls. |
| `sort_by`, `sort_order` | Sorting parameters | No | Sorts by an allowed transaction field; defaults to `transaction_date` descending. |

## Upstream Data Sources

| Source | Used fields | Inclusion rule |
| --- | --- | --- |
| `portfolios` | `portfolio_id` | Portfolio must exist. |
| `business_dates` | `date`, `calendar_code` | Supplies the default `as_of_date` when the caller omits it and `include_projected=false`. |
| `transactions` | transaction identity, dates, type, instrument/security ids, quantities, prices, monetary fields, FX fields, linked-event fields, source fields, and `updated_at` | Rows must match the requested portfolio and filters. Date filters use `transaction_date`. |
| `transaction_costs` | `fee_type`, `amount`, `currency` | Joined as row-level cost evidence and returned without aggregation. |
| `cashflows` | cashflow row fields linked to the transaction | Joined as row-level linked cashflow evidence when present. |
| `fx_rates` | `from_currency`, `to_currency`, `rate_date`, `rate` | Used only for optional reporting-currency restatement fields. |

## Unit Conventions

Raw monetary fields remain in the transaction row currency conventions already stored on the
ledger row. The response does not convert or overwrite raw ledger values.

When `reporting_currency` is supplied and an effective `as_of_date` exists, the service applies the
latest FX rate with `rate_date <= as_of_date` from each row currency to the requested reporting
currency and populates only the `*_reporting_currency` fields. Same-currency restatement uses a
rate of `1`.

No tax calculation, FX attribution, cash movement aggregation, transaction-cost curve aggregation,
market-impact adjustment, execution-quality assessment, or OMS status inference is performed by
this product.

## Variable Dictionary

| Symbol | Response or source field | Definition |
| --- | --- | --- |
| `P` | `portfolio_id` | Requested portfolio. |
| `S` | `start_date` | Optional inclusive start date. |
| `E` | `end_date` | Optional inclusive end date. |
| `A` | `as_of_date` | Effective booked-state cap. |
| `I` | `include_projected` | Flag controlling default as-of capping when no explicit `A` is supplied. |
| `F` | filter set | Instrument, security, transaction type, FX, linked-group, and leg filters. |
| `N` | `total` | Count of all rows matching `P`, `F`, and date/as-of filters. |
| `K` | `skip` | Offset into the matching row set. |
| `L` | `limit` | Maximum returned rows. |
| `R` | `transactions[]` | Returned page of transaction rows. |
| `Q` | `data_quality_status` | `COMPLETE`, `PARTIAL`, or `UNKNOWN` page quality posture. |
| `X_c` | reporting FX rate | Latest FX rate from row currency to reporting currency on or before `A`. |

## Methodology and Formulas

The matching row set is:

`M = rows where portfolio_id = P and all requested filters F match`

Date filters are applied as:

`transaction_date >= start_of_day(S)` when `S` is supplied

`transaction_date < start_of_next_day(E)` when `E` is supplied

`transaction_date < start_of_next_day(A)` when an effective `A` is supplied

Reporting-currency fields are computed independently for each populated raw monetary field:

`amount_reporting_currency = amount * X_c`

The raw amount remains unchanged. The product does not derive cross-row measures from the returned
page.

## Step-by-Step Computation

1. Verify the portfolio exists.
2. Resolve the effective `A`: use request `as_of_date` when supplied; otherwise, if
   `include_projected=false`, use the latest business date for the default business calendar or
   the current application date when no business date exists; otherwise leave `A` unset.
3. Build the transaction ledger filter set from portfolio, instrument/security, transaction type,
   FX component, linked group, FX contract, swap event, near-leg, far-leg, start date, end date,
   and effective as-of date.
4. Count all matching rows for `total`.
5. Query the requested page with eager row-level `cashflow` and `transaction_costs` evidence.
6. Sort by the requested allowed field and direction; when no allowed field is supplied, sort by
   `transaction_date` descending.
7. Convert each row into `TransactionRecord`, preserving row-level cost records and linked cashflow
   records when present.
8. If `reporting_currency` is supplied and `A` exists, populate supported
   `*_reporting_currency` fields using the latest FX rate on or before `A`.
9. Compute `data_quality_status` from `total`, returned row count, and `skip`.
10. Return source-data runtime metadata including product identity, version, effective as-of date,
    latest evidence timestamp, reconciliation status, restatement version, and data-quality status.

## Validation and Failure Behavior

| Condition | Behavior |
| --- | --- |
| Portfolio id does not exist | Service raises `LookupError`; the API maps it to HTTP `404`. |
| `reporting_currency` is supplied but no FX rate exists for a row currency as of `A` | Service raises `ValueError`; the API maps it to HTTP `400`. |
| No rows match the filters | Returns an empty page with `total=0` and `data_quality_status=UNKNOWN`. |
| Returned page is smaller than all matching rows or `skip > 0` | Returns `data_quality_status=PARTIAL`. |
| Returned page contains all matching rows from offset zero | Returns `data_quality_status=COMPLETE`. |
| `sort_by` is not in the allowed sort-field set | Falls back to `transaction_date`. |
| Row-level `transaction_costs` exist | Returned as `costs[]`; this endpoint does not aggregate them into cost curves. |
| Row-level linked `cashflow` exists | Returned as `cashflow`; this endpoint does not aggregate it into operational cashflow methodology. |

## Configuration Options

| Option | Current value |
| --- | --- |
| Default sort field | `transaction_date` |
| Default sort order | `desc` |
| Allowed sort fields | `transaction_date`, `settlement_date`, `quantity`, `price`, `gross_transaction_amount` |
| Default business calendar | `DEFAULT_BUSINESS_CALENDAR_CODE` |
| Product identity | `TransactionLedgerWindow:v1` |

## Outputs

| Field | Methodology mapping |
| --- | --- |
| `product_name`, `product_version` | Governed source-data product identity. |
| `portfolio_id` | Requested portfolio. |
| `reporting_currency` | Requested reporting currency, if supplied. |
| `total`, `skip`, `limit` | Matching row count and page controls. |
| `transactions[]` | Row-level transaction evidence after filters, sorting, and pagination. |
| `transactions[].costs[]` | Joined explicit transaction-cost rows without aggregation. |
| `transactions[].cashflow` | Joined linked cashflow row when present. |
| `*_reporting_currency` fields | Optional row-level restatement into requested reporting currency. |
| `as_of_date` | Effective booked-state cap or fallback output date. |
| `data_quality_status` | Page completeness posture for the returned ledger window. |
| `latest_evidence_timestamp` | Latest durable transaction `updated_at` timestamp for the filtered ledger window. |

## Worked Example

Request:

`GET /portfolios/P1/transactions?as_of_date=2026-03-10&reporting_currency=SGD&limit=10`

Source facts:

| Row | Raw field | Raw amount | Currency | FX rate to SGD | Restated field | Restated amount |
| --- | --- | ---: | --- | ---: | --- | ---: |
| T1 | `trade_fee` | 12.50 | USD | 1.36 | `trade_fee_reporting_currency` | 17.00 |
| T1 | `realized_gain_loss` | 250.00 | USD | 1.36 | `realized_gain_loss_reporting_currency` | 340.00 |
| T2 | `withholding_tax_amount` | 10.00 | USD | 1.36 | `withholding_tax_amount_reporting_currency` | 13.60 |
| T2 | `net_interest_amount` | 110.00 | USD | 1.36 | `net_interest_amount_reporting_currency` | 149.60 |

Final output mapping:

| Response field | Value |
| --- | ---: |
| `total` | 2 |
| `data_quality_status` | `COMPLETE` |
| `transactions[0].trade_fee_reporting_currency` | 17.00 |
| `transactions[1].withholding_tax_amount_reporting_currency` | 13.60 |
