# CR-1465: Transaction Processing CI Contract Suite

Date: 2026-07-10
Issue: #468
Status: Hardened locally; runtime service-set cutover pending

## Objective

Make the complete combined transaction-processing PostgreSQL contract blocking in pull requests
and main releasability instead of relying on release-wide integration or manual commands.

## Implementation

- Added the manifest-owned `transaction-processing-contract` suite.
- Added `make test-transaction-processing-contract` as the repository-native entrypoint.
- Configured the suite for the integration environment and DB-direct runtime.
- Added the suite to `make test-pr-suites`, PR Merge Gate, and Main Releasability matrices.
- Added scope tests proving the suite starts only PostgreSQL and migrations.
- Added a runtime-set guard proving the undeployed target is not added beside legacy calculator
  Compose services before atomic cutover.

The suite owns the complete
`tests/integration/services/portfolio_transaction_processing_service` tree, including atomic
success/rollback, replay, adjustment, FIFO, AVCO, fees, FX, multi-lot, backdated correction,
current-epoch position rebuild, and one-event-per-input behavior.

## Validation Evidence

- focused manifest/scope/service-set/governance tests: 25 passed;
- suite path validation: 1 entry, passed;
- test-lane governance guard: passed;
- repository-native target: 17 passed in 83.91 seconds;
- Ruff, format, and diff checks: passed.

## Compatibility And Remaining Work

No application, calculation, API, Kafka, database, image, or deployed runtime behavior changed.
Feature Lane remains fast and does not run this DB-heavy pack. PR and main lanes now block on it.

`scripts/ci_service_sets.py` intentionally remains on the three legacy calculator services because
Compose does not yet define the target. Add the target and remove the legacy services in the same
deployment cutover; never make CI start both topologies. No wiki change is required beyond the CI
reader guidance updated in this slice.
