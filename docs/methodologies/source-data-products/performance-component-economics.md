# PerformanceComponentEconomics Methodology

## Product Identity

- Product: `PerformanceComponentEconomics:v1`
- Route: `POST /integration/portfolios/{portfolio_id}/performance-component-economics`
- Owner: `lotus-core`
- Primary consumer: `lotus-performance`
- Boundary: source-authored economics evidence only. `lotus-performance` owns contribution,
  attribution, and return methodology.
- Authority: the admitted tenant scopes every portfolio and transaction read. An optional body
  `tenant_id` is an assertion only and must match that authority.

## Inputs

The product establishes a repeatable-read, read-only snapshot before its first database operation,
including portfolio admission and currency lookup. It then resolves the portfolio within the
admitted tenant and reads
`transactions` for that portfolio, inclusive transaction-date
window, and `as_of_date` bound. Optional `security_ids` and `transaction_types` narrow the source
rows. The inclusive transaction-date window remains capped at 366 days. It joins
`transaction_costs` and the latest `cashflows` epoch for each transaction. The row-level evidence
response is cursor-paged with `page.page_size + 1` budgeting. Source-cut capture loads the entire
matching window once in the same snapshot; page reads reuse that captured evidence. The 366-day
date bound is not a row-count or production-volume certification.

## Deterministic Row Selection

Rows are selected when:

1. the joined `portfolios.tenant_id` equals the admitted tenant,
2. `transactions.portfolio_id` equals the requested portfolio,
3. `transaction_date >= window.start_date`,
4. `transaction_date <= window.end_date`,
5. `transaction_date <= as_of_date`,
6. the inclusive request window is 366 days or less,
7. optional security and transaction-type filters match after canonical normalization.

Rows are ordered by normalized `security_id`, transaction date, and `transaction_id`. Linked
cashflows are selected deterministically by highest `cashflows.epoch`, then highest `cashflows.id`.

## Paging

The request accepts optional cursor paging controls through `page.page_size` and
`page.page_token`. Page tokens are scoped to the full request fingerprint, including portfolio,
window, `as_of_date`, filters, and the admitted tenant. They also bind the material
`source_cut_sha256` for the entire matching window, including qualified source/revision evidence,
companion values and portfolio base currency. Tokens from another tenant, request scope or source
cut, and legacy unbound tokens, are rejected with HTTP 400 by the query control plane.

After whole-window capture, repository page reads request `page_size + 1` ordered rows to determine
`has_more`; they do not issue a second independently timed evidence read. A confirmation outside
the returned page can change the cut even when returned rows and their latest timestamp do not.
The next HTTP request establishes a fresh snapshot and refuses the old token if that cut changed;
it does not retain a database snapshot across HTTP requests. Response `page.sort_key` is
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

For applicable historical FX, stored zero is not independent original-source evidence. The product
requires exactly one retained `RawTransactionPersisted` outbox payload for the selected transaction,
owned by the admitted portfolio tenant, matching the ledger source identifiers, mode, component
and stored economic fingerprint. The strict shared calculation-lineage decoder must accept the
retained version-1 or version-2 FX baseline receipt, governed numeric policy and complete persisted
output binding. Version 2 additionally binds all six original capital/FX/total local/base
presence/value pairs before normalization through `fx-original-pnl-presence@2`; explicit zero and
absence remain distinct without changing original financial results. Raw v1 transport can omit
tenant; the persisted joined portfolio supplies authority, not
caller body metadata. An explicit conflicting raw tenant is refused.

| Original authority | Row FX amounts | Row reason |
| --- | --- | --- |
| Qualified explicit zero, positive or negative amounts | Exact independently supplied amounts | `FX_SOURCE_QUALIFIED` |
| Qualified source missing one or both bases | Missing basis remains null; known basis retained | `FX_SOURCE_INCOMPLETE` |
| Missing, duplicate, foreign, mismatched raw evidence or absent/tampered receipt | Both null | `FX_SOURCE_AUTHORITY_UNAVAILABLE` |
| Explicit `NONE` mode or non-realizing `FX_CONTRACT_OPEN` | Zero, without claiming upstream P&L presence | `FX_SOURCE_NOT_APPLICABLE` |

For applicable FX, QCP consumes the common `TransactionSourceEvidence` contract with
`consumer=core-qcp` and current selection: a completely qualified linked current revision supplies
zero only for a genuinely absent approved basis; without a revision it uses retained original
authority. The common reader independently verifies tenant/portfolio/transaction ownership, raw
root, immutable revision hash, signed intent and complete receipt. Ambiguous, tampered, unknown or
foreign authority is unavailable, never inferred from normalized stored amounts. Row
`transaction_source_evidence` records the selection/status, producer version, qualified root,
revision ID/hash and confirmation time without exposing raw/auth payloads.

QCP does not accept original/revision selectors in this product request. The existing exact ledger
route `GET /portfolios/{portfolio_id}/transactions/{transaction_id}` supplies those inspection
controls through the same qualification contract:

| Ledger selection | Query parameters | Authority |
| --- | --- | --- |
| Current (default) | `source_evidence_selection=current` | Qualified current revision, or original when no revision exists. |
| Original | `source_evidence_selection=original` | Immutable original raw/output/receipt only; revision/intent/operation metadata does not enter its cut. |
| Explicit revision | `source_evidence_selection=revision&source_revision_id=<owned-revision-id>` | Exact owned revision; unknown or foreign identity is indistinguishable from absence. |

Only explicit revision selection requires a revision ID. Original records remain equal across
confirmation except volatile generation time. Current/explicit records may qualify an absent FX
basis as zero while preserving signed companions, original capital/total identities and immutable
financial/raw/receipt rows. Confirmation time is not the transaction financial date and does not
retroactively restate the booked row.

Legacy pre-upstream fingerprints can identify retained immutable raw evidence but cannot recreate
omitted P&L from a normalized receipt or stored zero. Missing authority is never backfilled during
a read. Non-FX behavior is unchanged. Local/base total P&L is withheld independently when the
corresponding applicable FX basis is unknown, even if a stored total exists.
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

Independently qualified FX zero also contributes evidence. Any included unknown base amount makes
that component total null; `evidence_count` counts known contributors and `missing_evidence_count`
counts unavailable contributors. A mixed known/unknown total must not expose the known subtotal as
the complete amount. FX and total families can remain missing even when another row observes them.

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
| `rows[*].transaction_source_evidence` | Common independently qualified current source proof, original presence and selected immutable revision identity for applicable FX. |
| `component_totals` and `component_totals_scope` | Core response policy derived from the returned page only. |
| `supportability` and `data_quality_status` | Core source-evidence policy derived from returned rows and paging state. |
| `page`, `request_fingerprint`, runtime source-data metadata, and top-level `lineage` | QCP response-envelope metadata derived by Core assembly policy. `content_hash`, `source_digest`, and `source_batch_fingerprint` are the same deterministic SHA-256 value and exclude volatile `generated_at`. |
| `source_cut_sha256` | Material authority for the whole matching snapshot window and base currency, not just returned rows or the latest timestamp. This cut also enters the deterministic response content hash. |

## Supportability

`READY` with reason `PERFORMANCE_COMPONENT_ECONOMICS_READY` means at least one source row was
returned, no additional page is indicated, and applicable FX evidence is qualified. `READY` with reason
`PERFORMANCE_COMPONENT_ECONOMICS_NO_ACTIVITY` means Core proved the portfolio and base-currency
authority, successfully queried the initial page of the complete bounded request scope, and found no
matching activity. That authoritative empty result has `source_row_count=0`, `rows=[]`, no observed
families, no missing families, `data_quality_status=COMPLETE`, `source_evidence_current=true`, and
`freshness_status=CURRENT`. `latest_evidence_timestamp` remains null because there is no source row;
`generated_at` is captured after Core completes the authoritative scope query. The result is not
evidence that every component amount was zero.

`DEGRADED` with reason `PERFORMANCE_COMPONENT_ECONOMICS_PAGE_PARTIAL` means the current response is
a valid partial page and `page.next_page_token` must be followed to exhaust the requested window.
Otherwise incomplete applicable FX yields `DEGRADED`, reason
`PERFORMANCE_COMPONENT_ECONOMICS_FX_SOURCE_INCOMPLETE` and `data_quality_status=PARTIAL`.
An unexpectedly empty continuation page is `UNAVAILABLE` with reason
`PERFORMANCE_COMPONENT_ECONOMICS_PAGE_EVIDENCE_CHANGED`, `data_quality_status=UNKNOWN`, and all
supported families missing. A continuation can prove only the suffix after its cursor, not that the
complete bounded request scope had no activity; concurrent source changes therefore fail closed.
Snapshot setup failure or a late/already-active database transaction also refuses before authority
is returned. `latest_evidence_timestamp` is descriptive freshness metadata, not source-cut proof.
Missing and foreign portfolios share the same not-found response. Missing admission fails at shared
ingress; a blank or mismatched body tenant assertion returns HTTP 403 before service or database
work. Invalid request or cursor scopes fail closed through the documented HTTP problem contract.
Persistence/query failures remain errors; Core does not convert an unproved scope into
`READY / PERFORMANCE_COMPONENT_ECONOMICS_NO_ACTIVITY`.

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

## Source Selection And Continuation Examples

These requests use safe placeholders and require the existing verified tenant/service admission;
an `X-Tenant-Id` header alone is not authorization. Ledger selection examples describe the actual
route/query contract, not a new QCP input field or a live-enrollment proof:

```text
GET /portfolios/<owned-portfolio>/transactions/<owned-transaction>?source_evidence_selection=current
GET /portfolios/<owned-portfolio>/transactions/<owned-transaction>?source_evidence_selection=original
GET /portfolios/<owned-portfolio>/transactions/<owned-transaction>?source_evidence_selection=revision&source_revision_id=<owned-revision-id>
```

For QCP, the existing POST route accepts a current-evidence request such as:

```json
{
  "as_of_date": "2026-04-10",
  "window": {"start_date": "2026-04-01", "end_date": "2026-04-10"},
  "page": {"page_size": 1}
}
```

For a synthetic window containing first row A and later row Z, retain the returned opaque
`page.next_page_token` unchanged in the next request's `page.page_token`. If a qualified source
confirmation changes Z after the first response, the current rows for A may remain identical but
the whole-window source cut changes. The old token then receives HTTP 400
`QCP_SOURCE_EVIDENCE_INVALID_REQUEST`; restart with no token to establish a new cut. Never edit a
token, infer it from a timestamp or combine pages from different cuts as one complete window.

The actual owning PostgreSQL consumer matrix covers genuine version-1/version-2 producers,
zero/+12/-12 companions, independently reloaded QCP/ledger cuts, stale outside-page continuation,
immutable original selection, unknown/foreign revision refusal and late/tampered authority. Its
frozen execution is scoped evidence, not live Kafka or production-volume acceptance. Component
totals remain `returned_page`; qualified zero is evidence, unknown FX withholds its dependent
total, and mixed known/unknown contributors never become an optimistic complete subtotal.

## Explicit Non-Claims

This product is not contribution analytics, attribution analytics, a return calculator, tax advice,
best-execution evidence, venue-routing evidence, OMS acknowledgement, or a performance-ready UI
claim. Downstream `lotus-performance` consumption and proof remain tracked separately.

The read-side qualifier has a rejection-only retained-verification boundary: a strict shared
decoder, exact algorithm/version/working precision and complete numeric-policy identity must
accept the persisted receipt, and its output-binding predicate must accept the same canonical
ledger output before either original source amount is interpreted. The calculated-output policy
guard verifies this predicate-dependent path and preserves helper caller-escape checks. It does
not fabricate a producer receipt, infer original presence or certify database execution.
The guard also qualifies the canonicalizer's input-derived projection shape; a helper that
ignores or remaps its input cannot supply binding authority. Unsupported alias-bearing
assignments are rejected so containers cannot conceal a mutable reference after verification.
Covered amount helpers are also checked for read-only normalized Decimal/None returns, so a
helper cannot conceal an output alias behind an arithmetic callsite registration.

The owning historical FX PostgreSQL proof executes through `make test-query-authority-db-contract`
and `critical-db-coverage` in protected CI. Unit execution and schema documentation do not prove
durable reload, no-mutation, deployment or an actual external downstream consumer. The evidence-only
source-confirmation command and version-2 original-presence producer are described in the
[FX contract](../../rfc-transaction-specs/transactions/FX/FX-SLICE-6-PNL-SEMANTICS.md) and
[ingestion operator guide](../../../wiki/Ingestion-Service.md). They do not rewrite booked
economics, original raw/receipt, replay fences or cash/cost effects. The notification has no
registered external subscriber; Kafka enrollment, downstream qualification, mainline release,
publication and broad issue certification remain separate authority.

Source-confirmation qualification uses detached immutable facts across the application/storage
boundary. Its native adapter carries every ledger column except the four technical fields `id`,
`updated_at`, `payload_fingerprint` and `calculation_lineage`; fingerprint and complete original
receipt are retained separately. Revision material requires every mapped revision column, and
nested evidence cannot change through an ORM or caller alias after projection. This preserves
the same retained-input validation, financial output binding and retry qualification; it is an
internal ownership boundary, not additional consumer or database acceptance evidence.
