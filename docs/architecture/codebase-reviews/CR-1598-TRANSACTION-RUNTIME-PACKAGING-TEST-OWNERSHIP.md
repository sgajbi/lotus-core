# CR-1598: Transaction Runtime Packaging Test Ownership

## Objective

Place transaction wheel and container source-closure evidence in a dedicated packaging test
boundary instead of at the service-test root.

## Finding

The `2,302`-byte image/package contract remained at the service-test root even though it validates
the bounded Python distribution, Docker build closure, legacy wheel exclusion, runtime import
smoke, non-root user, exposed port, and command for the deployable transaction image. The file also
lacked a module docstring.

## Change

1. Moved and renamed the contract to `packaging/test_runtime_image_contract.py`.
2. Added a responsibility docstring and corrected repository-root resolution for the deeper path.
3. Added target packaging-owner and retired root-path assertions.
4. Extended repository-local test-layout guidance for runtime packaging contracts.

## Measurable Improvement

- Removed one supply-chain file and `2,302` bytes from the flat service-test root.
- Reduced service-root test files from two to one.
- Added one packaging-owner path assertion and one retired root-path assertion.
- Preserved bounded-wheel and Docker source-closure assertions.

## Compatibility

No Dockerfile, wheel metadata, image label, runtime command, production code, financial behavior,
API, OpenAPI schema, event contract, metric, database structure, runtime topology, or downstream
contract changed.

## Documentation Decision

Repository context and the codebase-review ledger changed because test ownership changed. README,
supported features, database catalog, API inventory, OpenAPI, wiki source, image metadata, and
platform context require no change.

## Validation

1. Runtime packaging contract passed: `3 passed`.
2. Complete transaction-processing unit package passed: `836 passed`.
3. Image provenance and documentation/wiki gates passed.
4. Ruff lint and format checks passed for the moved contract.
5. Repository diff check passed.

## Remaining Work

Keep #719 open. Organize the remaining HTTP health contract under delivery ownership; broader
legacy deployable and compatibility retirement still requires #718 usage proof.
