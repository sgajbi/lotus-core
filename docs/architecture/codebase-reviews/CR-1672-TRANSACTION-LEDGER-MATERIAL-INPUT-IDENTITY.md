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

## Compatibility

Route paths, query parameters, response schemas, source-product identity, page semantics, raw and
reporting-currency fields, database schema, migrations, topics, groups, and runtime topology are
unchanged. Existing scope identifiers intentionally change when a selected material input changes;
this corrects cache/reconstruction invalidation semantics. Consumers must already treat scope ids
as opaque.

## Same-Pattern Review

The adjacent `HoldingsAsOf`, cash-balance, and `PortfolioStateSnapshot` identity builders already
bind full content/source/calculation evidence and do not share the owning-row/count-only defect.
No additional same-pattern source change was required.

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

## Durable-Truth Decision

The source-product methodology, RFC-0083, review ledger, and transaction-processing wiki source
change because reconstruction truth changed. OpenAPI and migrations do not change because the
public schema and persisted schema are unchanged. No new service, event, topic, group, or
supported-feature declaration is introduced.

## Delivery Status

Implementation is fixed locally in signed commits on
`feat/deterministic-financial-derived-state`. Protected PR CI, exact-main validation, wiki
publication/parity, GitHub closure evidence, and branch/worktree reconciliation remain required.
