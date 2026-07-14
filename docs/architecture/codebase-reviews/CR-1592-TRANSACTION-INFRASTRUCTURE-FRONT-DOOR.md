# CR-1592: Transaction Infrastructure Front Door

## Objective

Make infrastructure dependencies explicit by retiring the generic transaction-processing
infrastructure facade after its adapters gained domain-owned packages.

## Finding

`app/infrastructure/__init__.py` re-exported `20` symbols spanning cashflow, cost basis, position,
and an application-layer settlement error. Five integration/unit callers still used that facade,
so imports concealed the capability being exercised and the root remained an attractive dumping
ground despite the package reorganization.

## Change

1. Migrated cashflow callers to `infrastructure.cashflow`.
2. Migrated AVCO reconciliation callers to `infrastructure.cost_basis`.
3. Reduced the infrastructure root to a documented namespace without imports or exports.
4. Added an AST-based package-structure test that rejects any executable root content.
5. Reconciled repository context, consolidation evidence, transaction-processing wiki source, and
   the codebase-review ledger.

## Measurable Improvement

- Removed `20` unrelated symbols from one broad package API.
- Removed all `5` remaining transaction-processing callers of that package API.
- Established one named capability in every infrastructure adapter import.
- Added one deterministic no-return guard without a compatibility alias.

## Compatibility

No adapter behavior, application policy, transaction ordering, API, OpenAPI schema, event, topic,
group, metric, database structure, image, runtime topology, or downstream contract changed. The
removed imports were internal package conveniences and all repository callers now use the existing
owned package APIs.

## Documentation Decision

Repository context, consolidation evidence, transaction-processing wiki source, and the review
ledger changed because dependency ownership truth changed. README, supported features, database
catalog, API inventory, OpenAPI, durability policy, image metadata, critical-path coverage, and
platform context require no change because behavior, persistence, topology, and governed runtime
paths are unchanged.

## Validation

1. `13` focused package-structure, cashflow repository/cache, and runtime-composition tests passed.
2. The full transaction-processing unit package passed: `822 passed`.
3. All `7` affected database integration scenarios collected through owned package imports.
4. The repository warning budget passed: `4,613 passed`, `10 deselected`, and zero warnings.
5. Repository formatting, lint, architecture, critical-path contract, image provenance, and
   docs/wiki gates passed.
6. Repository-wide import search, AST package guard, and staged-diff checks confirmed that no broad
   transaction infrastructure import or executable package-root content remains.

## Remaining Work

Keep #719 open. Organize remaining service-root tests around delivery, application, domain, runtime,
and web ownership in separate behavior-preserving slices; evaluate subpackage exports only when
usage evidence shows that narrower APIs remain too broad.
