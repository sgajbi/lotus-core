# CR-1521: Simulation Decision Boundary

Date: 2026-07-11
Issues: #465, #470, #709, #710, #711
Status: Hardened locally; advisory migration and generic projection redesign remain open

## Objective

Prevent generic Core simulation from absorbing downstream advisory decisioning while preserving the
existing advisory compatibility endpoint and consumer contract during a governed migration.

## Findings

- Query control plane owns the simulation routes, but generic application and persistence code still
  lives under `query_service` and constructs concrete repositories from an async database session.
- Generic simulation applies quantity deltas rather than the complete transaction economics owned
  by Core.
- Advisory compatibility code contains suitability scanning and workflow-gate decisions that belong
  to `lotus-advise` after migration.
- The compatibility model module contained 1,516 physical lines and mixed source-state, proposal,
  suitability, workflow, evidence, and response concepts.
- Simulation sessions do not yet pin immutable effective-dated baselines or provide complete
  tenant, concurrency, idempotency, and replay controls.

## Implementation

- Added an architecture rule that blocks generic simulation router, DTO, repository, and service
  modules from importing advisory decisioning through absolute or relative imports.
- Kept `/integration/advisory/proposals/simulate-execution` as an explicit compatibility route; the
  guard does not silently break its current downstream contract.
- Moved suitability thresholds, suitability evidence/results, and workflow gate decisions into
  `advisory_decision_models.py` with a module responsibility docstring.
- Preserved imports and Pydantic/OpenAPI behavior through identity-preserving re-exports from the
  existing `models.py` compatibility surface.
- Narrowed proposal status typing to its three contract values instead of arbitrary `str`.
- Raised or reused GitHub issues for every actionable deferred finding rather than retaining them in
  chat: #465, #470, and #709 through #714.

## Ownership Decision

Core owns deterministic source-state projection, baseline identity, transaction effects,
execution-feasibility facts, and source lineage. `lotus-advise` owns recommendation, suitability,
proposal ranking, approval, and advisor/client workflow. `lotus-risk` owns scenarios, stress,
concentration, VaR, and risk conclusions. Simulation remains an in-process control-plane module; a
new deployable requires measured independent scaling or isolation evidence.

## Compatibility

No route, request or response field, Pydantic model identity, OpenAPI schema, database table, Kafka
contract, suitability result, workflow gate, risk consumer, or advisory consumer behavior changed.
The extracted models are explicitly transitional compatibility types, not approval for new Core
decisioning.

## Validation

- Architecture-boundary unit tests: `22 passed`.
- Advisory simulation unit/integration cohort: `122 passed`.
- Scoped MyPy: five simulation source files passed.
- Scoped Ruff lint/format and strict architecture guard passed.
- Reconciliation onto the post-PR-727 mainline reran boundary, advisory compatibility, MyPy, Ruff,
  strict architecture, documentation, and diff checks.

## Follow-Up

1. Complete #470 by splitting source inputs/projected effects from downstream decision outputs and
   migrating advisory decision ownership with versioned consumer proof.
2. Complete #465 by deciding query-service versus query-control-plane module and runtime ownership.
3. Complete #709 through #711 for unified transaction-economics projection, immutable baseline
   lineage, and session isolation/concurrency/idempotency.
4. Do not close #470 until Core no longer claims downstream advisory decision ownership and all
   compatibility changes are tested and documented.
