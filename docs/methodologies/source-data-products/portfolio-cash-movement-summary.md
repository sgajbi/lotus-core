# Portfolio Cash Movement Summary Methodology

## Metric

`PortfolioCashMovementSummary:v1` is the `lotus-core` source-owned metric family for bounded
portfolio cash movement evidence. It summarizes latest-version `cashflows` rows for one portfolio
and one inclusive cashflow-date window.

The metric outputs bucket-level signed cash movement totals, source row counts, and movement
direction by source-owned classification, timing, currency, and flow scope.

## Endpoint and Mode Coverage

| Endpoint | Mode | Product |
| --- | --- | --- |
| `GET /portfolios/{portfolio_id}/cash-movement-summary` | Operational read | `PortfolioCashMovementSummary:v1` |

This endpoint is evidence only. It is not a cashflow forecast, income plan, funding
recommendation, treasury instruction, liquidity advice, tax methodology, performance attribution,
execution-quality assessment, or OMS acknowledgement.

## Inputs

| Field | Source | Required | Description |
| --- | --- | --- | --- |
| `portfolio_id` | Request path | Yes | Portfolio whose cashflow rows are summarized. |
| `start_date` | Request query | Yes | Inclusive cashflow-date window start. |
| `end_date` | Request query | Yes | Inclusive cashflow-date window end. |
| `transaction_id` | `cashflows` | Yes | Transaction identity used for latest-row selection. |
| `id` | `cashflows` | Yes | Tie-breaker for same-epoch cashflow restatements. |
| `epoch` | `cashflows` | Yes | Cashflow restatement epoch. |
| `cashflow_date` | `cashflows` | Yes | Date used for window inclusion. |
| `classification` | `cashflows` | Yes | Source-owned movement classification. |
| `timing` | `cashflows` | Yes | Source-owned timing bucket. |
| `currency` | `cashflows` | Yes | Currency for the signed amount. |
| `amount` | `cashflows` | Yes | Signed source cashflow amount. |
| `is_position_flow` | `cashflows` | Yes | Position-scope flag. |
| `is_portfolio_flow` | `cashflows` | Yes | Portfolio-scope flag. |
| `updated_at` | `cashflows` | Yes | Evidence timestamp for latest-evidence posture. |

## Upstream Data Sources

| Source | Use |
| --- | --- |
| `portfolios` | Confirms the requested portfolio exists and supplies the portfolio authority boundary. |
| `cashflows` | Supplies latest source rows for cash movement grouping and totals. |

Rows from `transactions`, `transaction_costs`, tax-lot tables, cash-account balance tables, and FX
tables are not joined by this product. Currency conversion, tax interpretation, funding logic, and
cash-account balance derivation stay outside this methodology.

## Unit Conventions

1. `amount` and `total_amount` are signed monetary values in `currency`.
2. Positive totals are inflows; negative totals are outflows; zero totals are flat movement.
3. Mixed currencies are never converted or netted together. They remain separate buckets.
4. Counts are source-row counts, not distinct transaction counts after downstream filtering.

## Variable Dictionary

| Symbol | Field | Definition |
| --- | --- | --- |
| `P` | `portfolio_id` | Requested portfolio id. |
| `D0` | `start_date` | Inclusive cashflow-date window start. |
| `D1` | `end_date` | Inclusive cashflow-date window end. |
| `R` | latest row set | Cashflow rows ranked by `(transaction_id, epoch DESC, id DESC)` where rank is `1`. |
| `W` | window row set | Rows in `R` where `portfolio_id = P` and `D0 <= cashflow_date <= D1`. |
| `G` | bucket key | `(classification, timing, currency, is_position_flow, is_portfolio_flow)`. |
| `A_g` | `total_amount` | Sum of signed `amount` values for rows in bucket `g`. |
| `N_g` | `cashflow_count` | Count of rows in bucket `g`. |
| `T_g` | bucket evidence timestamp | Maximum `updated_at` for rows in bucket `g`. |
| `T_latest` | `latest_evidence_timestamp` | Maximum `T_g` across all buckets. |

## Methodology and Formulas

Latest row selection:

`R = row_number(partition by transaction_id order by epoch desc, id desc) = 1`

Window selection:

`W = {r in R where r.portfolio_id = P and D0 <= r.cashflow_date <= D1}`

Bucket total:

`A_g = sum(r.amount for r in W where key(r) = g)`

Bucket count:

`N_g = count(r for r in W where key(r) = g)`

Movement direction:

`movement_direction_g = INFLOW if A_g > 0; OUTFLOW if A_g < 0; FLAT if A_g = 0`

Response cashflow count:

`cashflow_count = sum(N_g for all g)`

Latest evidence timestamp:

`T_latest = max(T_g for all g)`; null when `W` is empty.

## Step-by-Step Computation

1. Verify `portfolio_id` exists in `portfolios`. If not, return `404`.
2. Reject requests where `start_date > end_date`.
3. Build the latest cashflow row set by ranking rows within each `transaction_id` by
   `(epoch DESC, id DESC)` and keeping rank `1`.
4. Filter latest rows to `portfolio_id` and the inclusive `cashflow_date` window.
5. Group rows by `(classification, timing, currency, is_position_flow, is_portfolio_flow)`.
6. Calculate `cashflow_count`, `total_amount`, `movement_direction`, and bucket evidence timestamp
   for each group.
7. Sort buckets by classification, timing, currency, portfolio-flow flag descending, and
   position-flow flag descending.
8. Set response `cashflow_count` to the sum of bucket counts.
9. Set `latest_evidence_timestamp` to the latest bucket timestamp, or null when no bucket exists.
10. Set `data_quality_status` to `COMPLETE` when at least one row is included and `MISSING` when
    the portfolio exists but no latest cashflow rows are present in the requested window.
11. Set `as_of_date` to `end_date`.
12. Set `source_batch_fingerprint` to
    `cash_movement_summary:{portfolio_id}:{start_date}:{end_date}`.

## Validation and Failure Behavior

| Case | Behavior |
| --- | --- |
| Missing portfolio | Return `404`; do not fabricate an empty source product. |
| `start_date > end_date` | Return `400`; do not infer or swap dates. |
| Existing portfolio with no cashflow rows in window | Return `buckets=[]`, `cashflow_count=0`, `data_quality_status=MISSING`, and null `latest_evidence_timestamp`. |
| Multiple epochs for one transaction | Use only the latest row by `(epoch DESC, id DESC)`. |
| Same epoch with multiple rows for one transaction | Use the row with highest `id`. |
| Mixed currencies | Keep separate buckets by `currency`; do not convert or restate. |
| Zero bucket total | Return `movement_direction=FLAT`; do not suppress the bucket. |

## Configuration Options

No runtime policy changes the computation. The caller controls only:

| Option | Effect |
| --- | --- |
| `start_date` | Inclusive lower bound for `cashflow_date`. |
| `end_date` | Inclusive upper bound for `cashflow_date` and response `as_of_date`. |

## Outputs

| Response field | Mapping |
| --- | --- |
| `product_name` | Fixed `PortfolioCashMovementSummary`. |
| `product_version` | Fixed `v1`. |
| `portfolio_id` | Request portfolio id. |
| `start_date` | Request window start. |
| `end_date` | Request window end. |
| `buckets[].classification` | Bucket `classification`. |
| `buckets[].timing` | Bucket `timing`. |
| `buckets[].currency` | Bucket `currency`. |
| `buckets[].is_position_flow` | Bucket position-flow flag. |
| `buckets[].is_portfolio_flow` | Bucket portfolio-flow flag. |
| `buckets[].cashflow_count` | `N_g`. |
| `buckets[].total_amount` | `A_g`. |
| `buckets[].movement_direction` | Direction rule from `A_g`. |
| `cashflow_count` | Sum of all bucket counts. |
| `data_quality_status` | `COMPLETE` when rows exist; otherwise `MISSING`. |
| `latest_evidence_timestamp` | `T_latest`. |
| `source_batch_fingerprint` | Deterministic request fingerprint. |

## Worked Example

Input latest rows for `portfolio_id=P1`, `start_date=2026-03-01`, and `end_date=2026-03-31`:

| transaction_id | epoch | id | cashflow_date | classification | timing | currency | amount | is_position_flow | is_portfolio_flow | updated_at |
| --- | ---: | ---: | --- | --- | --- | --- | ---: | --- | --- | --- |
| `T1` | 1 | 11 | 2026-03-05 | `CASHFLOW_IN` | `SETTLED` | `USD` | 10000 | false | true | 2026-03-05T10:00:00Z |
| `T2` | 0 | 12 | 2026-03-06 | `CASHFLOW_OUT` | `SETTLED` | `USD` | -2500 | false | true | 2026-03-06T10:00:00Z |
| `T3` | 0 | 13 | 2026-03-07 | `TRADE_SETTLEMENT` | `SETTLED` | `USD` | -1250 | true | false | 2026-03-07T10:00:00Z |
| `T4` | 0 | 14 | 2026-03-08 | `FEE` | `SETTLED` | `USD` | 0 | false | true | 2026-03-08T10:00:00Z |

Intermediate bucket calculations:

| Bucket key | Formula | `total_amount` | `cashflow_count` | `movement_direction` |
| --- | --- | ---: | ---: | --- |
| `CASHFLOW_IN, SETTLED, USD, false, true` | `10000` | 10000 | 1 | `INFLOW` |
| `CASHFLOW_OUT, SETTLED, USD, false, true` | `-2500` | -2500 | 1 | `OUTFLOW` |
| `FEE, SETTLED, USD, false, true` | `0` | 0 | 1 | `FLAT` |
| `TRADE_SETTLEMENT, SETTLED, USD, true, false` | `-1250` | -1250 | 1 | `OUTFLOW` |

Final response mapping:

| Field | Value |
| --- | --- |
| `cashflow_count` | `1 + 1 + 1 + 1 = 4` |
| `latest_evidence_timestamp` | `2026-03-08T10:00:00Z` |
| `data_quality_status` | `COMPLETE` |
| `source_batch_fingerprint` | `cash_movement_summary:P1:2026-03-01:2026-03-31` |

The method does not infer funding need, liquidity advice, tax result, execution quality, client
suitability, or OMS acknowledgement from these rows.
