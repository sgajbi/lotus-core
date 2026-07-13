# CR-1562 Corporate Action Ownership And Evidence

Date: 2026-07-14

## Objective

Advance issue #719 by moving corporate-action validation, basis reconciliation, and reconciliation
evidence policy into the unified transaction-processing capability.

## Findings

- Bundle A validation and reconciliation were single-consumer policies under `portfolio_common`.
- The 1,617-line cost infrastructure workflow coordinated group loading, domain calculation,
  deterministic evidence, persistence dictionaries, logging, metrics, and batch deduplication.
- Finding status and reason-code vocabularies were open strings inside infrastructure.

## Change

- Added transaction-service-owned corporate-action validation over immutable
  `BookedTransaction`.
- Added service-owned basis reconciliation with a closed reconciliation status vocabulary.
- Added typed application coordination, repository and observer ports, immutable run and finding
  evidence, per-batch group deduplication, and closed finding and reason-code vocabularies.
- Mapped ORM rows to `BookedTransaction` and evidence records to SQLAlchemy writes only inside the
  repository adapter; support logs and metrics now run through a dedicated observer after a
  successful persistence write.
- Routed cost and cashflow production callers through the owned domain policies.
- Deleted the obsolete shared validation/reconciliation facades and moved their tests to the owner.
- Reduced `cost_calculation_workflow.py` from 1,617 to 1,145 lines while keeping persistence,
  metrics, and logging in dedicated infrastructure adapters.
- Removed the duplicate cost-basis transaction-type enum in favor of the governed canonical
  transaction registry and published a generated, guarded lifecycle capability catalog.

## Architecture Decision

This is design modularity inside the existing transaction-processing deployable. No workload,
failure-isolation, security, scaling, or ownership evidence justifies another runtime service.

## Compatibility

API, event, topic, database, reconciliation record, deterministic ID, downstream response, and
runtime topology contracts are unchanged.

## Validation

- `688` transaction-processing unit tests passed.
- `64` focused application, repository, workflow, composition, and observability tests passed.
- `24` architecture, dependency-inversion, repository-shape, mapping, and capability-catalog guard
  tests passed.
- Both PostgreSQL mixed-demerger lifecycle cases passed, including atomic rollback evidence.
- The canonical transaction-registry cleanup passed `112` cost, registry, and transaction-spec
  tests. Scoped Ruff and all affected architecture guards passed.
- Same-pattern structure and generated-catalog guards prevent retired facades, duplicate type
  vocabularies, and unsupported lifecycle claims from returning.

## Contract And Documentation Decisions

- No OpenAPI, route, event, topic, database migration, table, or downstream response changed.
- Repository context, the codebase-review ledger, supported-feature documentation, authored wiki,
  and generated transaction capability catalog changed because ownership and support truth changed.
- Central platform context and skills did not change: existing layered-architecture, issue-evidence,
  and documentation governance already cover this pattern.

## Remaining Work

Issue #719 remains open for complete cost/cashflow/position ownership, legacy calculator runtime
retirement, replay/backdating/concurrency proof, and final database/runtime cleanup. Issues #450,
#480, and #481 retain partial allocation, parent-event graph, and lot-lineage gaps.
