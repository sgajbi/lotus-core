# CR-1591: Transaction Runtime Dependency Composition

## Objective

Complete the #719 flat-infrastructure cleanup by moving concrete application assembly to the
runtime composition root and removing builder/factory exports from the infrastructure package.

## Finding

`app/infrastructure/composition.py` was the last implementation file in the infrastructure root.
It built live processing, replay, and AVCO reconciliation use cases from concrete SQLAlchemy,
Kafka, cache, observer, and repository dependencies. Runtime consumers, an operator command, test
support, integration tests, and unit tests imported those builders through the broad infrastructure
package, obscuring the composition-root boundary.

## Change

1. Moved dependency assembly to `app/runtime/dependency_composition.py` with a module docstring.
2. Wired runtime consumer composition directly to the runtime dependency builders.
3. Migrated the AVCO operator command, test support, integration tests, and unit tests to the
   explicit composition root.
4. Removed two factories and three builders from the broad infrastructure-root API without aliases.
5. Moved composition tests under a mirrored runtime package and added a no-return structure guard.
6. Added runtime composition to critical-path coverage and reconciled repository context,
   consolidation evidence, wiki source, and the review ledger.

## Measurable Improvement

- Removed the final implementation module from the flat infrastructure root.
- Removed one runtime-assembly test from the service test root.
- Removed five composition-specific symbols from the broad infrastructure API.
- Established one explicit runtime dependency composition root for consumers and operator commands.
- Kept adapters in infrastructure and behavior in application/domain layers.

## Compatibility

No dependency choice, session/cache/producer lifetime, use-case configuration, consumer, operator
command, API, OpenAPI schema, event, topic, group, metric, database structure, image, runtime
topology, or downstream contract changed. Only internal composition ownership and import paths
changed.

## Documentation Decision

Repository context, critical-path coverage, consolidation evidence, transaction-processing wiki,
and the review ledger changed because composition-root truth changed. README, supported features,
database catalog, API inventory, OpenAPI, durability policy, image metadata, and platform context
require no change because behavior, persistence, and topology are unchanged.

## Validation

1. `12` focused dependency-composition, runtime-consumer, operator-command, and structure tests
   passed.
2. The full transaction-processing unit package passed: `821 passed`.
3. The repository warning budget passed: `4,612 passed`, `10 deselected`, and zero warnings.
4. Strict MyPy passed for the transaction-processing port and both runtime composition modules.
5. All `12` affected integration scenarios collected through the runtime composition import path.
6. Repository lint, architecture, critical-path contract, image provenance, and docs/wiki gates
   passed.
7. Stale-path and staged-diff checks passed; the retired infrastructure composition path remains
   only in this historical finding.

## Remaining Work

Keep #719 open. Continue evidence-led review of the broad infrastructure package front door and
remaining service-root tests without replacing explicit ownership with another generic package.
