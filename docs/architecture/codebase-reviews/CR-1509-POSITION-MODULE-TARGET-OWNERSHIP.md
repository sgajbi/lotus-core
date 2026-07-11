# CR-1509: Position Module Target Ownership

Date: 2026-07-11
Issue: #468
Status: Reconciled onto current main; aggregate validation and full consolidation cutover pending

## Objective

Remove the retired position-calculator source root and make the unified transaction-processing
service the unambiguous owner of position reduction, recalculation coordination, and persistence.

## Finding

The standalone position runtime had already been removed, but its surviving reducer, workflow, and
repository remained under `src/services/calculators/position_calculator`. The target image copied
that legacy tree into the runtime, which obscured ownership, retained dead models and package
markers, and made architecture guards teach agents to extend the obsolete layout.

## Implementation

- Moved the pure position reducer to the target domain package.
- Moved SQLAlchemy recalculation coordination and persistence to target infrastructure.
- Renamed the coordinator to `PositionCalculationWorkflow` and replaced obsolete queue-oriented
  decision language with inline backdated-recalculation language.
- Deleted unused position models, repository stubs, package markers, generated package remnants,
  and the target image's legacy position source copy.
- Redirected target adapters, the SQLAlchemy unit of work, tests, coverage ownership, repository
  output exceptions, and architecture guards to the new paths.
- Added an explicit image contract that prevents the legacy position root from returning.

## Architecture And Compatibility

The flow is now delivery mapper -> application use case -> position port -> target infrastructure
adapter -> pure domain reducer/recalculation policy -> target repository -> PostgreSQL. The current
workflow remains in infrastructure because it coordinates `AsyncSession`, epoch fencing,
repositories, and metrics; claiming it as domain or application code would be false layering.

No public API, database schema, topic, or payload changed. The internal position-processing result
retains the always-false `replay_queued` compatibility field until downstream result-contract
retirement is separately evidenced. Historical replay terminology remains only where it accurately
describes deterministic ledger-history reconstruction, not a queue or deployable.

## Validation

- Position, transaction-spec, architecture, image, and registry cohort: `155 passed`.
- Repository-output, critical-path, testability, and image-inventory guards: `18 passed`.
- Repository-native transaction-processing contract: `32 passed in 131.81s`.
- Installed target distribution imported the reducer, workflow, and repository without the legacy
  source root.
- MyPy, Ruff, strict architecture, position reducer boundary, repository-output, testability,
  critical-path, and event-runtime contract gates passed.
- Reconciliation onto the post-PR-727 mainline preserved correction-aware materialized-event
  rebuild behavior and passed `144` focused position, adapter, architecture, image, and transaction
  specification tests plus targeted MyPy, Ruff, JSON, and diff checks.

## Remaining Work

Move surviving cost and cashflow modules under target-owned domain/application/infrastructure
names only after equivalent import, contract, installed-image, and downstream evidence. Migrate the
legacy-named position test directories in a separate no-behavior slice. Remove compatibility result
fields only after consumer inventory proves they are unused.

No platform skill change is required. Existing backend delivery, codebase review, and repository
context rules already require target ownership, dead-code proof, truthful layering, installed-image
validation, and prevention guards.
