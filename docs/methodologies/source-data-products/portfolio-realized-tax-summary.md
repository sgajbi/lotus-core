# Portfolio Realized Tax Summary Methodology

## Metric

`PortfolioRealizedTaxSummary:v1` is the core-owned operational source-data product exposed by
`GET /portfolios/{portfolio_id}/realized-tax-summary`.

It summarizes explicit realized tax evidence recorded on booked transaction ledger rows for one
portfolio. The product aggregates only source-recorded `withholding_tax_amount` and
`other_interest_deductions_amount` fields, grouped by ledger currency, with optional
reporting-currency restatement. It is not tax advice, after-tax optimization, tax-loss harvesting,
jurisdiction-specific recommendation, client-tax approval, tax-reporting certification, execution
quality, or OMS acknowledgement.

## Endpoint and Mode Coverage

| Mode | Request shape | Implemented behavior |
| --- | --- | --- |
| Default realized-tax summary | No `as_of_date` | Resolves `as_of_date` to the latest business date when available, otherwise the current application date. Includes tax-evidence rows with `transaction_date <= as_of_date`. |
| Explicit as-of summary | `as_of_date=<date>` | Includes tax-evidence rows with `transaction_date <= as_of_date`. |
| Date-window summary | `start_date=<date>` and/or `end_date=<date>` | Applies inclusive lower and upper bounds on `transaction_date` before aggregating explicit tax evidence. |
| Reporting-currency summary | `reporting_currency=<ccy>` | Restates each currency total to the requested currency using the latest available FX rate on or before the effective `as_of_date`. Raw currency totals remain unchanged. |

## Inputs

| Input | Source | Required | Meaning |
| --- | --- | --- | --- |
| `portfolio_id` | Path parameter | Yes | Portfolio whose booked transaction ledger is summarized. |
| `start_date` | Query parameter | No | Inclusive lower bound on `transaction_date`. |
| `end_date` | Query parameter | No | Inclusive upper bound on `transaction_date`. |
| `as_of_date` | Query parameter | No | Booked-state cap on `transaction_date`. |
| `reporting_currency` | Query parameter | No | Currency used to populate `reporting_currency_total_tax_amount`. |

## Upstream Data Sources

| Source | Used fields | Inclusion rule |
| --- | --- | --- |
| `portfolios` | `portfolio_id`, `currency` | Portfolio must exist; `currency` is returned as `base_currency`. |
| `business_dates` | `date`, `calendar_code` | Supplies the default `as_of_date` when the caller omits it. |
| `transactions` | `transaction_id`, `transaction_date`, `currency`, `withholding_tax_amount`, `other_interest_deductions_amount`, `updated_at` | Rows must match the requested portfolio, date filters, and contain at least one explicit tax-evidence field. |
| `fx_rates` | `from_currency`, `to_currency`, `rate_date`, `rate` | Used only for optional reporting-currency restatement. |

## Unit Conventions

Raw currency totals remain in each transaction row's `currency`. Null tax fields contribute zero to
their respective component and do not create inferred tax evidence.

When `reporting_currency` is supplied, each currency group's total tax amount is multiplied by the
latest FX rate with `rate_date <= as_of_date`. Same-currency restatement uses a rate of `1`.

No client-specific tax treatment, rule interpretation, tax-loss harvesting, after-tax portfolio
optimization, tax-reporting certification, or OMS status is derived.

## Variable Dictionary

| Symbol | Response or source field | Definition |
| --- | --- | --- |
| `P` | `portfolio_id` | Requested portfolio. |
| `S` | `start_date` | Optional inclusive start date. |
| `E` | `end_date` | Optional inclusive end date. |
| `A` | `as_of_date` | Effective booked-state cap. |
| `M` | matching transactions | Booked transaction rows for `P`, `S`, `E`, and `A` with explicit tax evidence. |
| `C` | `currency` | Ledger currency for each matching row. |
| `W_c` | `withholding_tax_amount` | Sum of explicit withholding-tax amounts for currency `c`. |
| `D_c` | `other_interest_deductions_amount` | Sum of explicit other-interest-deduction amounts for currency `c`. |
| `T_c` | `total_tax_amount` | `W_c + D_c`. |
| `X_c` | FX rate | Latest rate from currency `c` to requested reporting currency on or before `A`. |
| `R` | `reporting_currency_total_tax_amount` | `sum(T_c * X_c)` across returned currency groups. |

## Methodology and Formulas

The matching row set is:

`M = rows where portfolio_id = P and tax evidence exists`

Date filters are applied as:

`transaction_date >= start_of_day(S)` when `S` is supplied

`transaction_date < start_of_next_day(E)` when `E` is supplied

`transaction_date < start_of_next_day(A)` when an effective `A` is supplied

For each currency `c` in `M`:

`W_c = sum(coalesce(row.withholding_tax_amount, 0) for row in M where row.currency = c)`

`D_c = sum(coalesce(row.other_interest_deductions_amount, 0) for row in M where row.currency = c)`

`T_c = W_c + D_c`

If a reporting currency is requested:

`R = sum(T_c * X_c for each currency c)`

## Step-by-Step Computation

1. Verify the portfolio exists and return its base currency.
2. Resolve the effective `A`: use request `as_of_date` when supplied; otherwise use the latest
   business date for the default business calendar or the current application date when no business
   date exists.
3. Count all portfolio transaction rows matching the date/as-of filters for source-window posture.
4. Load only matching rows that contain explicit `withholding_tax_amount` or
   `other_interest_deductions_amount` evidence.
5. Aggregate evidence rows by `currency`.
6. For each currency group, calculate withholding, other deduction, total amount, and contributing
   evidence-row count.
7. If `reporting_currency` is supplied, restate each currency total to the requested currency using
   the latest FX rate on or before `A`.
8. Return source-data runtime metadata, evidence counts, grouped totals, optional reporting total,
   and a reason code describing whether evidence existed.

## Validation and Failure Behavior

| Condition | Behavior |
| --- | --- |
| Portfolio id does not exist | Service raises `LookupError`; the API maps it to HTTP `404`. |
| `reporting_currency` is supplied but no FX rate exists for a source currency as of `A` | Service raises `ValueError`; the API maps it to HTTP `400`. |
| No transaction rows match the portfolio/date/as-of window | Returns no currency totals, `source_transaction_count=0`, and `PORTFOLIO_REALIZED_TAX_EVIDENCE_EMPTY`. |
| Transaction rows exist but none carry explicit tax evidence | Returns no currency totals and `PORTFOLIO_REALIZED_TAX_EVIDENCE_EMPTY`; the service does not fabricate zero-tax conclusions. |
| Matching evidence rows exist | Returns one currency total per ledger currency and `PORTFOLIO_REALIZED_TAX_SUMMARY_READY`. |

## Configuration Options

| Option | Current value |
| --- | --- |
| Default business calendar | `DEFAULT_BUSINESS_CALENDAR_CODE` |
| Product identity | `PortfolioRealizedTaxSummary:v1` |
| Currency grouping | `transactions.currency` |
| Restatement source | `fx_rates` latest rate on or before effective `as_of_date` |

## Outputs

| Field | Methodology mapping |
| --- | --- |
| `product_name`, `product_version` | Governed source-data product identity. |
| `portfolio_id` | Requested portfolio. |
| `base_currency` | Portfolio master currency. |
| `reporting_currency` | Requested reporting currency, if supplied. |
| `source_transaction_count` | Count of all portfolio transaction rows matching the date/as-of window. |
| `tax_evidence_transaction_count` | Count of rows contributing explicit tax evidence. |
| `currency_totals[]` | Per-currency withholding, other deduction, total tax amount, and evidence-row count. |
| `reporting_currency_total_tax_amount` | Optional restated total across currency groups. |
| `reason_codes[]` | `PORTFOLIO_REALIZED_TAX_SUMMARY_READY` or `PORTFOLIO_REALIZED_TAX_EVIDENCE_EMPTY`. |
| `latest_evidence_timestamp` | Latest durable transaction `updated_at` timestamp for the filtered source window. |

## Worked Example

Request:

`GET /portfolios/P1/realized-tax-summary?as_of_date=2026-03-10&reporting_currency=SGD`

Source facts:

| Row | Currency | Withholding tax | Other deductions | FX rate to SGD |
| --- | --- | ---: | ---: | ---: |
| T1 | USD | 10.00 | 5.00 | 1.36 |
| T2 | USD | null | 2.50 | 1.36 |
| T3 | EUR | 8.00 | null | 1.50 |

Final output mapping:

| Response field | Value |
| --- | ---: |
| `currency_totals[USD].withholding_tax_amount` | 10.00 |
| `currency_totals[USD].other_tax_deductions_amount` | 7.50 |
| `currency_totals[USD].total_tax_amount` | 17.50 |
| `currency_totals[EUR].total_tax_amount` | 8.00 |
| `tax_evidence_transaction_count` | 3 |
| `reporting_currency_total_tax_amount` | 35.80 |
