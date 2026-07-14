# CR-1595: Transaction Application Test Ownership

## Objective

Make transaction-processing unit-test organization reflect the established application boundary
instead of leaving core use-case behavior at the service-test root.

## Finding

The transaction-processing and booked-transaction replay use-case tests, totaling `27,111` bytes,
remained at the service-test root after delivery, runtime, infrastructure, and focused application
capabilities gained owned test packages. Concurrency and risk-based coverage manifests also pinned
the old process-transaction test path.

## Change

1. Moved the process-transaction use-case test to
   `application/test_process_transaction.py`, matching the production application module name.
2. Moved the booked-transaction replay test to the sibling application test boundary.
3. Added module docstrings and an application-specific ownership guard for target and retired paths.
4. Updated concurrency/duplicate-delivery and risk-based coverage evidence to the owned path.
5. Extended repository context with the application test-layout rule.

## Measurable Improvement

- Removed two unrelated files and `27,111` bytes from the flat service-test root.
- Reduced service-root test files from seven to five without creating a generic catch-all package.
- Added two target-path, two retired-path, and two module-docstring ownership assertions.
- Preserved all 22 moved behavior tests and added two ownership tests.

## Compatibility

No production code, financial behavior, API, OpenAPI schema, event contract, metric, database
structure, image, runtime topology, or downstream contract changed. Git history remains detectable
as file renames, and test discovery remains repository-native.

## Documentation Decision

Repository context, concurrency evidence, risk-based coverage evidence, and the codebase-review
ledger changed because test ownership changed. README, supported features, database catalog, API
inventory, OpenAPI, wiki source, image metadata, and platform context require no change.

## Validation

1. Moved application behavior and ownership cohort passed: `24 passed`.
2. Complete transaction-processing unit package passed: `832 passed`.
3. Concurrency duplicate-delivery and risk-based coverage matrix guards passed.
4. Strict architecture, testability, and documentation/wiki gates passed.
5. Ruff lint and format checks passed for the moved and new tests.
6. Repository diff check passed.

## Remaining Work

Keep #719 open. Organize domain-structure, compatibility, image, and web tests in separate slices;
do not replace the service-root dump with one mixed governance package.
