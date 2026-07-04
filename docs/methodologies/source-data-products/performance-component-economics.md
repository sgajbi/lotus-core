# PerformanceComponentEconomics Methodology

## Product Identity

- Product: `PerformanceComponentEconomics:v1`
- Route: `POST /integration/portfolios/{portfolio_id}/performance-component-economics`
- Owner: `lotus-core`
- Primary consumer: `lotus-performance`
- Boundary: source-authored economics evidence only. `lotus-performance` owns contribution,
  attribution, and return methodology.

## Inputs

The product reads `transactions` for the requested `portfolio_id`, inclusive transaction-date
window, and `as_of_date` bound. Optional `security_ids` and `transaction_types` narrow the source
rows. The inclusive transaction-date window remains capped at 366 days. It joins
`transaction_costs` and the latest `cashflows` epoch for each transaction. The row-level evidence
read is cursor-paged with `page.page_size + 1` source-row budgeting.

## Deterministic Row Selection

Rows are selected when:

1. `transactions.portfolio_id` equals the requested portfolio,
2. `transaction_date >= window.start_date`,
3. `transaction_date <= window.end_date`,
4. `transaction_date <= as_of_date`,
5. the inclusive request window is 366 days or less,
6. optional security and transaction-type filters match after canonical normalization.

Rows are ordered by normalized `security_id`, transaction date, and `transaction_id`. Linked
cashflows are selected deterministically by highest `cashflows.epoch`, then highest `cashflows.id`.

## Paging

The request accepts optional cursor paging controls through `page.page_size` and
`page.page_token`. Page tokens are scoped to the full request fingerprint, including portfolio,
window, `as_of_date`, filters, and tenant. Tokens from another request scope are rejected with HTTP
400 by the query control plane.

Repository reads request `page_size + 1` ordered rows to determine `has_more` without materializing
the full transaction window. Response `page.sort_key` is
`security_id:asc,transaction_date:asc,transaction_id:asc`; `page.returned_component_count` reports
the number of row-level economics records returned in the current response, and
`page.next_page_token` is present only when another page exists.

## Component Families

The contract source-authors these component families when evidence exists:

| Family | Source fields |
| --- | --- |
| `cashflow` | linked latest-epoch `cashflows.amount`, `currency`, canonical uppercase `classification`, canonical uppercase `timing`, flow-scope flags |
| `fee` | explicit per-currency `transaction_costs.amount` rows as `trade_fee_components`, falling back to `transactions.trade_fee` and `transactions.trade_currency` |
| `income` | `transactions.net_interest_amount` |
| `tax` | `transactions.withholding_tax_amount`, `other_interest_deductions_amount` |
| `realized_capital_pnl` | `transactions.realized_capital_pnl_local/base` plus `realized_pnl_local_currency` |
| `realized_fx_pnl` | `transactions.realized_fx_pnl_local/base` plus `realized_pnl_local_currency` |
| `realized_total_pnl` | `transactions.realized_total_pnl_local/base` plus `realized_pnl_local_currency` |
| `fx_context` | `transactions.transaction_fx_rate`, `fx_contract_id` |

Zero or absent fields remain zero or null. The product does not fabricate missing economics.

`transaction_costs` component identity is normalized as `(transaction_id, lower(trim(fee_type)),
upper(trim(currency)))`. The database enforces one row per normalized component. The response
builder also de-duplicates already-loaded duplicate rows at that grain before producing
`trade_fee_components`, so accidental replay or legacy duplicate rows cannot inflate fee evidence.

## Totals

`component_totals` groups non-zero component amounts by `component_family` and currency for the
returned page. `component_totals_scope` is always `returned_page`; consumers that need full-window
totals must iterate all pages or request a future aggregate contract. Fee totals use
`trade_fee_currency`, cashflow totals use `cashflow_currency`, income and tax totals use the
transaction economics currency, and realized `*_pnl_base` totals use the portfolio base currency.
Row-level realized `*_pnl_local` fields carry `realized_pnl_local_currency`, normally the
transaction trade currency, so consumers do not infer local P&L currency from book currency. Tax
totals combine withholding tax and other interest deductions in the same currency while preserving
row-level fields separately.

When positive transaction-cost rows on one transaction carry multiple currencies, row-level
`trade_fee_currency` is `MIXED`, `trade_fee_amount` is zero, and `trade_fee_components` carries one
amount per currency. Fee totals are built from those per-currency components. Downstream consumers
must not treat `MIXED` as an ISO currency.

## Field Provenance And Assembly Boundaries

The implementation keeps the source-data anti-corruption boundary in three stages:

1. typed read records from the repository,
2. source-evidence policy over component families, supportability, data quality, totals, and
   lineage,
3. response-envelope assembly for product identity, page metadata, runtime metadata, and DTO
   construction.

| Field family | Provenance |
| --- | --- |
| `rows[*].transaction_id`, `portfolio_id`, `security_id`, `transaction_type`, `transaction_date`, `currency`, `trade_currency`, `gross_transaction_amount`, tax, income, realized P&L, FX context | Source-authored transaction evidence, normalized only for identifiers, case, and Decimal/date representation. |
| `rows[*].cashflow_*` | Source-authored latest linked cashflow evidence selected by the repository by highest cashflow epoch and id. |
| `rows[*].trade_fee_components` | Source-authored transaction-cost rows de-duplicated by component identity, or transaction `trade_fee` fallback when no cost rows exist. |
| `rows[*].source_lineage` | Core source-data policy metadata for the row evidence contract. |
| `component_totals` and `component_totals_scope` | Core response policy derived from the returned page only. |
| `supportability` and `data_quality_status` | Core source-evidence policy derived from returned rows and paging state. |
| `page`, `request_fingerprint`, runtime source-data metadata, and top-level `lineage` | Response-envelope metadata derived by Core assembly policy. |

## Supportability

`READY` means at least one source row was returned and no additional page is indicated. `DEGRADED`
with reason `PERFORMANCE_COMPONENT_ECONOMICS_PAGE_PARTIAL` means the current response is a valid
partial page and `page.next_page_token` must be followed to exhaust the requested window.
`UNAVAILABLE` means the portfolio exists but no source rows matched the requested scope.
`observed_component_families` and `missing_component_families` describe coverage for the returned
page; downstream consumers must decide which families are required for a specific performance
workflow.

## Explicit Non-Claims

This product is not contribution analytics, attribution analytics, a return calculator, tax advice,
best-execution evidence, venue-routing evidence, OMS acknowledgement, or a performance-ready UI
claim. Downstream `lotus-performance` consumption and proof remain tracked separately.
