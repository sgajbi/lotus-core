# CR-1510: Cost-Basis Domain Target Ownership

Date: 2026-07-11
Issue: #468
Status: Reconciled onto current main; aggregate validation and workflow/persistence migration pending

## Objective

Make the unified transaction-processing service the unambiguous owner of cost-basis models,
calculation policies, transaction ordering, lot disposition, and calculation diagnostics.

## Finding

The combined runtime imported active business rules from the legacy
`cost_calculator_service/app/cost_engine` package. Generic names such as `processing`, `parser`,
`sorter`, `cost_objects`, `ErrorReporter`, and `Transaction` obscured the domain boundary and made
new work likely to extend a retired service layout.

## Implementation

- Moved the pure calculation closure to
  `portfolio_transaction_processing_service/app/domain/cost_basis`.
- Organized value models separately from deterministic calculation services.
- Renamed generic modules and symbols to cost-basis transaction, transaction ordering, lot state,
  lot disposition, cost-basis calculation, and calculation-error language.
- Added one public `cost_basis` API so workflows and tests do not import internal file layout.
- Added concise responsibility docstrings to every moved module.
- Removed the old `cost_engine` tree, its test-only Python path, and active vocabulary.
- Added package-structure tests for docstrings, domain-specific filenames, and legacy-path absence.
- Renamed the current cost-basis domain standard and retained framework-independence enforcement.

## Architecture And Compatibility

The target domain package imports no framework, SQLAlchemy, Kafka, repository, or infrastructure
code. The transitional cost workflow, checkpoint helpers, transaction processor, and SQL repository
now consume the target domain API. They remain under the legacy cost root until application ports
and persistence records are extracted in later slices.

No public API, Kafka topic/payload, database schema, or persisted calculation behavior changed.
Internal profile evidence now uses `cost_basis_calculation` instead of the retired `cost_engine`
label. This is an intentional developer-evidence vocabulary change, not a runtime metric change.

## Validation

- Complete cost unit, target adapter/composition, and transaction-spec cohort: `346 passed`.
- Repository-native transaction-processing contract: `32 passed in 127.90s`.
- Installed target distribution imported the public cost-basis API without the legacy engine root.
- Ruff, MyPy, strict architecture, domain-layer, testability, and in-process modularity gates passed.
- Reconciliation onto the post-PR-727 mainline retained the non-lot full-rebuild lot-state refresh
  and passed `318` focused cost, domain-structure, profile, and transaction-spec tests plus targeted
  MyPy, Ruff, domain, modularity, repository-output, testability, reducer, architecture, JSON, and
  diff guards.

## Remaining Work

Extract the cost workflow behind target application ports, move checkpoint/rebuild policy to target
application/domain ownership, and move SQL records/repository to target infrastructure. Delete the
legacy delivery shell only after its remaining delivery tests are migrated to the active consumer.

After cost/cashflow code ownership stabilizes, review transaction cost, lot state, cost-processing
checkpoint, average-cost pool, cashflow, position-history, and obsolete pipeline-stage tables for
duplicate state, write amplification, missing constraints/indexes, and redundant lifecycle rows.
Any schema change requires additive migration, rollback, replay/backfill, query-plan, concurrency,
and downstream read-contract evidence; table merging is not an objective by itself.

No platform skill change is required. Existing backend delivery and codebase-review governance
already require truthful ownership, framework-free domain logic, migration proof, and prevention
guards.
