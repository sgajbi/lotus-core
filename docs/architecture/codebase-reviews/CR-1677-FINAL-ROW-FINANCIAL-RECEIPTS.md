# CR-1677: Final-Row Financial Receipts

## Scope

This review covers GitHub issue #878 and the transaction-processing same-pattern scan for receipts
created before conflict resolution and for ambiguous timestamps made artificially timezone-aware
before financial lineage construction.

## Findings

FX booking created a complete persistence-shaped calculation receipt before calling the transaction
upsert. The repository's established partial-update semantics omit incoming `None` values. During
reprocessing, an existing optional database value could therefore survive while the incoming
receipt replaced the old receipt and omitted that retained value. The application then returned
the pre-upsert transaction rather than the accepted durable row.

The same repository mapped database rows through the public transaction event boundary. That
mapper deliberately excludes derived `calculation_lineage` from Kafka contracts, but internal
history, single-row, update, and upsert results consequently lost their persisted receipt too.

The FX lineage canonicalizer attached UTC to naive transaction, settlement, and creation
timestamps. Position-history ordering used the same implicit-UTC pattern before placing its total
ordering key into calculation lineage. Both converted an ambiguous local time into apparently
governed financial evidence.

## Correction

The SQLAlchemy transaction repository now returns the row produced by `INSERT .. ON CONFLICT ..
RETURNING` and reattaches its internal calculation receipt after the public event mapper. FX
booking rebuilds the receipt from that complete row. It performs a second upsert only when conflict
resolution or database defaults changed the persisted output, then verifies that the returned
receipt binds the final durable row. The normal insert/reprocess path with unchanged output retains
one write round trip; existing omitted-field retention semantics and public event contracts remain
unchanged.

FX lineage and position-history ordering now reject naive or otherwise offset-ambiguous datetimes.
Timezone-aware values are converted to UTC before hashing or ordering, so equivalent instants have
one deterministic identity.

## Same-Pattern Review

The scan covered every `on_conflict_do_update`, calculation-lineage builder, and implicit UTC
attachment in `portfolio_transaction_processing_service`.

- Cashflow replacement supplies every persisted calculated output field on conflict; it does not
  have the optional-field omission defect.
- Lot-state and AVCO writers use complete row projections and the exact persisted-output checks
  established by CR-1659; their upserts do not accept a partially merged financial receipt.
- Readiness, income-offset, and reconciliation upserts persist workflow state rather than a
  precomputed financial output receipt.
- Cashflow rule-cache timestamps describe SQL-owned rule-set version metadata and normalize a
  database timestamp; they are not transaction/calculation instants accepted from a financial
  input contract.
- `CostBasisTransaction.standardize_datetime_value` is a distinct, high-fan-out legacy parser
  compatibility contract that accepts strings and naive datetimes before unified transaction
  economics. It is durably assigned to the existing #719 owner; changing it safely requires a
  dedicated input-contract and downstream fixture migration, not an incidental FX edit.

## Compatibility And Documentation

There is no public API, OpenAPI, event, database schema, migration, topic, partition, or runtime
topology change. Timezone-aware transaction inputs remain compatible. Naive FX and position-history
calculation inputs now fail closed intentionally. Repository context and this review ledger change
because the final-row receipt and timestamp-boundary rules are reusable. README and authored wiki
are explicit no-change because no user command, operator workflow, or published capability changed.
The existing delivery, issue-resolution, calculated-output guard, and review-ledger skills already
require these checks, so central platform context and skills are also unchanged.

## Validation

- FX, position-history, cost-repository, cost-processing, and settlement unit cohorts passed;
- the PostgreSQL reprocessing proof retained an omitted optional source value and verified the
  final stored receipt against the complete durable row;
- targeted Ruff, configured MyPy, and diff-hygiene checks passed;
- signed commits: `2006b5c8c`, `81ede2154`, and `65fb51523`.
