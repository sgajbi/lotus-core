# CR-1672 Transaction Ledger Material-Input Identity

## Scope

GitHub issue #865 and the `TransactionLedgerWindow:v1` reconstruction identity.

## Finding

The page-invariant reconstruction scope bound only the matching transaction count and maximum
`transactions.updated_at`. Returned ledger economics also depend on transaction material fields,
owned transaction costs, the latest cashflow selected per transaction, and selected
reporting-currency FX rows. A cost, selected cashflow, or applicable FX correction could therefore
change the response economics without invalidating the existing scope identity.

## Correction

1. Added a typed application evidence contract for the matching row count, latest selected
   material timestamp, and four input-family digests.
2. Added one PostgreSQL evidence statement over the complete filtered transaction CTE.
3. Canonicalized and SHA-256-hashed each material source row in the database, ordered the
   fixed-width row digests deterministically, and reduced each input family to one SHA-256 digest.
4. Bound reconstruction identity to matching transactions, owned costs, latest cashflow selected by
   `epoch DESC, id DESC`, and latest applicable reporting FX selected by source currency and as-of
   date.
5. Excluded pagination, sort controls, unrelated portfolios, superseded cashflow epochs, and
   unselected FX evidence from identity.
6. Removed the obsolete transaction-only latest-evidence repository read and reused the evidence
   count, avoiding a second complete-scope read.
7. A P1 review identified that multiple statements under default `READ COMMITTED` could still mix
   old evidence with corrected page or FX values. The request now establishes
   `REPEATABLE READ, READ ONLY` before its first repository query, covering portfolio/as-of
   resolution, evidence, page rows, instrument checks, and conversion reads.
8. A corrected-head P2 review found that normalized legacy FX-pair variants on one date could make
   evidence select highest `id` while conversion selected an unspecified peer. Conversion now uses
   the identical `rate_date DESC, id DESC` rule. A repository-wide same-pattern review aligned all
   latest-FX readers and made dated FX series/window ordering deterministic by `(rate_date, id)`.

## Compatibility

Route paths, query parameters, response schemas, source-product identity, page semantics, raw and
reporting-currency fields, database schema, migrations, topics, groups, and runtime topology are
unchanged. Existing scope identifiers intentionally change when a selected material input changes;
this corrects cache/reconstruction invalidation semantics. Consumers must already treat scope ids
as opaque.

## Same-Pattern Review

The adjacent `HoldingsAsOf`, cash-balance, and `PortfolioStateSnapshot` identity builders already
bind full content/source/calculation evidence and do not share the owning-row/count-only defect.
The corrected-head FX review exposed the same missing `id` tie-breaker in reporting, reconciliation,
valuation, and timeseries latest-FX readers; these were aligned in scope. Query Service, Query
Control Plane, and transaction-processing FX series/window readers now order by date and id so
same-date legacy variants have stable output order and map reduction. A source scan found no
remaining `FxRate` ordering that uses `rate_date` alone.

## Validation

1. Focused unit cohorts: 87 tests passed.
2. Repository unit cohort: 23 tests passed.
3. Real PostgreSQL material-input isolation proof passed, covering transaction, cost, latest
   cashflow, selected FX, unrelated portfolio/FX, superseded cashflow, and one-statement shape.
4. A repository-owned 100,000-transaction capacity proof, with 100,000 owned costs and 100,000
   selected cashflows, passed in 112.55 seconds end to end; the material-input evidence statement
   itself completed in 2.502 seconds and returned only four fixed-width digests plus count/time
   metadata.
5. Scoped Ruff lint/format and MyPy passed before documentation closure.
6. A two-session PostgreSQL regression committed a transaction and FX correction after the evidence
   statement but before the page read. The in-flight response retained one internally consistent
   pre-correction snapshot; the next request observed both corrections and a new scope id.
7. A PostgreSQL legacy-variant regression proved same-date `USD/SGD` and `usd/sgd` rows resolve to
   the same highest-id row for evidence and conversion: changing the unselected row changed neither,
   while changing the selected row changed both the digest and returned rate.

## Durable-Truth Decision

The source-product methodology, RFC-0083, review ledger, and transaction-processing wiki source
change because reconstruction truth changed. OpenAPI and migrations do not change because the
public schema and persisted schema are unchanged. No new service, event, topic, group, or
supported-feature declaration is introduced.

## Delivery Status

Implementation is fixed locally in signed commits on
`feat/deterministic-financial-derived-state`. Protected PR CI, exact-main validation, wiki
publication/parity, GitHub closure evidence, and branch/worktree reconciliation remain required.
