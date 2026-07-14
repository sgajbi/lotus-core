# CR-1596: Transaction Domain Structure Test Ownership

## Objective

Keep transaction domain architecture evidence beside the domain package it protects instead of at
the service-test root.

## Finding

Cost-basis and processing-stage package structure guards, totaling `3,995` bytes, remained at the
service-test root. The cost-basis domain standard also pinned the old root path, and moving the
guards without correcting their repository-root resolution would silently point them above the
repository.

## Change

1. Moved the cost-basis structure guard to `domain/cost_basis/test_package_structure.py`.
2. Moved the processing-stage structure guard to `domain/processing/test_package_structure.py`.
3. Corrected repository-root resolution for both deeper paths and added target/retired-path checks.
4. Reconciled the cost-basis domain standard and repository-local test-layout guidance.

## Measurable Improvement

- Removed two unrelated files and `3,995` bytes from the flat service-test root.
- Reduced service-root test files from five to three.
- Added two domain-owner path assertions and two retired root-path assertions.
- Preserved nine architecture assertions and added two ownership assertions.

## Compatibility

No production code, domain behavior, financial calculation, API, OpenAPI schema, event contract,
metric, database structure, image, runtime topology, or downstream contract changed. Test discovery
remains repository-native.

## Documentation Decision

Repository context, the cost-basis domain standard, and the codebase-review ledger changed because
test ownership changed. README, supported features, database catalog, API inventory, OpenAPI, wiki
source, image metadata, and platform context require no change.

## Validation

1. Moved domain structure cohort passed: `11 passed`.
2. Complete transaction-processing unit package passed: `834 passed`.
3. Domain-layer import guard and documentation/wiki gates passed.
4. Ruff lint and format checks passed for both moved guards.
5. Repository diff check passed.

## Remaining Work

Keep #719 open. Organize compatibility, image, and web tests in separate slices; do not combine
delivery-contract and architecture-governance tests into one generic package.
