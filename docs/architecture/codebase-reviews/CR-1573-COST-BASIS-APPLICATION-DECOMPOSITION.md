# CR-1573: Cost-Basis Application Decomposition

## Objective

Reduce the design-time complexity of the unified transaction processor by moving cost-basis policy,
deterministic rebuild planning, upstream cash-leg validation, and SQL reconciliation into their
correct layers and cohesive domain-owned packages. The follow-up slice also moves calculated
transaction persistence behind application ports without changing the deployed runtime boundary.

## Finding

`CostCalculationWorkflow` remained a 1,067-line infrastructure coordinator with five distinct
responsibilities mixed into it:

1. deciding which transaction types open, consume, preserve, or transfer cost lots;
2. replaying canonical history to construct an average-cost-pool rebuild plan;
3. loading and validating upstream-provided cash legs; and
4. deciding which calculated lot-state scope to persist for incremental FIFO, AVCO, and full
   rebuilds; and
5. coordinating SQL reconciliation of persisted average-cost-pool state.

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
5. Added `application.cost_basis_processing.persist_open_lot_state` and
   `CostBasisCalculationResult`, removed the transport-coupled private persistence method, and
   removed the unused transaction-repository dependency from that policy.
6. Renamed the internal persistence selector to `OpenLotPersistenceScope` and removed its obsolete
   infrastructure export without a compatibility facade.
7. Mirrored every new or moved production package in the unit-test tree and removed tests coupled
   to private infrastructure workflow methods.
8. Preserved the public infrastructure import for the upstream-unavailable exception while moving
   its implementation to the application layer.
9. Moved timeline orchestration and its tests under the mirrored
   `application.cost_basis_processing` package and guarded the retired flat paths.
10. Aligned average-cost-pool reconciliation across explicitly named domain, port, application, and
    infrastructure modules, replacing the flat application/port roots and vague domain filename.
11. Grouped the cost-basis observation protocol under `ports.cost_basis`, and the Prometheus adapter
    and instruments under `infrastructure.cost_basis`, with a mirrored infrastructure test.
12. Added `application.cost_basis_processing.persist_cost_basis_transactions` to own affected-suffix
    transaction, fee-breakdown, opening-lot, and accrued-income-offset writes through typed ports;
    it returns immutable `BookedTransaction` values for infrastructure event mapping.
13. Added typed persistence observations and a failure-contained Prometheus/log adapter, preserving
    BUY/SELL lifecycle labels and support event names without importing telemetry into application
    code.
14. Removed the persistence private methods and duplicate tests from the broad infrastructure
    workflow/test roots, and changed the rollback integration test to inject failure at the concrete
    repository adapter instead of a retired workflow implementation detail.

## Measurable Improvement

- removed four policy/application responsibilities from the 1,067-line infrastructure workflow;
- removed 99 lines of lot-state policy from infrastructure and replaced private-method tests with
  five direct application-port scenarios;
- replaced ORM-row-oriented rebuild tests with canonical application-port tests;
- made lot behavior independently testable without infrastructure imports;
- organized reconciliation code and tests below explicit `cost_basis` packages; and
- replaced six flat, vague, or mismatched production/test paths with layer-mirrored cost-basis
  package paths and retirement guards; and
- retained one combined transaction-processing runtime and application use case without adding a
  deployable service boundary;
- reduced `CostCalculationWorkflow` from 869 to 742 lines in the persistence follow-up while placing
  its 146-line application function and 256-line behavioral suite in mirrored owner packages; and
- removed every repository reference to the retired private persistence helpers.

## Compatibility

Transaction ordering, FIFO/AVCO calculations, settlement pairing, database schema, SQL operations,
event envelopes, topics, API contracts, and runtime topology are unchanged. The existing
`infrastructure.UpstreamCashLegUnavailableError` import remains available to current consumers.
This slice improves design modularity inside the unified processor; it does not claim completion of
the broader calculator-runtime retirement tracked by #719.

## Validation

- complete transaction-processing unit suite after persistence extraction: `780 passed`;
- PostgreSQL AVCO reconciliation: `2 passed`;
- PostgreSQL combined cash-in-lieu lifecycle: `1 passed`;
- focused domain, application, and infrastructure tests: passed;
- timeline/backdated/incremental/private-banking scenario tests: `52 passed`;
- reconciliation use-case, adapter, composition, and operator-report tests: `30 passed`;
- cost-basis observability, composition, timeline, and incremental-workflow tests: `23 passed`;
- application-layer, dependency-inversion, domain-layer, and infrastructure-adapter guards:
  passed;
- focused strict MyPy, Ruff lint/format, import scans, and `git diff --check`: passed.
- backdated suffix partial-write rollback on PostgreSQL after repository-level failure injection:
  `1 passed`.

## Documentation Decision

Repository context, this review ledger, and the Cost Processing wiki source changed because
application and infrastructure ownership changed. README, OpenAPI, API inventory,
supported-features material, database migrations, central platform context, and Lotus skills
require no change because external behavior, persistence contracts, platform routing, and the
governed layered-architecture rule are unchanged.

## Remaining Work

Keep #719 open. Further slices must extract settlement/generated-leg coordination only when each
resulting application service has a narrow port contract and focused domain tests.
Do not restore extracted behavior to `CostCalculationWorkflow`, create flat compatibility modules,
or split the runtime without workload, failure-isolation, scaling, security, or ownership evidence.
