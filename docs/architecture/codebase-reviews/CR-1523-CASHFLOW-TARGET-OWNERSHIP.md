# CR-1523: Cashflow Target Ownership

Date: 2026-07-11
Issue: #468
Status: Implemented locally; cost source closure remains open

## Objective

Remove the retired standalone cashflow calculator source root and make cashflow vocabulary,
calculation, staging, rule access, and persistence explicit modules of the unified portfolio
transaction-processing service.

## Finding

The active transaction runtime already invoked cashflow inside the same ordered unit of work as
cost and position, but its implementation and tests remained under
`calculators/cashflow_calculator_service`. The target image copied that legacy source tree, and a
dead standalone Kafka consumer retained duplicate physical-idempotency, transaction, retry, and DLQ
ownership.

## Implementation

- Moved cashflow type vocabulary to the target domain package.
- Moved the immutable `StoredCashflow` persistence output into the target domain and preserved
  atomic current-main repair/upsert behavior.
- Moved cashflow calculation, rule-cache staging, SQL rule access, and SQL cashflow persistence to
  target infrastructure with explicit domain names and module docstrings.
- Rewired composition and the SQLAlchemy unit of work to target-owned imports.
- Deleted the standalone cashflow consumer and legacy package root.
- Moved calculation, repository, rule-contract, and transaction RFC tests to target ownership.
- Replaced consumer-shaped cache/lineage coverage with focused staging-workflow tests.
- Removed temporary generic calculation/repository aliases in favor of explicit domain names.
- Removed the legacy cashflow source copy from the target image and stale pytest source path.
- Updated test-suite manifests, supported-feature implementation paths, failure-recovery service
  identity, and repository output-shape registration.

## Boundary And Compatibility Decision

This is design and source ownership consolidation inside the already unified deployable. Cashflow
remains a separate financial module behind `CashflowProcessingPort`; no additional runtime,
database, queue, or scaling boundary was introduced.

Cashflow amounts, timing, level, classification, corporate-action lineage, transaction validation,
rule versioning, semantic identity, epoch fencing, SQL rows, outbox topic/payload, API contracts,
and database schema are unchanged. The historical cashflow semantic-idempotency service name remains
unchanged to preserve replay compatibility.

## Validation

- Source-branch cashflow, transaction RFC, portfolio-flow, composition, and image-contract cohort:
  `135 passed`.
- Main reconciliation focused cohort: `129 passed`.
- Target package MyPy: `68 source files`, no issues.
- Ruff, domain-layer, infrastructure-adapter, in-process modularity, supported-features, and
  target-scoped repository output-shape guards passed.
- Target Docker image built without the legacy cashflow source tree.
- Installed entrypoint proof remains blocked by the known legacy cost source self-import; #468 owns
  that next slice.
- Repository output-shape validation passed after moving the existing transitional timeseries and
  aggregation registrations to their service-owned paths; later typed-record slices remove them.
- Repo-local wiki validation passed. Platform wiki check-only correctly reports publication drift
  while this branch remains unmerged; publication is a post-merge action.

## Same-Pattern Scan

The position legacy root was already retired. Cost is the only remaining calculator source root
copied into the target image and causes the installed entrypoint failure. It remains the next #468
slice. Valuation stays separate pending the evidence-gated runtime decision in #713.

## Documentation Decision

Repository context, the modularity adoption catalog, supported-feature source paths, and wiki
architecture truth changed in this slice. README and public API documentation did not change
because no command, endpoint, or consumer contract changed.
