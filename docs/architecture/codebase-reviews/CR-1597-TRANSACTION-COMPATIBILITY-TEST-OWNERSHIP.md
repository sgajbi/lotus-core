# CR-1597: Transaction Compatibility Test Ownership

## Objective

Place cross-layer legacy-import and retired-facade evidence in an explicit transaction architecture
test boundary instead of at the service-test root.

## Finding

The `1,163`-byte compatibility confinement guard remained at the service-test root even though it
scans the complete transaction capability for legacy calculator imports and obsolete infrastructure
facades. It also repeated repository/service path setup inside separate tests.

## Change

1. Moved and renamed the guard to
   `architecture/test_legacy_compatibility_confinement.py`.
2. Consolidated repository, service-source, and service-test root constants.
3. Added target architecture-owner and retired root-path assertions.
4. Extended repository-local test-layout guidance for cross-layer architecture guards.

## Measurable Improvement

- Removed one cross-layer file and `1,163` bytes from the flat service-test root.
- Reduced service-root test files from three to two.
- Added one architecture-owner path assertion and one retired root-path assertion.
- Preserved the calculator-import and retired-event-mapper confinement checks.

## Compatibility

No production code, legacy-import policy, domain behavior, financial calculation, API, OpenAPI
schema, event contract, metric, database structure, image, runtime topology, or downstream contract
changed.

## Documentation Decision

Repository context and the codebase-review ledger changed because test ownership changed. README,
supported features, database catalog, API inventory, OpenAPI, wiki source, image metadata, and
platform context require no change.

## Validation

1. Compatibility architecture guard passed: `3 passed`.
2. Complete transaction-processing unit package passed: `835 passed`.
3. Complete strict architecture and documentation/wiki gates passed.
4. Ruff lint and format checks passed for the moved guard.
5. Repository diff check passed.

## Remaining Work

Keep #719 open. Organize image packaging and HTTP health tests as separate delivery-owned slices;
do not place them in the cross-layer architecture package.
