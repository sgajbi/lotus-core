# CR-1660: Bounded Transaction Cost Hydration

## Scope

This review closes GitHub issue #509 across the paginated Query Service transaction ledger and the
adjacent Query Control Plane transaction-economics readers. It changes collection-loading strategy
only; transaction selection, ordering, filters, response contracts, and financial values remain
unchanged.

## Findings

- `TransactionRepository.get_transactions` joined the one-to-many `transaction_costs` collection
  into the offset/limit statement. SQLAlchemy protected entity cardinality through query rewriting,
  but the database still transferred and de-duplicated one row per transaction/cost combination.
- The Query Control Plane transaction-cost evidence reader used the same joined collection pattern.
- Its cursor-limited performance-component reader also joined costs into the bounded transaction
  page, reproducing the named defect beyond the original Query Service call site.
- The one-to-one cashflow relationship does not create collection fan-out and remains joined where
  it forms part of the selected row contract.

## Resolution

- Replaced joined collection loading with a correlated `LATERAL` cost aggregate in all three
  transaction-economics reads.
- Each selected transaction now carries deterministically ordered, aligned cost columns in the same
  PostgreSQL statement snapshot. The query retains one row per transaction, so offset/limit and
  cursor limits apply before any collection-row multiplication.
- A late review correctly identified that the initial two-statement `selectinload` implementation
  could combine parent and cost versions across `READ COMMITTED` snapshots. The single-statement
  aggregate closes that race without widening transaction isolation or changing session ownership.
- Aggregate reconstruction fails closed if fee, amount, currency, or timestamp columns are not
  aligned.
- Preserved the existing stable sort fields, filters, page size, cashflow selection, result mapping,
  and serialized contracts.

This is an internal infrastructure-adapter optimization. It does not change runtime topology or
introduce a new service boundary.

## Evidence

- GitHub and local Git both verify the branch commits as signed.
- 23 warning-strict Query Service repository tests passed.
- 10 warning-strict Query Control Plane transaction-economics source tests passed, plus focused
  aggregate reconstruction proof.
- Real PostgreSQL proof seeded three transactions with one, two, and three cost rows. A two-row
  page returned exactly the newest two transactions with all five applicable costs in exactly one
  `SELECT`, retained one SQL row per transaction through `LATERAL` aggregation, and bounded the
  result to the selected two-row page.
- Strict MyPy passed across 240 source files; scoped Ruff, format, and diff-hygiene checks passed.

## Compatibility and remaining batch work

Public API, OpenAPI, event, database schema, migration, transaction ordering, filters, financial
results, and downstream payloads are unchanged. Issue #506 separately owns replacement of offset
pagination; this slice deliberately establishes bounded collection hydration before cursor
semantics change. Issues #503–#508 and #510–#511 remain independent work in the same database
hot-path scalability batch.

## Documentation, wiki, context, and skill decision

The codebase review ledger is the only durable documentation surface changed. No operator command,
business methodology, API contract, database migration procedure, repository workflow, or wiki
flow changed, so README, deep product docs, repository context, central context, and wiki source
remain unchanged. The existing backend-delivery and review-ledger skills already require
same-pattern scanning and database-backed proof; no skill or routing change is justified.
