# CR-1586: Transaction Event Mapping Package Ownership

## Objective

Advance issue #719 by giving governed transaction-event translation one explicit anti-corruption
package instead of unrelated flat infrastructure modules and service-root tests.

## Finding

The bidirectional booked-transaction mapper and synthetic FX-instrument event mapper remained as
`booked_transaction_event_mapper.py` and `fx_event_mapper.py` in the transaction infrastructure
root. Their tests remained at the service test root, while cost-basis, cashflow, transaction-spec,
golden-scenario, capacity, and concurrency consumers imported the flat paths directly. This made
framework/domain translation look like miscellaneous infrastructure rather than one owned boundary.

## Change

1. Added `app/infrastructure/transaction_mapping/` with explicit `booked_transaction.py` and
   `foreign_exchange_instrument.py` modules.
2. Preserved the import-time transaction event/domain field-drift check and every bidirectional
   mapping operation.
3. Moved mapper tests into a mirrored transaction-mapping infrastructure package and added module
   docstrings.
4. Migrated every production, transaction-spec, golden-scenario, unit, capacity, and concurrency
   consumer to the owned package.
5. Deleted both flat source modules and both service-root mapper tests without aliases.
6. Added a no-return structure guard and critical-path source/test ownership.
7. Reconciled repository context, transaction consolidation evidence, wiki source, and the review
   ledger.
8. Added the missing typed SQLAlchemy `Select` return contract to the touched open-lot checkpoint
   statement builder after strict MyPy exposed that adjacent boundary gap.

## Measurable Improvement

- Removed two unrelated modules from the flat infrastructure root.
- Removed two infrastructure tests from the service test root.
- Established one self-explanatory package for governed event/domain translation.
- Preserved one import-time field-drift gate for all booked transaction fields.
- Gave future transaction and synthetic-instrument mappings one discoverable extension point.

## Compatibility

No `TransactionEvent`, `InstrumentEvent`, `BookedTransaction`, or `FxContractInstrument` field,
normalization, tuple conversion, envelope value, schema version, event type, topic, persistence
mapping, calculation, API, OpenAPI schema, metric, database structure, or downstream contract
changed. Only internal import paths and test organization changed.

## Documentation Decision

Repository context, critical-path coverage, consolidation ledger, wiki source, and review ledger
changed because mapping ownership and navigation changed. README, application-port catalog,
supported-feature, database, API inventory, OpenAPI, and platform context require no change because
the mapping package is an internal infrastructure anti-corruption boundary with no new port,
deployable, persistence, or external capability.

## Validation

1. `144` focused mapper, cost-basis, cashflow, transaction-spec, and portfolio-flow golden tests
   passed.
2. Scoped Ruff lint and format passed after normalizing explicit owned-package imports.
3. The complete transaction-processing unit package passed `816` tests in `6.53s`.
4. Four directly affected PostgreSQL AVCO-capacity and cost-basis concurrency scenarios passed in
   `106.19s`.
5. Strict MyPy passed for eleven booked-transaction, FX-instrument, mapping, cashflow, and cost-basis
   source modules.
6. Repository-wide warning-budget collection passed `4,601` unit tests with `10` deselected and
   zero warnings in `210.62s`, proving no hidden consumer of either retired flat module remains.
7. Full lint, architecture, critical-path coverage, docs/wiki, staged diff, mapping anti-corruption,
   Ruff format, and no-return checks passed.

## Remaining Work

Keep #719 open. Continue evidence-led organization of replay and observability infrastructure in
separate slices. Do not move framework event models into domain/application code or recreate broad
mapping facades.
