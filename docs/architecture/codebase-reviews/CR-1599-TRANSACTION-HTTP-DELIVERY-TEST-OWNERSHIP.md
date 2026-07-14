# CR-1599: Transaction HTTP Delivery Test Ownership

## Objective

Place the transaction worker health, readiness, metrics, version, and HTTP security evidence beside
the HTTP delivery boundary instead of at the service-test root.

## Finding

The final test module at the service-test root validated only the worker's health HTTP application.
Its generic `web` name obscured that delivery responsibility and left the root available as an
unowned dumping location for later tests.

## Change

1. Moved and renamed the contract to `delivery/http/test_health_contract.py`.
2. Added HTTP test-package and module docstrings plus repository-root-stable contract lookup.
3. Renamed test cases around transaction-worker health responsibilities.
4. Added owner, retired-path, and empty service-test-root assertions.
5. Extended repository-local test-layout guidance for worker HTTP delivery contracts.

## Measurable Improvement

- Removed the final test module from the flat service-test root.
- Reduced service-root test files from one to zero.
- Added one explicit HTTP owner assertion, one retired-path assertion, and one no-root-dump guard.
- Preserved readiness dependency, runtime failure, security coverage, OpenAPI, and build metadata
  evidence.

## Compatibility

No production module, route, response payload, OpenAPI schema, security allowlist, health/readiness
behavior, metric, image metadata, database structure, financial calculation, event contract, runtime
topology, or downstream contract changed.

## Documentation Decision

Repository context and the codebase-review ledger changed because test ownership changed. README,
supported features, database catalog, API inventory, OpenAPI, wiki source, image metadata, and
platform context require no change.

## Validation

1. Focused HTTP delivery contract passed: `4 passed`.
2. Complete transaction-processing unit package passed: `837 passed`.
3. Security-control coverage and documentation/wiki gates passed.
4. Repository-wide Ruff lint and format checks passed.
5. Repository diff check passed.

## Remaining Work

Keep #719 open. Continue organizing transaction tests by true capability ownership while #718
retains the usage-proof requirement for legacy runtime retirement.
