# Transaction Cost Curve Methodology

## Metric

`TransactionCostCurve:v1` is the core-owned observed transaction-cost evidence product exposed by
`POST /integration/portfolios/{portfolio_id}/transaction-cost-curve`.

It returns observed booked fee evidence grouped by security, transaction type, and fee currency for
a requested portfolio and transaction-date window. The product lets downstream proof packs
distinguish source-backed booked-fee evidence from local estimated construction cost. It is not a
predictive market-impact model, venue-routing model, fill-quality measure, best-execution
assessment, OMS acknowledgement, or minimum-cost execution optimizer.

## Endpoint and Mode Coverage

| Request shape | Implemented behavior |
| --- | --- |
| `portfolio_id` path parameter | Selects the portfolio whose booked transaction-cost evidence is requested. |
| `as_of_date` | Bounds the request scope and product runtime metadata. |
| `window.start_date` / `window.end_date` | Inclusive transaction-date window used for observed evidence. |
| optional `security_ids` | Restricts evidence to requested securities and reports missing requested securities as supportability gaps. |
| optional `transaction_types` | Restricts evidence to requested transaction types after upper-case normalization. |
| `min_observation_count` | Suppresses curve points whose group has fewer observed transactions than the threshold. |
| `page.page_size` / `page.page_token` | Returns deterministic cursor pages ordered by security id, transaction type, and currency. |

The product currently has one implemented methodology: observed booked-fee aggregation. It does not
switch into simulated, quoted, venue, broker, or expected-cost modes.

## Inputs

| Input | Source | Required | Meaning |
| --- | --- | --- | --- |
| `portfolio_id` | Path parameter | Yes | Portfolio whose evidence is returned. |
| `as_of_date` | Request body | Yes | Business date for request identity and metadata. |
| `window.start_date`, `window.end_date` | Request body | Yes | Inclusive transaction-date evidence window. |
| `security_ids` | Request body | No | Optional security filter and supportability coverage expectation. |
| `transaction_types` | Request body | No | Optional transaction-type filter. |
| `min_observation_count` | Request body | No, default `1` | Minimum number of qualifying booked transactions for a curve point. |

## Upstream Data Sources

| Source | Used fields | Inclusion rule |
| --- | --- | --- |
| `portfolios` | `portfolio_id` | Portfolio must exist. |
| `transactions` | `transaction_id`, `security_id`, `transaction_type`, `currency`, `transaction_date`, `gross_transaction_amount`, `trade_fee`, `updated_at` | Transaction must match the portfolio, requested filters, as-of scope, and requested transaction-date window. Gross transaction amount must be non-zero after absolute-value normalization. |
| `transaction_costs` | `amount` | If explicit transaction-cost rows exist, their amounts are summed and used as the fee amount. If no explicit cost rows exist, the transaction `trade_fee` field is used. |

Transactions with zero or missing fee evidence, or zero gross notional, do not contribute to a curve
point. Cost rows take precedence over `trade_fee` so the product does not double count fees when
both representations are present.

## Unit Conventions

All grouped monetary fields use the transaction fee currency returned as `currency`.

`gross_transaction_amount` is converted to absolute notional before aggregation so buy and sell
notionals are comparable as observed cost denominators. Fee amounts must be positive. Negative or
zero fees are treated as unusable evidence rather than rebates or execution-quality conclusions.

No FX conversion, market-impact adjustment, broker spread estimate, venue normalization, tax
calculation, or liquidity bucketing is performed by this product.

## Variable Dictionary

| Symbol | Response or source field | Definition |
| --- | --- | --- |
| `P` | `portfolio_id` | Requested portfolio. |
| `A` | `as_of_date` | Business as-of date for request scope. |
| `W` | `window` | Inclusive transaction-date evidence window. |
| `G` | `(security_id, transaction_type, currency)` | Deterministic grouping key. |
| `n_G` | `observation_count` | Number of qualifying booked transactions in group `G`. |
| `F_i` | transaction-cost amount or `trade_fee` | Positive observed fee amount for transaction `i`. |
| `N_i` | `abs(gross_transaction_amount)` | Positive observed transaction notional for transaction `i`. |
| `TC_G` | `total_cost` | Sum of observed fees in group `G`. |
| `TN_G` | `total_notional` | Sum of absolute gross notionals in group `G`. |
| `B_i` | per-transaction cost bps | `F_i / N_i * 10000`. |
| `AB_G` | `average_cost_bps` | Notional-weighted observed average cost in basis points for group `G`. |
| `MIN_G` | `min_cost_bps` | Minimum per-transaction observed cost bps in group `G`. |
| `MAX_G` | `max_cost_bps` | Maximum per-transaction observed cost bps in group `G`. |

## Methodology and Formulas

For each qualifying group `G`:

`TC_G = sum(F_i for each transaction i in G)`

`TN_G = sum(N_i for each transaction i in G)`

`B_i = F_i / N_i * 10000`

`AB_G = TC_G / TN_G * 10000`

`MIN_G = min(B_i for each transaction i in G)`

`MAX_G = max(B_i for each transaction i in G)`

`average_cost_bps`, `min_cost_bps`, and `max_cost_bps` are rounded to four decimal places.

## Step-by-Step Computation

1. Verify that the requested portfolio exists.
2. Build a request-scope fingerprint from portfolio id, as-of date, window, filters, minimum
   observation count, and tenant scope.
3. Decode and validate the optional page token against the request-scope fingerprint.
4. Query booked transactions and explicit transaction-cost rows for the portfolio, as-of date,
   requested transaction-date window, and optional filters.
5. For each transaction, determine `F_i` from summed explicit `transaction_costs.amount` when cost
   rows exist; otherwise use `trade_fee`.
6. Exclude transactions where `F_i <= 0` or `abs(gross_transaction_amount) <= 0`.
7. Group remaining transactions by `(security_id, upper(transaction_type), upper(currency))`.
8. Exclude groups whose `observation_count` is less than `min_observation_count`.
9. Compute total cost, total notional, average cost bps, min cost bps, max cost bps, first observed
   date, last observed date, and a bounded deterministic sample of up to five transaction ids.
10. Sort curve points by security id, transaction type, and currency.
11. Apply cursor paging and emit a next page token when more grouped points remain.
12. Return supportability, lineage, and runtime source-data product metadata.

## Validation and Failure Behavior

| Condition | Behavior |
| --- | --- |
| Portfolio id does not exist | Service raises `LookupError`; the API maps it to HTTP `404`. |
| `window.end_date < window.start_date` | Request validation rejects the request. |
| Blank or duplicate `security_ids` | Request validation rejects the request. |
| Blank or duplicate `transaction_types` | Request validation rejects the request after upper-case normalization. |
| Page token scope does not match the request | Service raises `ValueError`; the API maps it to HTTP `400`. |
| No qualifying observed cost evidence | Response returns no curve points with supportability `UNAVAILABLE` and reason `TRANSACTION_COST_EVIDENCE_NOT_FOUND`. |
| Requested securities are missing qualifying points | Response carries supportability `INCOMPLETE` and reason `TRANSACTION_COST_EVIDENCE_MISSING_FOR_SECURITIES`. |
| More grouped points exist than the page size | Response carries supportability `DEGRADED` and reason `TRANSACTION_COST_CURVE_PAGE_PARTIAL` for that page. |

`data_quality_status` is `COMPLETE` only when the returned supportability is `READY`; otherwise it
is `PARTIAL`. This status certifies the observed-fee evidence response only, not execution quality
or best execution.

## Configuration Options

| Option | Current value |
| --- | --- |
| Default page size | `250` curve points |
| Maximum page size | `1000` curve points |
| Default minimum observation count | `1` transaction |
| Maximum minimum observation count | `100` transactions |
| Sort order | `security_id:asc,transaction_type:asc,currency:asc` |
| Product identity | `TransactionCostCurve:v1` |

## Outputs

| Field | Methodology mapping |
| --- | --- |
| `curve_points[].security_id` | Group key security id. |
| `curve_points[].transaction_type` | Group key transaction type, normalized to upper case. |
| `curve_points[].currency` | Group key fee/notional currency, normalized to upper case. |
| `curve_points[].observation_count` | `n_G`. |
| `curve_points[].total_cost` | `TC_G`. |
| `curve_points[].total_notional` | `TN_G`. |
| `curve_points[].average_cost_bps` | `AB_G`. |
| `curve_points[].min_cost_bps` | `MIN_G`. |
| `curve_points[].max_cost_bps` | `MAX_G`. |
| `curve_points[].first_observed_date` | Earliest transaction date in group `G`. |
| `curve_points[].last_observed_date` | Latest transaction date in group `G`. |
| `curve_points[].sample_transaction_ids` | Deterministic sorted sample of up to five source transaction ids. |
| `supportability` | Readiness state for observed cost evidence only. |

## Worked Example

Request:

`POST /integration/portfolios/PB_SG_GLOBAL_BAL_001/transaction-cost-curve`

```json
{
  "as_of_date": "2026-05-03",
  "window": {"start_date": "2026-04-01", "end_date": "2026-04-30"},
  "security_ids": ["EQ_US_AAPL"],
  "transaction_types": ["BUY"],
  "min_observation_count": 2
}
```

Source facts:

| Transaction | Security | Type | Currency | Fee `F_i` | Notional `N_i` | Cost bps `B_i` |
| --- | --- | --- | --- | ---: | ---: | ---: |
| `TXN-AAPL-001` | `EQ_US_AAPL` | `BUY` | `USD` | 10 | 10000 | 10 |
| `TXN-AAPL-002` | `EQ_US_AAPL` | `BUY` | `USD` | 30 | 20000 | 15 |

Final output mapping:

| Response field | Value |
| --- | ---: |
| `curve_points[0].observation_count` | 2 |
| `curve_points[0].total_cost` | 40 |
| `curve_points[0].total_notional` | 30000 |
| `curve_points[0].average_cost_bps` | 13.3333 |
| `curve_points[0].min_cost_bps` | 10.0000 |
| `curve_points[0].max_cost_bps` | 15.0000 |
