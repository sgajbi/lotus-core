# Transaction Ledger Window Methodology

## Metric

`TransactionLedgerWindow:v1` is the core-owned operational transaction-ledger product exposed by
`GET /portfolios/{portfolio_id}/transactions` and the exact-record projection
`GET /portfolios/{portfolio_id}/transactions/{transaction_id}`.

It returns governed booked transaction rows for one portfolio with source-data product identity,
runtime metadata, optional filters, offset pagination, linked cost/cashflow evidence, and
optional reporting-currency restatement fields. The product is source evidence for row-level
portfolio activity, including explicit FX-leg realized P&L fields when upstream transaction
processing supplies them. It is not a tax methodology, FX attribution methodology, cash-movement
aggregation methodology, transaction-cost curve methodology, execution-quality assessment, OMS
acknowledgement, or client advice output.

## Endpoint and Mode Coverage

| Mode | Request shape | Implemented behavior |
| --- | --- | --- |
| Default booked ledger | No `as_of_date`, `include_projected=false` | Resolves `as_of_date` to the latest business date when available, otherwise the current application date. Returns rows with `transaction_date <= as_of_date`. |
| Explicit as-of ledger | `as_of_date=<date>` | Returns rows with `transaction_date <= as_of_date`. |
| Projected-inclusive ledger | `include_projected=true` | Does not apply the default business-date cap when `as_of_date` is omitted, allowing future-dated projected rows that match the other filters. |
| Reporting-currency restated ledger | `reporting_currency=<ccy>` with an effective `as_of_date` | Adds reporting-currency monetary fields by applying the latest available FX rate on or before the effective `as_of_date`. Raw ledger monetary fields, including explicit FX realized-P&L fields, remain unchanged. |
| Exact record rehydration | `/{transaction_id}` with the portfolio path boundary | Returns one canonical record and the same material-input proof metadata. Both identities are applied in SQL; an absent record and a record owned by another portfolio return the same `404`. No ledger page scan is performed. |

## Inputs

| Input | Source | Required | Meaning |
| --- | --- | --- | --- |
| `portfolio_id` | Path parameter | Yes | Portfolio whose transaction ledger is queried. |
| `transaction_id` | Exact-record path parameter | Exact route only | Source-owned record identity, always combined with `portfolio_id`. |
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
| `portfolios` | `portfolio_id` | The collection route validates portfolio existence. The exact route avoids a separate existence probe so absent and wrong-portfolio records are indistinguishable. |
| `business_dates` | `date`, `calendar_code` | Supplies the default `as_of_date` when the caller omits it and `include_projected=false`. |
| `transactions` | transaction identity, dates, type, instrument/security ids, quantities, prices, monetary fields, FX fields, linked-event fields, source fields, and `updated_at` | Rows must match the requested portfolio and filters. Date filters use `transaction_date`. |
| `transaction_costs` | `fee_type`, `amount`, `currency` | Joined as row-level cost evidence and returned without aggregation. |
| `cashflows` | cashflow row fields linked to the transaction | Joined as row-level linked cashflow evidence when present. |
| `fx_rates` | `from_currency`, `to_currency`, `rate_date`, `rate` | Used only for optional reporting-currency restatement fields. |
| `instruments` | `security_id` and instrument master context | Returned row security ids are checked against this governed reference source. Missing matches degrade the response to partial supportability. Cost-calculator product transaction processing also requires this reference before cost fields and processed events are produced. |

## Unit Conventions

Raw monetary fields remain in the transaction row currency conventions already stored on the
ledger row. The response does not convert or overwrite raw ledger values.

When `reporting_currency` is supplied and an effective `as_of_date` exists, the service applies the
latest FX rate with `rate_date <= as_of_date` from the source currency of each monetary field to the
requested reporting currency and populates only the `*_reporting_currency` fields. Same-currency
restatement uses a rate of `1`.

The route restates only row-level fields that already exist on the transaction record. Book-currency
fields use `currency` as the source currency: `gross_transaction_amount`, `gross_cost`, `net_cost`,
`realized_gain_loss`, `withholding_tax_amount`, `other_interest_deductions_amount`, and
`net_interest_amount`. Trade/local fields use `trade_currency` when populated and otherwise fall
back to `currency`: `trade_fee`, `realized_capital_pnl_local`, `realized_fx_pnl_local`, and
`realized_total_pnl_local`.

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
| `G` | `reason_codes[]` | Bounded supportability reason codes for empty, paged, complete, or missing-instrument-reference ledger windows. |
| `U` | `missing_instrument_security_ids[]` | Returned transaction security ids that do not resolve to governed `instruments.security_id`. |
| `X_book` | reporting FX rate for book-currency fields | Latest FX rate from `currency` to reporting currency on or before `A`. |
| `X_trade` | reporting FX rate for trade/local fields | Latest FX rate from `trade_currency` to reporting currency on or before `A`, falling back to `currency` when `trade_currency` is absent. |
| `FX_local` | `realized_fx_pnl_local` | Upstream-supplied row-level realized FX P&L in the transaction row currency. |
| `FX_report` | `realized_fx_pnl_local_reporting_currency` | Optional reporting-currency restatement of `FX_local`; this is not portfolio-level FX attribution. |
| `H_txn` | transaction evidence digest | SHA-256 digest of the ordered, material persisted fields for every transaction in `M`. |
| `H_cost` | cost evidence digest | SHA-256 digest of the ordered transaction-cost rows owned by transactions in `M`. |
| `H_cash` | selected cashflow evidence digest | SHA-256 digest of the latest cashflow per transaction in `M`, selected by `epoch DESC, id DESC`. |
| `H_fx` | selected FX evidence digest | SHA-256 digest of the latest applicable reporting FX row per distinct normalized source currency, selected on or before `A` by `rate_date DESC, id DESC`. Same-currency conversion contributes no persisted FX row. |

## Methodology and Formulas

The matching row set is:

`M = rows where portfolio_id = P and all requested filters F match`

For exact rehydration, `F` includes `transaction_id = T`. The migrated
`ix_transactions_portfolio_transaction_id` index binds both identity predicates in one access path.

Date filters are applied as:

`transaction_date >= start_of_day(S)` when `S` is supplied

`transaction_date < start_of_next_day(E)` when `E` is supplied

`transaction_date < start_of_next_day(A)` when an effective `A` is supplied

Returned-row instrument reference support is:

`U = distinct returned security ids R.security_id where no instruments.security_id match exists`

Reporting-currency fields are computed independently for each populated raw monetary field:

`book_amount_reporting_currency = book_amount * X_book`

`trade_or_local_amount_reporting_currency = trade_or_local_amount * X_trade`

For explicit realized FX P&L local evidence:

`FX_report = FX_local * X_trade`

The raw amount remains unchanged. The product does not derive cross-row measures from the returned
page.

The reconstruction identity binds the complete filtered input scope, not the returned page:

`scope_id = SHA-256(P, A, F, N, latest_material_evidence_at, H_txn, H_cost, H_cash, H_fx, current)`

Each input-family digest is reduced in PostgreSQL in deterministic row order. PostgreSQL hashes
each canonical material row first and then hashes the ordered fixed-width row digests, so the
application receives one bounded value per family rather than assembling or transferring the
complete ledger. `skip`, `limit`, sort order, and returned page rows are deliberately excluded.
Updates to unrelated portfolios, superseded cashflow epochs, unused FX pairs, or FX rows outside
the selected as-of rule therefore do not change the identity.

Before JSONB row construction, every `timestamptz` value is formatted as fixed-width UTC ISO text
with microseconds and a `Z` suffix, and every `date` value is formatted as `YYYY-MM-DD`. Digest
identity is therefore independent of the PostgreSQL connection's `TimeZone` and `DateStyle`.

Evidence selection and reporting conversion use the same normalized-pair ordering:
`rate_date DESC, id DESC`. The `id` tie-breaker is required for legacy case variants that the
raw-string uniqueness constraint can hold on the same date; the selected conversion row and the row
bound into `H_fx` cannot diverge.

Before the first repository read, the request establishes one PostgreSQL
`REPEATABLE READ, READ ONLY` transaction snapshot. Portfolio/as-of resolution, material-input
evidence, page rows, instrument-reference checks, and reporting-FX conversion all use that snapshot.
A correction committed while a request is in flight is therefore visible either to the complete
request or to the next request, never to only the page or only its reconstruction evidence.

## Step-by-Step Computation

1. Establish one repeatable, read-only database snapshot before any source read.
2. Verify the portfolio exists inside that snapshot.
3. Resolve the effective `A`: use request `as_of_date` when supplied; otherwise, if
   `include_projected=false`, use the latest business date for the default business calendar or
   the current application date when no business date exists; otherwise leave `A` unset.
4. Build the transaction ledger filter set from portfolio, instrument/security, transaction type,
   FX component, linked group, FX contract, swap event, near-leg, far-leg, start date, end date,
   and effective as-of date.
5. In one database statement, count all matching rows and reduce the complete matching
   transaction, owned cost, selected latest-cashflow, and selected reporting-FX inputs into
   deterministic fixed-width evidence digests and a latest material evidence timestamp.
6. Derive the page-invariant reconstruction scope identity from the filter scope and those
   material-input digests.
7. Query the requested page with eager row-level `cashflow` and `transaction_costs` evidence.
8. Sort by the requested allowed field and direction; when no allowed field is supplied, sort by
   `transaction_date` descending.
9. Resolve distinct returned row security ids against `instruments.security_id` and retain any
   missing ids as `missing_instrument_security_ids`.
10. Convert each row into `TransactionRecord`, preserving row-level cost records and linked cashflow
   records when present.
11. If `reporting_currency` is supplied and `A` exists, populate supported
   `*_reporting_currency` fields using the latest FX rate on or before `A`; book-currency fields
   use `currency`, and trade/local fields use `trade_currency` when available, including explicit
   row-level `realized_*_pnl_local` fields.
12. Compute `data_quality_status` and `reason_codes` from `total`, returned row count, `skip`, and
    missing instrument-reference evidence.
13. Return source-data runtime metadata including product identity, version, effective as-of date,
    latest evidence timestamp, reconciliation status, restatement version, data-quality status, and
    bounded supportability reason fields.

## Validation and Failure Behavior

| Condition | Behavior |
| --- | --- |
| Portfolio id does not exist | Service raises `LookupError`; the API maps it to HTTP `404`. |
| Exact transaction is absent, outside the as-of boundary, or owned by another portfolio | Returns the same generic HTTP `404`; the route does not disclose which condition applied. |
| Exact source query raises a database error | Maps to HTTP `503`; it is never rewritten as not-found. |
| Exact identity evidence is not zero-or-one | Fails closed as unavailable; no arbitrary row is selected. |
| Caller supplies an invalid `reporting_currency` code | Validation fails before source access; the API maps it to HTTP `400`. |
| Collection route requests restatement but no FX rate exists for a required field source currency as of `A` | Service raises `ValueError`; the collection API maps it to HTTP `400`. |
| Exact route cannot map persisted transaction evidence or resolve a required authoritative FX rate | Fails closed as source unavailable and maps to HTTP `503`; persisted evidence failures are not attributed to the caller. |
| No rows match the filters | Returns an empty page with `total=0` and `data_quality_status=UNKNOWN`. |
| Returned page is smaller than all matching rows or `skip > 0` | Returns `data_quality_status=PARTIAL`. |
| Any returned row `security_id` does not resolve to `instruments.security_id` | Returns `data_quality_status=PARTIAL`, reason `TRANSACTION_LEDGER_INSTRUMENT_REFERENCE_MISSING`, and the bounded missing security ids. |
| Returned page contains all matching rows from offset zero | Returns `data_quality_status=COMPLETE`. |
| `sort_by` is not in the allowed sort-field set | Falls back to `transaction_date`. |
| Row-level `transaction_costs` exist | Returned as `costs[]`; this endpoint does not aggregate them into cost curves. |
| Row-level linked `cashflow` exists | Returned as `cashflow`; this endpoint does not aggregate it into operational cashflow methodology. |
| Product transaction reaches cost processing before instrument master data is available | Cost consumer defers processing as a retryable reference-data dependency; it does not write calculated costs or emit processed transaction evidence. |
| PostgreSQL session `TimeZone` or `DateStyle` differs across readers | Temporal evidence is canonicalized to UTC/ISO before hashing; the reconstruction scope id is unchanged for identical persisted rows. |

## Configuration Options

| Option | Current value |
| --- | --- |
| Default sort field | `transaction_date` |
| Default sort order | `desc` |
| Allowed sort fields | `transaction_date`, `settlement_date`, `quantity`, `price`, `gross_transaction_amount` |
| Default business calendar | `DEFAULT_BUSINESS_CALENDAR_CODE` |
| Exact lookup index | `ix_transactions_portfolio_transaction_id (portfolio_id, transaction_id)` |
| Product identity | `TransactionLedgerWindow:v1` |

## Outputs

| Field | Methodology mapping |
| --- | --- |
| `product_name`, `product_version` | Governed source-data product identity. |
| `portfolio_id` | Requested portfolio. |
| `reporting_currency` | Requested reporting currency, if supplied. |
| `total`, `skip`, `limit` | Matching row count and page controls. |
| `transactions[]` | Row-level transaction evidence after filters, sorting, and pagination. |
| `transaction` | Exact-route canonical transaction record; uses the same DTO and proof semantics as a ledger row. |
| `transactions[].costs[]` | Joined explicit transaction-cost rows without aggregation. |
| `transactions[].cashflow` | Joined linked cashflow row when present. |
| `*_reporting_currency` fields | Optional row-level restatement into requested reporting currency. |
| `transactions[].realized_fx_pnl_local_reporting_currency` | Optional restatement of upstream-supplied row-level realized FX P&L evidence; not an FX attribution measure. |
| `as_of_date` | Effective booked-state cap or fallback output date. |
| `data_quality_status` | Page completeness posture for the returned ledger window. |
| `reason_codes[]` | `TRANSACTION_LEDGER_READY`, `TRANSACTION_LEDGER_EMPTY`, `TRANSACTION_LEDGER_PAGE_PARTIAL`, or `TRANSACTION_LEDGER_INSTRUMENT_REFERENCE_MISSING`. |
| `missing_instrument_reference_count` | Count of returned security ids without governed instrument master support. |
| `missing_instrument_security_ids[]` | Returned security ids that do not resolve to `instruments.security_id`. |
| `latest_evidence_timestamp` | Latest selected durable `updated_at` timestamp across matching transactions, their costs, their selected latest cashflows, and applicable selected FX rates. |
| `source_lineage.reconstruction.scope_id` | Page-invariant identity of the complete filtered material-input scope; changes when selected transaction, cost, cashflow, or reporting-FX economics change. |

## Worked Example

Request:

`GET /portfolios/P1/transactions?as_of_date=2026-03-10&reporting_currency=SGD&limit=10`

Source facts:

| Row | Raw field | Raw amount | Currency | FX rate to SGD | Restated field | Restated amount |
| --- | --- | ---: | --- | ---: | --- | ---: |
| T1 | `trade_fee` | 12.50 | EUR | 1.50 | `trade_fee_reporting_currency` | 18.75 |
| T1 | `realized_gain_loss` | 250.00 | USD | 1.36 | `realized_gain_loss_reporting_currency` | 340.00 |
| T1 | `realized_fx_pnl_local` | 1250.00 | EUR | 1.50 | `realized_fx_pnl_local_reporting_currency` | 1875.00 |
| T2 | `withholding_tax_amount` | 10.00 | USD | 1.36 | `withholding_tax_amount_reporting_currency` | 13.60 |
| T2 | `net_interest_amount` | 110.00 | USD | 1.36 | `net_interest_amount_reporting_currency` | 149.60 |

Final output mapping:

| Response field | Value |
| --- | ---: |
| `total` | 2 |
| `data_quality_status` | `COMPLETE` |
| `reason_codes` | `["TRANSACTION_LEDGER_READY"]` |
| `missing_instrument_reference_count` | 0 |
| `transactions[0].trade_fee_reporting_currency` | 18.75 |
| `transactions[0].realized_fx_pnl_local_reporting_currency` | 1875.00 |
| `transactions[1].withholding_tax_amount_reporting_currency` | 13.60 |
