# CR-1606: Transaction FX Test Ownership

## Objective

Place FX validation, linkage, contract lifecycle, control-code, currency, and realized-P&L baseline
tests beside the owned FX transaction domain family and retire the old transaction test tree.

## Finding

Production FX policies live under `app/domain/transaction/fx`, but six suites remained under the
legacy test-only `transaction/fx` tree. Test manifests, critical-path coverage, and FX RFC evidence
pinned those stale paths, and all six moved modules lacked responsibility docstrings.

## Change

1. Moved all six suites under `domain/transaction/fx` with their durable names preserved.
2. Added responsibility docstrings to each moved suite.
3. Added one family guard covering all target paths and complete retirement of the old transaction
   test tree.
4. Reconciled the FX manifest, critical-path evidence, conformance report, and implementation RFC.

## Measurable Improvement

- Removed the final six files from the old transaction test tree.
- Retired the test-only `transaction` directory completely.
- Added six target-owner assertions and one retired-tree assertion.
- Preserved validation/reason-code, linkage/swap grouping, contract lifecycle, currency/control-code,
  and realized FX P&L baseline coverage.

## Compatibility

No production FX policy, signed settlement economics, realized P&L result, domain model, use case,
port, adapter, API, OpenAPI schema, event contract, persistence behavior, database structure,
metric, runtime topology, or downstream contract changed.

## Documentation Decision

Governed manifests, critical-path evidence, and FX RFCs changed because evidence paths changed.
Existing repository context and skills already require nested domain-family ownership, so no
duplicate guidance was added. README, supported features, API inventory, OpenAPI, wiki source, and
platform context require no change.

## Validation

1. Focused FX domain suites passed: `29 passed`.
2. Transaction FX contract passed: `318 passed`.
3. Complete transaction-processing unit package passed: `846 passed`.
4. Critical-path coverage, test-lane governance, and domain-layer guards passed.
5. Documentation/wiki, RFC ledger, and repository-wide Ruff lint/format gates passed.
6. Same-pattern scan found no governed evidence references to the retired tree.
7. Repository diff check passed.

## Remaining Work

Keep #719 open. This completes the bounded transaction test-ownership batch, not the umbrella
runtime/downstream/capacity acceptance criteria. The generic `cost` test tree remains a separately
bounded future organization slice.
