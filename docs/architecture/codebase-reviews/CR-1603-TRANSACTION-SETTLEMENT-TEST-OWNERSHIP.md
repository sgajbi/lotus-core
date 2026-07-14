# CR-1603: Transaction Settlement Test Ownership

## Objective

Place cash/product-leg and interest settlement tests beside the owned transaction settlement domain
family instead of in the generic transaction test root.

## Finding

Cash-entry mode, signed cash movement, generated cash-leg lineage, net-interest settlement, and
upstream product/cash pairing policies live under `app/domain/transaction/settlement`. Their tests
remained in the generic transaction folder, and transaction manifests plus RFC evidence pinned the
stale names.

## Change

1. Moved five policy suites under `domain/transaction/settlement` with production-aligned names.
2. Added one package-structure guard covering all target and retired paths.
3. Reconciled BUY/DIVIDEND/INTEREST/portfolio-flow manifest references and critical-path evidence.
4. Reconciled dual-leg adjustment and transaction conformance commands.

## Measurable Improvement

- Removed five settlement modules from the generic transaction test root.
- Reduced generic transaction-root modules from twelve to seven.
- Added five target-owner and five retired-path assertions without repeating boilerplate in each
  behavior suite.
- Preserved cash-entry mode, equal-and-opposite leg linkage, signed cash economics, withholding,
  interest, transfer pairing, and source-lineage coverage.

## Compatibility

No production settlement policy, cashflow/cost/position result, application use case, port, adapter,
API, OpenAPI schema, event contract, persistence behavior, database structure, metric, runtime
topology, or downstream contract changed.

## Documentation Decision

Governed test manifests, critical-path evidence, and affected transaction RFCs changed because test
paths changed. Existing repository context already requires nested domain-family ownership, so
adding more context would duplicate guidance. README, supported features, API inventory, OpenAPI,
wiki source, and platform context require no change.

## Validation

1. Focused settlement domain suites passed: `60 passed`.
2. Transaction DIVIDEND contract passed: `282 passed`.
3. Transaction INTEREST contract passed: `312 passed`.
4. Transaction portfolio-flow bundle contract passed: `234 passed`.
5. Complete transaction-processing unit package passed: `843 passed`.
6. Critical-path coverage and test-lane governance guards passed.
7. Documentation/wiki, RFC ledger, and repository-wide Ruff lint/format gates passed.
8. Same-pattern scan found no governed evidence references to the retired paths.
9. Repository diff check passed.

## Remaining Work

Keep #719 open. Migrate transaction validation, identity/booking, and FX tests in separate domain
family slices; broader unified processing/runtime acceptance criteria remain outstanding.
