# CR-1593: Transaction Delivery And Runtime Test Ownership

## Objective

Make unit-test organization reflect the established Kafka delivery and runtime production packages
instead of accumulating unrelated tests at the transaction-processing service root.

## Finding

Three Kafka mapper/consumer tests and two runtime composition/manager tests, totaling `25,747`
bytes, remained at the service-test root. One duplicate-delivery governance manifest pinned an old
root path, and Kafka delivery source/tests were absent from transaction critical-path globs.

## Change

1. Moved replay-request consumer, transaction consumer, and transaction-event mapper tests under
   the mirrored `delivery/kafka` package with concise domain names.
2. Moved consumer-composition and runtime-manager tests under the existing `runtime` test package.
3. Added package and moved-module docstrings plus delivery/runtime retired-path guards.
4. Updated critical-path coverage and duplicate-delivery evidence to the owned paths.
5. Reconciled repository architecture context and the codebase-review ledger.

## Measurable Improvement

- Removed five unrelated files and `25,747` bytes from the flat service-test root.
- Added one explicit Kafka delivery test package and completed the existing runtime test package.
- Added five retired-path assertions and three target-path assertions for Kafka delivery, plus two
  retired-path and two target-path assertions for runtime ownership.
- Extended critical-path governance to Kafka delivery production and test code.

## Compatibility

No test behavior, production code, API, OpenAPI schema, event, topic, group, metric, database
structure, image, runtime topology, or downstream contract changed. Git history is preserved as
renames, and test discovery remains repository-native.

## Documentation Decision

Repository context, critical-path coverage, duplicate-delivery evidence, and the review ledger
changed because test/governance ownership changed. README, supported features, database catalog,
API inventory, OpenAPI, wiki source, durability policy, image metadata, consolidation behavior,
and platform context require no change.

## Validation

1. The moved delivery/runtime cohort passed: `42 passed`.
2. The full transaction-processing unit package passed: `824 passed`.
3. Ruff lint and format checks passed for both mirrored packages.
4. Critical-path coverage and concurrency duplicate-delivery contract guards passed with the new
   paths.
5. Repository lint, architecture, and docs gates passed.
6. The full-repository warning gate was not repeated because production code and test behavior are
   unchanged; the complete affected service package supplies the proportional warning/import proof.

## Remaining Work

Keep #719 open. Organize application, domain-structure, image, compatibility, and web tests in
separate ownership slices while preserving governed paths and avoiding a new generic test package.
