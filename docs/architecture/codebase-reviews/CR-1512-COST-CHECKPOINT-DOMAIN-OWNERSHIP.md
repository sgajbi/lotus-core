# CR-1512: Cost Checkpoint Domain Ownership

Date: 2026-07-11
Issue: #468
Status: Reconciled onto current main; aggregate validation and workflow/persistence extraction pending

## Objective

Move incremental and average-cost checkpoint policy into the transaction-processing cost-basis
domain without changing persisted state, ordering behavior, or downstream contracts.

## Finding

`CostBasisProcessingCheckpoint` and `AverageCostPoolCheckpoint` are framework-free domain state and
transition policies, but remained under the legacy calculator application package. This made the
target workflow depend on legacy ownership and encouraged persistence records and domain objects to
share field names implicitly.

## Implementation

- Moved both checkpoint policies under the target-owned `app/domain/cost_basis` public API.
- Replaced generic engine vocabulary with `COST_BASIS_STATE_VERSION` and
  `calculation_state_version` inside the domain.
- Added an explicit repository mapper between the domain field and the compatible database column
  `engine_state_version`; removed reflective dataclass-to-row persistence.
- Updated callers and tests to import the public cost-basis API.
- Added a structural test that prevents the retired legacy checkpoint modules from returning.
- Added responsibility docstrings to both moved modules.

## Compatibility And Data Decision

No API, event, table, column, migration, or stored value changed. The database column remains
`engine_state_version` to preserve deployed schema and rollback compatibility. Renaming it now
would create migration and operational risk without improving runtime behavior; the repository is
the anti-corruption boundary between storage vocabulary and the clearer domain name.

## Validation

- Checkpoint, workflow, repository, consumer, and structure cohort: `107 passed`.
- Broader cost and target-adapter cohort: `308 passed in 16.67s`.
- PostgreSQL average-cost capacity proof: `2 passed in 67.66s`.
- Repository-native transaction-processing contract: `32 passed in 126.23s`.
- Final focused proof after import normalization: `57 passed`.
- Ruff, formatting, MyPy, strict architecture, domain-layer, testability, in-process modularity, and
  installed-package import checks passed.
- Reconciliation onto the post-PR-727 mainline passed `319` focused cost, checkpoint,
  domain-structure, profile, and transaction-spec tests plus targeted MyPy, Ruff, architecture,
  documentation, modularity, JSON, and diff checks.

## Follow-Up

Transaction timeline orchestration and its observer port moved in CR-1513. Next extract workflow
and repository ownership incrementally, preserving the explicit checkpoint mapper and compatibility
schema until a separately evidenced database migration is justified.
