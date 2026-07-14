# CR-1587: Booked Transaction Replay Infrastructure Ownership

## Objective

Advance issue #719 by organizing booked-transaction replay infrastructure behind its existing
application port and removing the flat adapter and broad package-root API.

## Finding

`transaction_replay_adapter.py` contained the canonical replayer protocol, SQLAlchemy session
ownership, dependency error mapping, and zero-or-one cardinality invariant as a flat infrastructure
module. Both adapter symbols were re-exported from the broad infrastructure root, and the adapter
test remained at the service test root despite the existing `BookedTransactionReplayPort`.

## Change

1. Added `app/infrastructure/transaction_replay/booked_transaction.py` for canonical publisher
   delegation and replay adaptation.
2. Kept `CanonicalTransactionReplayer` beside the adapter as an infrastructure-only dependency
   protocol rather than leaking shared repository shape into application ports.
3. Composed the package-owned adapter through the existing replay use-case builder.
4. Removed both replay symbols from the broad infrastructure-root API without aliases.
5. Moved adapter tests into a mirrored transaction-replay package and added module/class docstrings.
6. Added a no-return structure guard, application-port catalog entry, and critical-path ownership.
7. Reconciled repository context, consolidation evidence, wiki source, and the review ledger.

## Measurable Improvement

- Removed one capability module from the flat infrastructure root.
- Removed one infrastructure test from the service test root.
- Removed two unrelated symbols from the broad infrastructure package API.
- Established one discoverable replay package behind the existing application port.
- Preserved separate replay runtime/backlog semantics without creating another service.

## Compatibility

No replay request, transaction ID, correlation propagation, SQLAlchemy session scope, canonical
publisher call, zero/one result mapping, dependency error, retry/DLQ behavior, Kafka topic, consumer
group, event, API, OpenAPI schema, metric, database structure, or downstream contract changed. Only
internal import paths and package ownership changed.

## Documentation Decision

Repository context, application-port catalog, critical-path coverage, consolidation ledger, wiki
source, and review ledger changed because replay adapter ownership and internal API truth changed.
README, supported-feature, database, API inventory, OpenAPI, and platform context require no change
because runtime topology and external replay behavior are unchanged.

## Validation

1. `29` focused replay application, adapter, composition, and delivery tests passed.
2. Scoped Ruff lint passed; package formatting was normalized before broad validation.
3. The complete transaction-processing unit package passed `817` tests in `7.74s`.
4. Five PostgreSQL booked-transaction replay lifecycle scenarios passed in `107.29s`.
5. Strict MyPy passed for the replay port, application use case, infrastructure adapter, and
   composition module.
6. Repository-wide warning-budget collection passed `4,602` unit tests with `10` deselected and
   zero warnings in `222.70s`, proving no hidden consumer of the removed flat/root surfaces remains.
7. Full lint, architecture, application-port catalog, transaction-replay boundary, critical-path
   coverage, docs/wiki, Ruff format, staged diff, and no-return checks passed.

## Remaining Work

Keep #719 open. Continue transaction-processing observability ownership in a separate slice. Do not
merge replay delivery controls into normal booking or restore flat/root compatibility imports.
