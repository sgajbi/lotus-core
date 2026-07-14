# CR-1601: Position Domain Test Ownership

## Objective

Place deterministic position history and reducer tests beside the owned position domain package and
remove the obsolete mixed `position` test folder.

## Finding

Pure history construction, transaction ordering, state reduction, corporate-action quantity,
cash-position, FX-contract, zero-balance, and backdated replay policies remained under a generic
service-level `position` test folder. Production already owns those policies under
`app/domain/position`, while manifests, RFC evidence, and developer commands pinned the stale path.

## Change

1. Moved history tests to `domain/position/test_history.py`.
2. Moved reducer tests to `domain/position/test_reducer.py` and added its missing module docstring.
3. Added domain-owner, retired-path, and mixed-folder-empty assertions.
4. Reconciled test manifests, critical-path/risk standards, transaction RFC evidence, and the
   position developer guide.
5. Extended repository-local test-layout guidance to cover domain behavior as well as structure.

## Measurable Improvement

- Removed the final two modules from the obsolete mixed `position` folder.
- Reduced mixed position-root test modules from two to zero.
- Added two domain-owner assertions, two retired-path assertions, and one mixed-folder-empty guard.
- Preserved direct coverage for deterministic ordering, epoch/replay decisions, transfer and
  corporate-action quantity effects, cash positions, FX contracts, and basis reset invariants.

## Compatibility

No production domain policy, calculation output, application use case, port, adapter, API, OpenAPI
schema, event contract, persistence behavior, database structure, metric, runtime topology, or
downstream contract changed.

## Documentation Decision

Repository context, governed coverage standards, transaction RFC evidence, and the position
developer guide changed because test ownership and commands changed. README, supported features,
API inventory, OpenAPI, wiki source, and platform context require no change.

## Validation

1. Focused position domain suites passed: `47 passed`.
2. Transaction FX contract passed: `318 passed`.
3. Transaction portfolio-flow bundle contract passed: `234 passed`.
4. Complete transaction-processing unit package passed: `840 passed`.
5. Critical-path coverage, risk matrix, and test-lane governance guards passed.
6. Documentation/wiki, RFC ledger, and repository-wide Ruff lint/format gates passed.
7. Same-pattern scan found old mixed-position paths only in explicit retired-path guards.
8. Repository diff check passed.

## Remaining Work

Keep #719 open. Continue migrating the generic `cost` and `transaction` test roots by actual domain,
application, and infrastructure ownership without changing financial behavior.
