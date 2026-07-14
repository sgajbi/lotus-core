# CR-1602: Corporate Action Domain Test Ownership

## Objective

Place corporate-action ordering and validation tests beside the owned transaction-domain family
instead of in the generic transaction test root.

## Finding

Corporate-action dependency ordering and Bundle A validation are implemented under
`app/domain/transaction/corporate_action`, but their tests remained in the generic transaction
folder. Critical-path, risk, and RFC evidence pinned the stale paths and obscured family ownership.

## Change

1. Moved ordering coverage to `domain/transaction/corporate_action/test_ordering.py`.
2. Moved validation coverage to `domain/transaction/corporate_action/test_validation.py`.
3. Added missing responsibility documentation plus owner and retired-path assertions.
4. Reconciled critical-path, risk, and corporate-action RFC evidence paths.
5. Extended repository-local test-layout guidance for nested domain families.

## Measurable Improvement

- Removed two corporate-action modules from the generic transaction test root.
- Reduced generic transaction-root modules from fourteen to twelve.
- Added two domain-family owner assertions and two retired-path assertions.
- Preserved deterministic dependency-rank, target-ordering, linkage, allocation, consideration, and
  validation reason-code coverage.

## Compatibility

No production domain policy, calculation result, application use case, port, adapter, API, OpenAPI
schema, event contract, persistence behavior, database structure, metric, runtime topology, or
downstream contract changed.

## Documentation Decision

Repository context, critical-path/risk standards, RFC index, and affected corporate-action RFCs
changed because test evidence paths changed. README, supported features, API inventory, OpenAPI,
wiki source, and platform context require no change.

## Validation

1. Focused corporate-action domain suites passed: `15 passed`.
2. Transaction portfolio-flow bundle contract passed: `234 passed`.
3. Complete transaction-processing unit package passed: `842 passed`.
4. Critical-path coverage and risk-based test coverage matrix guards passed.
5. Documentation/wiki, RFC ledger, and repository-wide Ruff lint/format gates passed.
6. Same-pattern scan found no governed evidence references to the retired paths.
7. Repository diff check passed.

## Remaining Work

Keep #719 open. Migrate settlement, validation, identity, and FX transaction tests in separate
domain-family slices; do not recreate a broad transaction dump under `domain`.
