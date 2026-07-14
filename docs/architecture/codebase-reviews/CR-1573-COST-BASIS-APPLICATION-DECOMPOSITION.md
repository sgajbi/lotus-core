# CR-1573: Cost-Basis Application Decomposition

## Objective

Reduce the design-time complexity of the unified transaction processor by moving cost-basis policy,
deterministic rebuild planning, upstream cash-leg validation, and SQL reconciliation into their
correct layers and cohesive domain-owned packages.

## Finding

`CostCalculationWorkflow` remained a 1,067-line infrastructure coordinator with four distinct
responsibilities mixed into it:

1. deciding which transaction types open, consume, preserve, or transfer cost lots;
2. replaying canonical history to construct an average-cost-pool rebuild plan;
3. loading and validating upstream-provided cash legs; and
4. coordinating SQL reconciliation of persisted average-cost-pool state.

The first responsibility is stable cost-basis domain policy. The next two are application behavior
over transaction, reference-data, and FX ports. Only the final responsibility belongs in
infrastructure. The reconciliation adapter and its test also remained at flat package roots, which
obscured ownership and encouraged further dumping into broad folders.

## Change

1. Added `domain.cost_basis.lot_behavior` as the canonical owner of transaction lot behavior and
   the behavior sets used by the cost engine.
2. Added `application.cost_basis_processing.AverageCostPoolRebuildPlanner` to replay canonical
   `BookedTransaction` history through existing ports and produce a validated rebuild plan without
   persistence side effects.
3. Added `application.cost_basis_processing.validate_upstream_cash_leg` to resolve and validate
   required settlement cash legs through `CostBasisTransactionStatePort`.
4. Moved the SQLAlchemy reconciliation adapter into the nested
   `infrastructure.cost_basis.average_cost_pool_reconciliation` package.
5. Mirrored every new or moved production package in the unit-test tree and removed tests coupled
   to private infrastructure workflow methods.
6. Preserved the public infrastructure import for the upstream-unavailable exception while moving
   its implementation to the application layer.

## Measurable Improvement

- removed three policy/application responsibilities from the 1,067-line infrastructure workflow;
- replaced ORM-row-oriented rebuild tests with canonical application-port tests;
- made lot behavior independently testable without infrastructure imports;
- organized reconciliation code and tests below explicit `cost_basis` packages; and
- retained one combined transaction-processing runtime and application use case without adding a
  deployable service boundary.

## Compatibility

Transaction ordering, FIFO/AVCO calculations, settlement pairing, database schema, SQL operations,
event envelopes, topics, API contracts, and runtime topology are unchanged. The existing
`infrastructure.UpstreamCashLegUnavailableError` import remains available to current consumers.
This slice improves design modularity inside the unified processor; it does not claim completion of
the broader calculator-runtime retirement tracked by #719.

## Validation

- complete transaction-processing unit suite: `752 passed`;
- PostgreSQL AVCO reconciliation: `2 passed`;
- PostgreSQL combined cash-in-lieu lifecycle: `1 passed`;
- focused domain, application, and infrastructure tests: passed;
- application-layer, dependency-inversion, domain-layer, and infrastructure-adapter guards:
  passed;
- focused strict MyPy, Ruff lint/format, import scans, and `git diff --check`: passed.

## Documentation Decision

Repository context, this review ledger, and the Cost Processing wiki source changed because
application and infrastructure ownership changed. README, OpenAPI, API inventory,
supported-features material, database migrations, central platform context, and Lotus skills
require no change because external behavior, persistence contracts, platform routing, and the
governed layered-architecture rule are unchanged.

## Remaining Work

Keep #719 open. Further slices must extract persistence and settlement/generated-leg coordination
only when each resulting application service has a narrow port contract and focused domain tests.
Do not restore extracted behavior to `CostCalculationWorkflow`, create flat compatibility modules,
or split the runtime without workload, failure-isolation, scaling, security, or ownership evidence.
