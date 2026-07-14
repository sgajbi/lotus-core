# CR-1604: Transaction Validation Test Ownership

## Objective

Place ordinary trade, income, and validation reason-code tests beside the owned transaction
validation domain family instead of in the generic transaction test root.

## Finding

BUY/SELL trade rules, DIVIDEND/INTEREST income rules, and stable validation reason codes live under
`app/domain/transaction/validation`. Their tests remained in the generic transaction folder while
test manifests, critical-path coverage, and transaction RFC evidence pinned the stale paths.

## Change

1. Moved income rules to `domain/transaction/validation/test_income.py`.
2. Moved trade rules to `domain/transaction/validation/test_trades.py`.
3. Moved reason-code vocabulary to `domain/transaction/validation/test_reason_codes.py`.
4. Added one package-structure guard for all target and retired paths.
5. Reconciled governed test manifests, critical-path evidence, and BUY/SELL/DIVIDEND/INTEREST RFCs.

## Measurable Improvement

- Removed three validation modules from the generic transaction test root.
- Reduced generic transaction-root modules from seven to four.
- Added three target-owner and three retired-path assertions.
- Preserved strict metadata, date ordering, amount/quantity, income direction, withholding, and
  stable reason-code coverage.

## Compatibility

No production validation rule, reason code, domain model, calculation, use case, port, adapter, API,
OpenAPI schema, event contract, persistence behavior, database structure, metric, runtime topology,
or downstream contract changed.

## Documentation Decision

Governed manifests, critical-path evidence, and affected transaction RFCs changed because evidence
paths changed. Existing repository context already requires nested domain-family ownership, so no
duplicate context was added. README, supported features, API inventory, OpenAPI, wiki source,
platform context, and skills require no change.

## Validation

1. Focused transaction validation suites passed: `22 passed`.
2. Transaction BUY contract passed: `211 passed`.
3. Transaction SELL contract passed: `131 passed`.
4. Transaction DIVIDEND contract passed: `282 passed`.
5. Transaction INTEREST contract passed: `312 passed`.
6. Complete transaction-processing unit package passed: `844 passed`.
7. Critical-path coverage and test-lane governance guards passed.
8. Documentation/wiki, RFC ledger, and repository-wide Ruff lint/format gates passed.
9. Same-pattern scan found no governed evidence references to the retired paths.
10. Repository diff check passed.

## Remaining Work

Keep #719 open. Move root transaction identity/booking/processing structure and nested FX tests in
separate slices; broader unified runtime acceptance criteria remain outstanding.
