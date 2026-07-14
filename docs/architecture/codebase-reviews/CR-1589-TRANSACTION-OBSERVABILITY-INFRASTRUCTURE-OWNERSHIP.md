# CR-1589: Transaction Observability Infrastructure Ownership

## Objective

Advance issue #719 by giving aggregate transaction-processing and corporate-action reconciliation
telemetry explicit financial-capability ownership instead of leaving unrelated adapters and tests in
flat service roots.

## Finding

`prometheus_observability.py` and `corporate_action_reconciliation_observability.py` were the last
two observability modules in the flat transaction infrastructure root. Both adapters were exported
through the broad infrastructure package, their tests were at the service test root, and the
corporate-action observer was separated from the cost-basis reconciliation capability it reports.

## Change

1. Added `app/infrastructure/transaction_processing/observability.py` for aggregate live/replay
   operation metrics behind `TransactionProcessingObserver`.
2. Moved corporate-action reconciliation metrics and support logs to
   `app/infrastructure/cost_basis/corporate_action_observability.py`.
3. Updated production composition and internal tests to import from owned package front doors.
4. Contained corporate-action metric and support-log failures so telemetry cannot abort the enclosing
   financial transaction after reconciliation evidence persistence.
5. Removed all four observability symbols from the broad infrastructure-root API without aliases.
6. Mirrored both test locations under their infrastructure packages and added package docstrings.
7. Added no-return guards for both flat source modules, both service-root tests, and both broad root
   exports.
8. Reconciled repository context, consolidation evidence, wiki source, and the review ledger.

## Measurable Improvement

- Removed two modules from the flat infrastructure root.
- Removed two infrastructure tests from the service test root.
- Removed four capability-specific symbols from the broad infrastructure API.
- Established one aggregate transaction-processing adapter package and completed cost-basis
  ownership for corporate-action reconciliation evidence.
- Preserved fail-open telemetry behavior without coupling application or domain code to Prometheus.

## Compatibility

No metric name, label, bucket, timing behavior, reconciliation status, support-log event, API,
OpenAPI schema, event, topic, consumer group, database structure, transaction boundary, runtime
topology, or downstream contract changed. Internal import paths and package ownership changed.
Corporate-action telemetry failure behavior intentionally changed from propagating into financial
processing to bounded logging and continuation; a regression test proves this supportability rule.

## Documentation Decision

Repository context, critical-path coverage, consolidation evidence, transaction-processing wiki,
cost-calculator wiki, and the review ledger changed because internal ownership truth changed.
README, supported features, database catalog, API inventory, OpenAPI, and platform context require
no change because external behavior, runtime topology, and data structures are unchanged.

## Validation

1. `13` focused observability, failure-containment, package-structure, and composition tests passed.
2. The complete transaction-processing unit package passed `820` tests in `6.87s`.
3. Strict MyPy passed for both observer ports, both infrastructure adapters, and composition.
4. The PostgreSQL atomic-unit-of-work suite collected all `12` scenarios through the new internal
   import path; no database behavior changed, so no database execution was required for this move.
5. Repository-wide warning-budget collection passed `4,611` unit tests with `10` deselected and
   zero warnings in `173.39s`, proving no hidden consumer of the removed flat/root surfaces remains.
6. Full Ruff lint/format, architecture, observability-contract, critical-path coverage, docs/wiki,
   staged-diff, and no-return checks passed.

## Remaining Work

Keep #719 open. Review transaction unit-of-work and composition ownership in separate slices; do not
turn `transaction_processing` into a generic infrastructure dump or restore broad compatibility
exports.
