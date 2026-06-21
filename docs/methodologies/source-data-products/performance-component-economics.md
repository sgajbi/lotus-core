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
rows. It joins `transaction_costs` and the latest `cashflows` epoch for each transaction.

## Deterministic Row Selection

Rows are selected when:

1. `transactions.portfolio_id` equals the requested portfolio,
2. `transaction_date >= window.start_date`,
3. `transaction_date <= window.end_date`,
4. `transaction_date <= as_of_date`,
5. optional security and transaction-type filters match after canonical normalization.

Rows are ordered by `security_id`, `transaction_date`, and `transaction_id`. Linked cashflows are
selected deterministically by highest `cashflows.epoch`, then highest `cashflows.id`.

## Component Families

The contract source-authors these component families when evidence exists:

| Family | Source fields |
| --- | --- |
| `cashflow` | linked latest-epoch `cashflows.amount`, `currency`, canonical uppercase `classification`, canonical uppercase `timing`, flow-scope flags |
| `fee` | explicit `transaction_costs.amount` rows plus `trade_fee_currency`, falling back to `transactions.trade_fee` and `transactions.trade_currency` |
| `income` | `transactions.net_interest_amount` |
| `tax` | `transactions.withholding_tax_amount`, `other_interest_deductions_amount` |
| `realized_capital_pnl` | `transactions.realized_capital_pnl_local/base` |
| `realized_fx_pnl` | `transactions.realized_fx_pnl_local/base` |
| `realized_total_pnl` | `transactions.realized_total_pnl_local/base` |
| `fx_context` | `transactions.transaction_fx_rate`, `fx_contract_id` |

Zero or absent fields remain zero or null. The product does not fabricate missing economics.

## Totals

`component_totals` groups non-zero component amounts by `component_family` and currency. Fee totals
use `trade_fee_currency`, cashflow totals use `cashflow_currency`, income and tax totals use the
transaction economics currency, and realized `*_pnl_base` totals use the portfolio base currency.
Tax totals combine withholding tax and other interest deductions in the same currency while
preserving row-level fields separately.

When positive transaction-cost rows on one transaction carry multiple currencies, the row-level
`trade_fee_currency` and fee total currency are `MIXED`. Downstream consumers must not treat
`MIXED` as an ISO currency or blindly aggregate it with single-currency fee totals.

## Supportability

`READY` means at least one source row was returned. `UNAVAILABLE` means the portfolio exists but no
source rows matched the requested scope. `observed_component_families` and
`missing_component_families` describe coverage; downstream consumers must decide which families are
required for a specific performance workflow.

## Explicit Non-Claims

This product is not contribution analytics, attribution analytics, a return calculator, tax advice,
best-execution evidence, venue-routing evidence, OMS acknowledgement, or a performance-ready UI
claim. Downstream `lotus-performance` consumption and proof remain tracked separately.
