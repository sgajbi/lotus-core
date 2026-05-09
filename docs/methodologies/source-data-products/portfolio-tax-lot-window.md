# Portfolio Tax Lot Window Methodology

## Metric

`PortfolioTaxLotWindow:v1` is the core-owned tax-lot and cost-basis evidence product exposed by
`POST /integration/portfolios/{portfolio_id}/tax-lots`.

It returns effective-dated portfolio tax lots for discretionary portfolio management sell decisions.
The product supplies source-owned lot quantity, acquisition date, cost-basis, source transaction,
and calculation-policy lineage. It is not jurisdiction-specific tax advice, realized-tax
optimization, wash-sale treatment, client-tax approval, tax-reporting certification, or execution
methodology.

## Endpoint and Mode Coverage

| Request shape | Implemented behavior |
| --- | --- |
| `portfolio_id` path parameter | Selects the portfolio whose tax-lot state is requested. |
| `as_of_date` | Includes lots acquired on or before the as-of date. |
| optional `security_ids` | Restricts evidence to requested securities and reports missing requested securities as supportability gaps. |
| optional `lot_status_filter=OPEN` | Returns lots with positive open quantity. |
| optional `lot_status_filter=CLOSED` | Returns lots with zero or negative open quantity. |
| `include_closed_lots=false` with no status filter | Returns open lots by default. |
| `include_closed_lots=true` with no status filter | Returns open and closed lots. |
| `page.page_size` / `page.page_token` | Returns deterministic cursor pages ordered by acquisition date and lot id. |

The product currently has one implemented methodology: source lot-state exposure from
`position_lot_state`. It does not switch into tax optimization, tax-loss harvesting, wash-sale, or
jurisdiction-specific advice modes.

## Inputs

| Input | Source | Required | Meaning |
| --- | --- | --- | --- |
| `portfolio_id` | Path parameter | Yes | Portfolio whose tax-lot evidence is returned. |
| `as_of_date` | Request body | Yes | Effective date for lot inclusion. |
| `security_ids` | Request body | No | Optional security filter and supportability coverage expectation. |
| `lot_status_filter` | Request body | No | Optional explicit `OPEN` or `CLOSED` status filter. |
| `include_closed_lots` | Request body | No, default `false` | Includes closed lots only when no explicit status filter is supplied. |
| `tenant_id` | Request body | No | Included in request-scope paging identity. |

## Upstream Data Sources

| Source | Used fields | Inclusion rule |
| --- | --- | --- |
| `portfolios` | `portfolio_id` | Portfolio must exist. |
| `position_lot_state` | `portfolio_id`, `security_id`, `instrument_id`, `lot_id`, `open_quantity`, `original_quantity`, `acquisition_date`, `lot_cost_base`, `lot_cost_local`, `source_transaction_id`, `source_system`, `calculation_policy_id`, `calculation_policy_version`, `updated_at` | Lot must match the portfolio, optional security filter, as-of date, and status filter. |
| `transactions` | `transaction_id`, `trade_currency` | Optional outer join by `source_transaction_id` to populate local lot currency. |

The product preserves lot state already calculated and stored in `position_lot_state`. Cost-basis
fields are preserved, not recalculated, reallocated, or tax-optimized by the endpoint.

## Unit Conventions

`open_quantity` and `original_quantity` use the instrument quantity unit carried by the source lot
state.

`cost_basis_base` uses the portfolio base currency represented by `lot_cost_base`.
`cost_basis_local` uses the local trade currency represented by `lot_cost_local` and
`transactions.trade_currency` when available.

No FX conversion, realized-tax calculation, tax-rate application, loss-harvesting optimization, or
wash-sale adjustment is performed by this product.

## Variable Dictionary

| Symbol | Response or source field | Definition |
| --- | --- | --- |
| `P` | `portfolio_id` | Requested portfolio. |
| `A` | `as_of_date` | Effective lot-state date. |
| `S` | `security_ids` | Optional requested securities. |
| `F` | `lot_status_filter` | Optional explicit lot status filter. |
| `C` | `include_closed_lots` | Closed-lot inclusion flag used only when `F` is omitted. |
| `Q_open` | `open_quantity` | Current open quantity for the lot. |
| `Q_orig` | `original_quantity` | Original acquired quantity for the lot. |
| `CB_base` | `cost_basis_base` | Current lot cost basis in portfolio base currency. |
| `CB_local` | `cost_basis_local` | Current lot cost basis in local trade currency. |
| `Status` | `tax_lot_status` | `OPEN` when `Q_open > 0`, otherwise `CLOSED`. |

## Methodology and Formulas

For every source lot row:

`Status = OPEN if Q_open > 0 else CLOSED`

`cost_basis_base = lot_cost_base`

`cost_basis_local = lot_cost_local`

`local_currency = transactions.trade_currency when the source transaction is available else null`

The endpoint does not calculate unrealized gain, realized gain, tax payable, tax alpha, wash-sale
adjustment, or optimal disposal sequence.

## Step-by-Step Computation

1. Verify that the requested portfolio exists.
2. Build a request-scope fingerprint from portfolio id, as-of date, security filter, lot-status
   filter, closed-lot inclusion flag, and tenant id.
3. Decode and validate the optional page token against the request-scope fingerprint.
4. Build the source query over `position_lot_state` where `portfolio_id=P` and
   `acquisition_date <= A`.
5. Apply `security_ids` when supplied.
6. Apply lot status: `OPEN` filters to `open_quantity > 0`; `CLOSED` filters to
   `open_quantity <= 0`; omitted status with `include_closed_lots=false` returns open lots by
   default; omitted status with `include_closed_lots=true` returns both open and closed lots.
7. Apply cursor continuation by `(acquisition_date, lot_id)` when a valid page token is supplied.
8. Outer join `transactions` by `source_transaction_id` to obtain local currency when available.
9. Sort by `acquisition_date` ascending, then `lot_id` ascending.
10. Fetch `page_size + 1` rows to detect whether the page is partial.
11. Map each returned lot into `PortfolioTaxLotRecord`, preserving source transaction and
    calculation-policy lineage.
12. Emit supportability, pagination metadata, lineage, and source-data product runtime metadata.

## Validation and Failure Behavior

| Condition | Behavior |
| --- | --- |
| Portfolio id does not exist | Service raises `LookupError`; the API maps it to HTTP `404`. |
| Blank or duplicate `security_ids` | Request validation rejects the request. |
| Page token scope does not match the request | Service raises `ValueError`; the API maps it to HTTP `400`. |
| More rows exist than the page size | Response carries supportability `DEGRADED` and reason `TAX_LOTS_PAGE_PARTIAL`. |
| Requested securities have no matching lots in the complete page scope | Response carries supportability `INCOMPLETE` and reason `TAX_LOTS_MISSING_FOR_REQUESTED_SECURITIES`. |
| Full-portfolio request returns no lots | Response carries supportability `UNAVAILABLE`, reason `TAX_LOTS_EMPTY`, and `data_quality_status=MISSING`. |

`data_quality_status` is `COMPLETE` only when supportability is `READY`; it is `MISSING` for
`UNAVAILABLE` and `PARTIAL` for degraded or incomplete responses. This status certifies source
tax-lot evidence availability only, not tax advice or tax optimization.

## Configuration Options

| Option | Current value |
| --- | --- |
| Default page size | `250` tax lots |
| Maximum page size | `1000` tax lots |
| Default status behavior | Open lots only |
| Sort order | `acquisition_date:asc,lot_id:asc` |
| Product identity | `PortfolioTaxLotWindow:v1` |

## Outputs

| Field | Methodology mapping |
| --- | --- |
| `lots[].portfolio_id` | Source lot portfolio id. |
| `lots[].security_id` | Source lot security id. |
| `lots[].instrument_id` | Source lot instrument id. |
| `lots[].lot_id` | Stable source lot id. |
| `lots[].open_quantity` | `Q_open`. |
| `lots[].original_quantity` | `Q_orig`. |
| `lots[].acquisition_date` | Lot acquisition date used for ordering and paging. |
| `lots[].cost_basis_base` | `CB_base`. |
| `lots[].cost_basis_local` | `CB_local`. |
| `lots[].local_currency` | Joined source transaction trade currency when available. |
| `lots[].tax_lot_status` | `Status`. |
| `lots[].source_lineage` | Source system, source transaction id, calculation policy id, and calculation policy version. |
| `supportability` | Readiness state for tax-lot evidence only. |

## Worked Example

Request:

`POST /integration/portfolios/PB_SG_GLOBAL_BAL_001/tax-lots`

```json
{
  "as_of_date": "2026-04-10",
  "security_ids": ["EQ_US_AAPL"],
  "lot_status_filter": "OPEN",
  "page": {"page_size": 250}
}
```

Source facts:

| Lot | Security | Open quantity `Q_open` | Original quantity `Q_orig` | Acquisition date | Base cost `CB_base` | Local cost `CB_local` | Currency |
| --- | --- | ---: | ---: | --- | ---: | ---: | --- |
| `LOT-AAPL-001` | `EQ_US_AAPL` | 100 | 100 | 2026-03-25 | 15005.50 | 15005.50 | USD |

Final output mapping:

| Response field | Value |
| --- | --- |
| `lots[0].lot_id` | `LOT-AAPL-001` |
| `lots[0].tax_lot_status` | `OPEN` |
| `lots[0].cost_basis_base` | `15005.50` |
| `lots[0].cost_basis_local` | `15005.50` |
| `supportability.state` | `READY` |
