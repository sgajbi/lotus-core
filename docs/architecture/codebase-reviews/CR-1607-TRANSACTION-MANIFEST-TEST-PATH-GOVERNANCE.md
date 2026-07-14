# CR-1607: Transaction Manifest Test Path Governance

## Objective

Keep the governed FX suite contract aligned with domain-owned test paths and prevent the retired FX
test prefix from returning.

## Finding

The test manifest itself referenced `domain/transaction/fx` after CR-1606, but its Query Service
contract test still required the retired `transaction/fx` validation path. The stale expectation
would fail the complete unit lane and could encourage restoring the obsolete tree.

## Change

1. Updated the FX manifest contract expectation to the domain-owned validation path.
2. Added an assertion that rejects every entry using the retired FX prefix.
3. Added the missing responsibility docstring to the manifest contract module.

## Measurable Improvement

- Removed the final non-retirement reference to the old transaction test tree.
- Added one explicit retired-prefix non-reintroduction assertion.
- Kept suite path existence and FX integration surface checks unchanged.

## Compatibility

No production code, test-suite membership, runtime mode, calculation, API, OpenAPI schema, event
contract, persistence behavior, database structure, metric, runtime topology, or downstream
contract changed.

## Documentation Decision

The codebase-review ledger changed because a same-pattern governance defect was fixed. Existing
repository context, test-lane governance, and skills already require manifest/path reconciliation,
so README, wiki, supported features, API inventory, OpenAPI, platform context, and skills require no
change.

## Validation

1. Focused manifest contract suite passed: `12 passed`.
2. Test-lane governance guard passed.
3. Documentation/wiki and repository-wide Ruff lint/format gates passed.
4. Same-pattern scan found old paths only in explicit retirement assertions.
5. Repository diff check passed.

## Remaining Work

Keep #719 open. This closes the stale-manifest defect inside the current test-ownership batch but
does not satisfy the umbrella runtime/downstream/capacity criteria.
