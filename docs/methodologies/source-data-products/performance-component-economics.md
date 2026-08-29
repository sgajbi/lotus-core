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
| `income` | `transactions.net_interest_amount` after withholding/other deductions and before separately reported transaction fees |
| `tax` | `transactions.withholding_tax_amount`, `other_interest_deductions_amount` |
| `realized_capital_pnl` | `transactions.realized_capital_pnl_local/base` plus `realized_pnl_local_currency` |
| `realized_fx_pnl` | `transactions.realized_fx_pnl_local/base` plus `realized_pnl_local_currency` |
| `realized_total_pnl` | `transactions.realized_total_pnl_local/base` plus `realized_pnl_local_currency` |
| `fx_context` | `transactions.transaction_fx_rate`, `fx_contract_id` |

Zero or absent fields remain zero or null. The product does not fabricate missing economics.
Rows also expose `allocated_cost_basis_local` and `allocated_cost_basis_base` as transaction-level
audit evidence for non-security consideration. These fields explain realized P&L but are not
reported as a separate additive component family, because allocated basis is an input to the P&L
equation rather than a gain, loss, fee, tax, income, or cashflow amount.

For INTEREST rows, `net_interest_amount` and fee evidence are intentionally separate components.
Consumers must not infer that `net_interest_amount` is final settlement cash: income settlement
subtracts the separately reported fee, while expense settlement adds it. The linked latest-epoch
cashflow remains the source-owned settled amount.

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

The QCP implementation keeps the source-data anti-corruption boundary in four stages:

1. `SqlAlchemyTransactionEconomicsReader` maps ORM rows into frozen
   `BookedTransactionEconomics`, `TransactionCashflowEvidence`, and
   `TransactionCostComponentEvidence` domain records,
2. `TransactionEconomicsReader` defines the application-facing source port,
3. source-evidence policy operates over component families, supportability, data quality, totals, and
   lineage,
4. response-envelope assembly produces product identity, page metadata, runtime metadata, and API
   construction.

| Field family | Provenance |
| --- | --- |
| `rows[*].transaction_id`, `portfolio_id`, `security_id`, `transaction_type`, `transaction_date`, `currency`, `trade_currency`, `gross_transaction_amount`, tax, income, realized P&L, FX context | Source-authored transaction evidence, normalized only for identifiers, case, and Decimal/date representation. |
| `rows[*].cashflow_*` | Source-authored latest linked cashflow evidence selected by the repository by highest cashflow epoch and id. |
| `rows[*].trade_fee_components` | Source-authored transaction-cost rows de-duplicated by component identity, or transaction `trade_fee` fallback when no cost rows exist. |
| `rows[*].source_lineage` | Core source-data policy metadata for the row evidence contract. |
| `component_totals` and `component_totals_scope` | Core response policy derived from the returned page only. |
| `supportability` and `data_quality_status` | Core source-evidence policy derived from returned rows and paging state. |
| `page`, `request_fingerprint`, runtime source-data metadata, and top-level `lineage` | QCP response-envelope metadata derived by Core assembly policy. `content_hash`, `source_digest`, and `source_batch_fingerprint` are the same deterministic SHA-256 value and exclude volatile `generated_at`. |

## Supportability

`READY` with reason `PERFORMANCE_COMPONENT_ECONOMICS_READY` means at least one source row was
returned and no additional page is indicated. `READY` with reason
`PERFORMANCE_COMPONENT_ECONOMICS_NO_ACTIVITY` means Core proved the portfolio and base-currency
authority, successfully queried the initial page of the complete bounded request scope, and found no
matching activity. That authoritative empty result has `source_row_count=0`, `rows=[]`, no observed
families, no missing families, `data_quality_status=COMPLETE`, `source_evidence_current=true`, and
`freshness_status=CURRENT`. `latest_evidence_timestamp` remains null because there is no source row;
`generated_at` is captured after Core completes the authoritative scope query. The result is not
evidence that every component amount was zero.

`DEGRADED` with reason `PERFORMANCE_COMPONENT_ECONOMICS_PAGE_PARTIAL` means the current response is
a valid partial page and `page.next_page_token` must be followed to exhaust the requested window.
An unexpectedly empty continuation page is `UNAVAILABLE` with reason
`PERFORMANCE_COMPONENT_ECONOMICS_PAGE_EVIDENCE_CHANGED`, `data_quality_status=UNKNOWN`, and all
supported families missing. A continuation can prove only the suffix after its cursor, not that the
complete bounded request scope had no activity; concurrent source changes therefore fail closed.
Missing portfolios and invalid request or cursor scopes fail closed through the documented HTTP
problem contract. Persistence/query failures remain errors; Core does not convert an unproved scope
into `READY / PERFORMANCE_COMPONENT_ECONOMICS_NO_ACTIVITY`.

For non-empty pages, `observed_component_families` and `missing_component_families` describe
coverage for the returned rows; downstream consumers must decide which families are required for a
specific performance workflow. For an authoritative empty window, both lists are empty because the
absence of activity does not make supported families incomplete.

## Authoritative Empty Example

For canonical portfolio `PB_SG_GLOBAL_BAL_001`, a successfully queried interval with no component
economics activity, such as `2026-04-01` through `2026-04-10`, returns:

```json
{
  "supportability": {
    "state": "READY",
    "reason": "PERFORMANCE_COMPONENT_ECONOMICS_NO_ACTIVITY",
    "source_row_count": 0,
    "observed_component_families": [],
    "missing_component_families": []
  },
  "rows": [],
  "data_quality_status": "COMPLETE",
  "latest_evidence_timestamp": null,
  "source_evidence_current": true,
  "freshness_status": "CURRENT"
}
```

This example states the contract posture for a successful empty read. Canonical runtime evidence is
still required after deployment; documentation does not substitute for a live database query.

## Explicit Non-Claims

This product is not contribution analytics, attribution analytics, a return calculator, tax advice,
best-execution evidence, venue-routing evidence, OMS acknowledgement, or a performance-ready UI
claim. Downstream `lotus-performance` consumption and proof remain tracked separately.
