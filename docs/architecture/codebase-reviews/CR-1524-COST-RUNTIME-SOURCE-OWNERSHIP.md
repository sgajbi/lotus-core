# CR-1524: Cost Runtime Source Ownership

Date: 2026-07-11
Issue: #468
Status: Implemented locally; compatibility test shell removal pending

## Objective

Move the active cost workflow, SQL repository, and metrics into the unified transaction-processing
package and prove that its installed image no longer depends on copied calculator source.

## Finding

The target wheel owned cost-basis domain and application policy, but active composition still
imported a 1,588-line workflow, 1,029-line repository, and Prometheus instruments from the legacy
calculator source root. The Dockerfile copied that root to satisfy imports, and the installed
entrypoint failed because the copied workflow imported target modules through a repository-only
`src.services...` path.

## Implementation

- Moved the active cost workflow, SQLAlchemy repository, and cost processing metrics into target
  infrastructure.
- Replaced repository-root self-imports with package-relative target imports.
- Rewired composition, adapters, reconciliation, the unit of work, tests, and repository guard
  registrations to target ownership.
- Added public domain names for cost normalization and advisory lock-key policy while retaining
  behavior.
- Removed the cost calculator source copy from the target Dockerfile.
- Strengthened the compatibility import test to require zero legacy calculator imports from the
  target service.
- Kept the legacy consumer shell outside the image only for its remaining mixed delivery
  characterization tests; it is not runtime composition.

## Boundary And Compatibility Decision

Cost, cashflow, and position remain cohesive in-process financial modules behind one application
use case and unit of work. This move changes source ownership, not runtime topology.

Cost-basis methods, ordering, checkpoint and replay behavior, locking, SQL queries, outbox events,
metrics, transaction boundaries, API contracts, and database schema are unchanged. The
compatibility consumer is not copied into the image and must be deleted after its workflow tests
are separated from obsolete Kafka delivery tests.

## Validation

- Cost, target transaction service, transaction RFC, portfolio-flow, and image-inventory cohort:
  `307 passed`; corrected structural assertion: `1 passed`.
- Target MyPy: `71 source files`, no issues.
- Main reconciliation: `305 passed`; targeted MyPy, Ruff, repository-output, domain,
  infrastructure-adapter, modularity, and diff guards passed while preserving pipeline readiness.
- Ruff, domain-layer, infrastructure-adapter, and target repository output-shape guards passed.
- Target image built successfully.
- Installed image imported `app.main`, cost workflow, and cashflow workflow and proved both legacy
  calculator source roots absent.

## Same-Pattern Scan

No active target module imports `src.services.calculators`. The remaining
`cost_calculator_service/app/consumer.py` is test-only compatibility delivery debt. Its mixed
2,065-line test must be decomposed so workflow/domain coverage remains while obsolete standalone
physical-idempotency, retry, and DLQ behavior is deleted.

## Documentation Decision

Repository context, modularity catalog, wiki architecture, and review ledger change. README and API
documentation remain unchanged because commands and public contracts did not change.
