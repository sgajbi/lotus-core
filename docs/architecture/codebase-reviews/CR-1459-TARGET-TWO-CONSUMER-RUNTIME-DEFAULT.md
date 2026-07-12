# CR-1459: Target Two-Consumer Runtime Default

Date: 2026-07-10
Issue: #468
Status: Hardened locally

## Objective

Make the undeployed `portfolio_transaction_processing_service` start its final two-consumer
topology instead of silently recreating the six-consumer compatibility host.

## Defect

`ConsumerManager` still defaulted to `build_legacy_transaction_consumers()`. The target package
therefore had final live/replay consumers and composition available but did not use them when
started normally. Packaging that state into an image would misleadingly run six legacy loops under
the new service identity.

The manager also used truthiness fallback for injected consumers and dispatcher. An intentionally
empty test/diagnostic consumer set or a valid false-valued collaborator could be replaced silently.

## Change

- default manager composition is now `build_transaction_processing_consumers()`;
- the normal target process starts one `transactions.persisted` consumer and one
  `transactions.reprocessing.requested` consumer;
- consumer and dispatcher injection use explicit `is not None` selection;
- the compatibility registry remains available for rollback characterization but is no longer the
  target package default.

## Compatibility And Rollout

This does not change deployed runtime. Docker Compose, Kubernetes, and current service inventories
still start the separate cost, cashflow, and position calculator services and do not start the target
package. It changes only what happens when the not-yet-deployed target entry point is invoked.

The target must not be added alongside the three legacy workers in a shared environment. Deployment
cutover must replace the old workers atomically after image, load, observability, downstream, and
rollback evidence passes.

No public API, topic payload, database schema, active group offset, README, or wiki current-runtime
claim changed.

## Validation

- target transaction-processing unit pack: 62 passed;
- tests prove final default composition, shared runtime delegation, and preservation of intentionally
  empty injected components;
- focused MyPy and Ruff passed;
- diff check passed.
