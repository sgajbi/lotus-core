# CR-1605: Transaction Domain Root Test Ownership

## Objective

Place booking metadata, processing classification, semantic identity, and package-structure tests
beside the transaction domain root and eliminate generic transaction-root test modules.

## Finding

Four suites directly validate modules under `app/domain/transaction`, but remained one level above
the mirrored domain test tree. Booking and processing paths were also pinned by transaction
manifests and RFC evidence, while two behavior modules lacked responsibility docstrings.

## Change

1. Moved booking, processing-type, and semantic-identity suites under `domain/transaction`.
2. Moved the transaction domain structure guard to `domain/transaction/test_package_structure.py`.
3. Corrected repository-root resolution and added target plus empty generic-root assertions.
4. Added missing responsibility docstrings to processing and semantic-identity coverage.
5. Reconciled transaction manifests and SELL/DIVIDEND/INTEREST RFC evidence paths.

## Measurable Improvement

- Removed the final four modules from the generic transaction test root.
- Reduced generic transaction-root modules from four to zero.
- Added four target-owner assertions and one empty-root regression assertion.
- Preserved booking linkage/policy, processing classification, semantic correction identity, domain
  docstring, retired flat module, and retired shared-transaction package evidence.

## Compatibility

No production booking policy, semantic identity, processing classification, calculation, use case,
port, adapter, API, OpenAPI schema, event contract, persistence behavior, database structure,
metric, runtime topology, or downstream contract changed.

## Documentation Decision

Governed manifests and affected transaction RFCs changed because evidence paths changed. Existing
repository context already requires mirrored domain ownership and empty flat roots, so no duplicate
context was added. README, supported features, API inventory, OpenAPI, wiki source, platform
context, and skills require no change.

## Validation

1. Focused transaction domain-root suites passed: `27 passed`.
2. Transaction BUY contract passed: `211 passed`.
3. Transaction SELL contract passed: `131 passed`.
4. Transaction DIVIDEND contract passed: `282 passed`.
5. Transaction INTEREST contract passed: `312 passed`.
6. Transaction FX contract passed: `318 passed`.
7. Complete transaction-processing unit package passed: `845 passed`.
8. Domain-layer and test-lane governance guards passed.
9. Documentation/wiki, RFC ledger, and repository-wide Ruff lint/format gates passed.
10. Same-pattern scan found no governed evidence references to the retired root paths.
11. Repository diff check passed.

## Remaining Work

Keep #719 open. Move the nested FX test tree beside `domain/transaction/fx` in a separate final
organization slice; broader unified runtime acceptance criteria remain outstanding.
